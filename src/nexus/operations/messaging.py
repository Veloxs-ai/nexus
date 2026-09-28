# Copyright 2026 Veloxs AI Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
# SPDX-License-Identifier: Apache-2.0

"""Outbound messages: safe templates and pluggable channel providers.

Templates only substitute ``{field}`` placeholders — no attribute access, indexing or
format specs — so a template written by a business user can never read more than the
values it is given. Regulated channels are supported the way they are used in
practice: WhatsApp business-initiated messages go out as pre-approved templates with
positional parameters, and Indian SMS carries the TRAI DLT template id.

Providers share one small interface (``send(message) -> SendResult``) and take their
secrets as constructor arguments, never from global state:

  * ``DryRunProvider``      — records messages, sends nothing (the safe default)
  * ``WebhookProvider``     — HTTPS POST to the lender's own gateway, HMAC-SHA256 signed
    with a timestamp, and the idempotency key as a header
  * ``SmtpEmailProvider``   — e-mail over SMTP with STARTTLS or implicit TLS
  * ``WhatsAppCloudProvider`` — Meta WhatsApp Cloud API template messages
  * ``TwilioSmsProvider``   — Twilio Programmable Messaging

Every provider reports whether a failure is worth retrying, so an outbox can back off
on timeouts and 5xx responses but stop at once on a rejected number.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import re
import smtplib
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Mapping
from dataclasses import dataclass, field
from email.message import EmailMessage
from typing import Any, Protocol

_TOKEN = re.compile(r"\{\{|\}\}|\{([A-Za-z_][A-Za-z0-9_]{0,63})\}|[{}]")
MAX_BODY_CHARS = 4096


class TemplateError(ValueError):
    """A message template is malformed."""


def template_fields(template: str) -> set[str]:
    """Placeholders in ``template``; only ``{name}`` is allowed (``{{`` / ``}}`` escape)."""
    names: set[str] = set()
    for match in _TOKEN.finditer(template):
        token = match.group(0)
        if token in ("{{", "}}"):
            continue
        if match.group(1) is None:
            raise TemplateError("templates may only contain {field} placeholders")
        names.add(match.group(1))
    return names


def render_template(template: str, values: Mapping[str, Any]) -> str:
    """Substitute ``{field}`` placeholders; missing values render as an empty string."""
    template_fields(template)

    def sub(match: re.Match[str]) -> str:
        token = match.group(0)
        if token in ("{{", "}}"):
            return token[0]
        value = values.get(match.group(1))
        return "" if value is None else str(value)

    return _TOKEN.sub(sub, template)[:MAX_BODY_CHARS]


def mask_recipient(value: str | None) -> str:
    """``+91 98******21`` / ``r***@example.in`` for logs and audit trails."""
    if not value:
        return ""
    value = value.strip()
    if "@" in value:
        local, _, domain = value.partition("@")
        return f"{local[:1]}***@{domain}"
    digits = re.sub(r"\D", "", value)
    if len(digits) < 6:
        return "*" * len(digits)
    plus = "+" if value.startswith("+") else ""
    return f"{plus}{digits[:2]}{'*' * (len(digits) - 4)}{digits[-2:]}"


@dataclass
class Message:
    channel: str
    to: str
    body: str = ""
    subject: str | None = None
    language: str = "en"
    idempotency_key: str = ""
    template_name: str | None = None  # WhatsApp approved template
    template_params: list[str] = field(default_factory=list)
    dlt_template_id: str | None = None  # India SMS (TRAI DLT)
    sender_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class SendResult:
    ok: bool
    provider: str
    provider_ref: str | None = None
    status: str = "sent"  # sent | delivered | failed
    error: str | None = None
    retryable: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "provider": self.provider,
            "provider_ref": self.provider_ref,
            "status": self.status,
            "error": self.error,
            "retryable": self.retryable,
        }


class ChannelProvider(Protocol):
    name: str

    def send(self, message: Message) -> SendResult: ...


def _fail(provider: str, error: str, retryable: bool) -> SendResult:
    return SendResult(
        ok=False, provider=provider, status="failed", error=error[:500], retryable=retryable
    )


def _http(
    provider: str,
    url: str,
    body: bytes,
    headers: dict[str, str],
    timeout: float,
) -> tuple[SendResult | None, dict[str, Any]]:
    """POST and parse JSON; returns (failure, {}) or (None, response)."""
    request = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read(65536).decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        detail = exc.read(2048).decode("utf-8", "replace") if exc.fp else ""
        retryable = exc.code >= 500 or exc.code in (408, 425, 429)
        return _fail(provider, f"HTTP {exc.code}: {detail[:300]}", retryable), {}
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        return _fail(provider, f"network error: {exc}", True), {}
    try:
        return None, (json.loads(raw) if raw.strip() else {})
    except ValueError:
        return None, {"raw": raw[:500]}


def _require_https(url: str, allow_insecure: bool) -> None:
    parsed = urllib.parse.urlparse(url)
    local = parsed.hostname in ("localhost", "127.0.0.1", "::1")
    if parsed.scheme != "https" and not (allow_insecure and local):
        raise ValueError("provider URLs must use https (plain http only for localhost testing)")


class DryRunProvider:
    """Records what would be sent. Nothing leaves the process."""

    name = "dry_run"

    def __init__(self) -> None:
        self.sent: list[Message] = []

    def send(self, message: Message) -> SendResult:
        self.sent.append(message)
        digest = hashlib.sha256(f"{message.idempotency_key}|{message.to}".encode()).hexdigest()
        return SendResult(
            ok=True, provider=self.name, provider_ref=f"dry-run:{digest[:16]}", status="delivered"
        )


class WebhookProvider:
    """POST JSON to the lender's messaging gateway.

    Headers: ``Idempotency-Key`` (the gateway can drop duplicates) and
    ``X-Nexus-Signature: t=<unix>,v1=<hex>`` where ``v1 = HMAC-SHA256(secret, "<t>.<body>")``.
    The receiver should reject signatures older than a few minutes.
    """

    name = "webhook"

    def __init__(self, url: str, secret: str, timeout: float = 10.0, allow_insecure: bool = False):
        _require_https(url, allow_insecure)
        if len(secret or "") < 16:
            raise ValueError("webhook signing secret must be at least 16 characters")
        self.url, self.secret, self.timeout = url, secret, timeout

    def sign(self, body: bytes, timestamp: int) -> str:
        mac = hmac.new(self.secret.encode(), f"{timestamp}.".encode() + body, hashlib.sha256)
        return f"t={timestamp},v1={mac.hexdigest()}"

    def send(self, message: Message) -> SendResult:
        payload = {
            "channel": message.channel,
            "to": message.to,
            "body": message.body,
            "subject": message.subject,
            "language": message.language,
            "template_name": message.template_name,
            "template_params": message.template_params,
            "dlt_template_id": message.dlt_template_id,
            "sender_id": message.sender_id,
            "idempotency_key": message.idempotency_key,
            "metadata": message.metadata,
        }
        body = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        headers = {
            "Content-Type": "application/json",
            "Idempotency-Key": message.idempotency_key,
            "X-Nexus-Signature": self.sign(body, int(time.time())),
        }
        failure, data = _http(self.name, self.url, body, headers, self.timeout)
        if failure:
            return failure
        ref = data.get("id") or data.get("message_id") or data.get("reference")
        return SendResult(ok=True, provider=self.name, provider_ref=str(ref) if ref else None)


class SmtpEmailProvider:
    name = "smtp"

    def __init__(
        self,
        host: str,
        port: int,
        sender: str,
        username: str | None = None,
        password: str | None = None,
        security: str = "starttls",  # starttls | tls | none (localhost only)
        timeout: float = 15.0,
    ):
        if security not in ("starttls", "tls", "none"):
            raise ValueError("security must be starttls, tls or none")
        if security == "none" and host not in ("localhost", "127.0.0.1", "::1"):
            raise ValueError("unencrypted SMTP is only allowed to localhost")
        self.host, self.port, self.sender = host, int(port), sender
        self.username, self.password, self.security, self.timeout = (
            username,
            password,
            security,
            timeout,
        )

    def send(self, message: Message) -> SendResult:
        email = EmailMessage()
        email["From"], email["To"] = self.sender, message.to
        email["Subject"] = message.subject or "Update on your loan"
        if message.idempotency_key:
            digest = hashlib.sha256(message.idempotency_key.encode()).hexdigest()[:32]
            email["Message-ID"] = f"<{digest}@{self.sender.partition('@')[2] or 'nexus.local'}>"
        email.set_content(message.body)
        context = ssl.create_default_context()
        try:
            if self.security == "tls":
                client: smtplib.SMTP = smtplib.SMTP_SSL(
                    self.host, self.port, timeout=self.timeout, context=context
                )
            else:
                client = smtplib.SMTP(self.host, self.port, timeout=self.timeout)
            with client:
                if self.security == "starttls":
                    client.starttls(context=context)
                if self.username:
                    client.login(self.username, self.password or "")
                refused = client.send_message(email)
        except smtplib.SMTPRecipientsRefused as exc:
            return _fail(self.name, f"recipient refused: {exc}", False)
        except (smtplib.SMTPException, OSError) as exc:
            return _fail(self.name, f"smtp error: {exc}", True)
        if refused:
            return _fail(self.name, f"recipient refused: {refused}", False)
        return SendResult(ok=True, provider=self.name, provider_ref=email["Message-ID"])


class WhatsAppCloudProvider:
    """Meta WhatsApp Cloud API; business-initiated messages must use approved templates."""

    name = "whatsapp_cloud"

    def __init__(
        self,
        phone_number_id: str,
        access_token: str,
        api_version: str = "v21.0",
        timeout: float = 10.0,
    ):
        if not re.fullmatch(r"\d{5,20}", phone_number_id or ""):
            raise ValueError("phone_number_id must be the numeric WhatsApp phone number id")
        if not re.fullmatch(r"v\d{1,3}\.\d", api_version):
            raise ValueError("api_version looks like v21.0")
        self.url = f"https://graph.facebook.com/{api_version}/{phone_number_id}/messages"
        self.token, self.timeout = access_token, timeout

    def send(self, message: Message) -> SendResult:
        if not message.template_name:
            return _fail(self.name, "WhatsApp needs an approved template name", False)
        payload = {
            "messaging_product": "whatsapp",
            "to": re.sub(r"\D", "", message.to),
            "type": "template",
            "template": {
                "name": message.template_name,
                "language": {"code": message.language or "en"},
                "components": [
                    {
                        "type": "body",
                        "parameters": [
                            {"type": "text", "text": p} for p in message.template_params
                        ],
                    }
                ]
                if message.template_params
                else [],
            },
        }
        headers = {"Content-Type": "application/json", "Authorization": f"Bearer {self.token}"}
        failure, data = _http(
            self.name, self.url, json.dumps(payload).encode(), headers, self.timeout
        )
        if failure:
            return failure
        ids = [m.get("id") for m in data.get("messages") or [] if isinstance(m, dict)]
        return SendResult(ok=True, provider=self.name, provider_ref=ids[0] if ids else None)


class TwilioSmsProvider:
    name = "twilio"

    def __init__(self, account_sid: str, auth_token: str, sender: str, timeout: float = 10.0):
        if not re.fullmatch(r"AC[0-9a-fA-F]{32}", account_sid or ""):
            raise ValueError("account_sid must look like AC followed by 32 hex characters")
        self.url = f"https://api.twilio.com/2010-04-01/Accounts/{account_sid}/Messages.json"
        self.sid, self.token, self.sender, self.timeout = account_sid, auth_token, sender, timeout

    def send(self, message: Message) -> SendResult:
        import base64

        body = urllib.parse.urlencode(
            {"To": message.to, "From": message.sender_id or self.sender, "Body": message.body}
        ).encode()
        auth = base64.b64encode(f"{self.sid}:{self.token}".encode()).decode()
        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "Authorization": f"Basic {auth}",
        }
        failure, data = _http(self.name, self.url, body, headers, self.timeout)
        if failure:
            return failure
        return SendResult(ok=True, provider=self.name, provider_ref=data.get("sid"))


PROVIDERS = ("dry_run", "webhook", "smtp", "whatsapp_cloud", "twilio")


def provider_from_config(config: Mapping[str, Any], secret: str | None = None) -> ChannelProvider:
    """Build a provider from non-secret settings plus one secret (token or password)."""
    kind = str(config.get("provider") or "dry_run")
    if kind == "dry_run":
        return DryRunProvider()
    if kind == "webhook":
        return WebhookProvider(
            str(config["url"]),
            secret or "",
            float(config.get("timeout", 10)),
            bool(config.get("allow_insecure", False)),
        )
    if kind == "smtp":
        return SmtpEmailProvider(
            str(config["host"]),
            int(config.get("port", 587)),
            str(config["sender"]),
            config.get("username"),
            secret,
            str(config.get("security", "starttls")),
        )
    if kind == "whatsapp_cloud":
        return WhatsAppCloudProvider(
            str(config["phone_number_id"]), secret or "", str(config.get("api_version", "v21.0"))
        )
    if kind == "twilio":
        return TwilioSmsProvider(str(config["account_sid"]), secret or "", str(config["sender"]))
    raise ValueError(f"unknown provider '{kind}' (use one of {', '.join(PROVIDERS)})")
