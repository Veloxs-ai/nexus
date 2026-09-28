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

"""Work items in the systems maintenance and operations teams already use.

One ``WorkItem`` (title, description, asset, priority, idempotency key) can become:

  * a ServiceNow incident (Table API), with the key in ``correlation_id``
  * an IBM Maximo work order (REST ``mxapiwodetail``), with the key in ``externalrefid``
  * a Microsoft Teams notification (incoming webhook / Workflows URL, Adaptive Card)
  * nothing at all (``DryRunWorkProvider``, the default)

Ticketing providers look the key up before creating, so a retried send never opens a second
ticket, and ``status(ref)`` reads a ticket's state back (``open`` / ``in_progress`` /
``resolved`` / ``closed`` / ``cancelled``) so a platform can close the loop: time to repair,
tickets left open. Credentials are passed in (never read from globals), URLs must be https,
and errors say whether a retry can help.
"""

from __future__ import annotations

import base64
import hashlib
import json
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Protocol

from .messaging import _require_https


@dataclass
class WorkItem:
    title: str
    description: str
    idempotency_key: str
    asset_ref: str | None = None
    priority: int = 3  # 1 (highest) .. 5
    category: str = "maintenance"
    site: str | None = None
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class WorkResult:
    ok: bool
    provider: str
    ref: str | None = None
    url: str | None = None
    created: bool = False  # False when an existing item with the same key was found
    error: str | None = None
    retryable: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "provider": self.provider,
            "ref": self.ref,
            "url": self.url,
            "created": self.created,
            "error": self.error,
            "retryable": self.retryable,
        }


TICKET_STATES = ("open", "in_progress", "resolved", "closed", "cancelled")
# ServiceNow incident.state (out of the box):
# 1 New, 2 In Progress, 3 On Hold, 6 Resolved, 7 Closed, 8 Canceled
SERVICENOW_STATES = {
    "1": "open",
    "2": "in_progress",
    "3": "in_progress",
    "6": "resolved",
    "7": "closed",
    "8": "cancelled",
}
# Maximo work order status (internal values):
# WAPPR, APPR, WSCH, WMATL, WPCOND, INPRG, COMP, CLOSE, CAN
MAXIMO_STATES = {
    "WAPPR": "open",
    "APPR": "open",
    "WSCH": "open",
    "WMATL": "open",
    "WPCOND": "open",
    "INPRG": "in_progress",
    "COMP": "resolved",
    "CLOSE": "closed",
    "CAN": "cancelled",
}


@dataclass
class TicketStatus:
    ok: bool
    ref: str
    state: str | None = None  # one of TICKET_STATES
    raw_state: str | None = None
    resolved_at: str | None = None  # as reported by the system (ISO or its own format)
    resolution: str | None = None
    error: str | None = None

    @property
    def done(self) -> bool:
        return self.state in ("resolved", "closed", "cancelled")

    def as_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "ref": self.ref,
            "state": self.state,
            "raw_state": self.raw_state,
            "resolved_at": self.resolved_at,
            "resolution": self.resolution,
            "error": self.error,
        }


class WorkProvider(Protocol):
    name: str

    def submit(self, item: WorkItem) -> WorkResult: ...


def _call(
    provider: str,
    method: str,
    url: str,
    headers: dict[str, str],
    body: dict[str, Any] | None,
    timeout: float,
) -> tuple[WorkResult | None, Any]:
    data = json.dumps(body).encode("utf-8") if body is not None else None
    request = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={
            "Accept": "application/json",
            **headers,
            **({"Content-Type": "application/json"} if data else {}),
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:  # https enforced
            raw = response.read(1 << 20).decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        detail = exc.read(2048).decode("utf-8", "replace") if exc.fp else ""
        retryable = exc.code >= 500 or exc.code in (408, 425, 429)
        return WorkResult(
            False, provider, error=f"HTTP {exc.code}: {detail[:300]}", retryable=retryable
        ), None
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        return WorkResult(False, provider, error=f"network error: {exc}", retryable=True), None
    try:
        return None, json.loads(raw) if raw.strip() else {}
    except ValueError:
        return None, {}


class DryRunWorkProvider:
    name = "dry_run"

    def __init__(self) -> None:
        self.items: list[WorkItem] = []

    def submit(self, item: WorkItem) -> WorkResult:
        self.items.append(item)
        ref = "DRY-" + hashlib.sha256(item.idempotency_key.encode()).hexdigest()[:10].upper()
        return WorkResult(True, self.name, ref=ref, created=True)


class ServiceNowProvider:
    """Incident via the Table API; ``correlation_id`` carries the idempotency key."""

    name = "servicenow"

    def __init__(
        self,
        instance_url: str,
        username: str | None = None,
        password: str | None = None,
        token: str | None = None,
        assignment_group: str | None = None,
        timeout: float = 15.0,
    ):
        _require_https(instance_url, False)
        if not token and not (username and password):
            raise ValueError("ServiceNow needs an OAuth token or a username and password")
        self.base = instance_url.rstrip("/")
        auth = (
            f"Bearer {token}"
            if token
            else "Basic " + base64.b64encode(f"{username}:{password}".encode()).decode()
        )
        self.headers = {"Authorization": auth}
        self.assignment_group, self.timeout = assignment_group, timeout

    def submit(self, item: WorkItem) -> WorkResult:
        key = item.idempotency_key[:100]
        query = urllib.parse.urlencode(
            {
                "sysparm_query": f"correlation_id={key}",
                "sysparm_limit": "1",
                "sysparm_fields": "sys_id,number",
            }
        )
        failure, found = _call(
            self.name,
            "GET",
            f"{self.base}/api/now/table/incident?{query}",
            self.headers,
            None,
            self.timeout,
        )
        if failure:
            return failure
        existing = (found or {}).get("result") or []
        if existing:
            return WorkResult(
                True,
                self.name,
                ref=existing[0].get("number"),
                created=False,
                url=f"{self.base}/nav_to.do?uri=incident.do?sys_id={existing[0].get('sys_id')}",
            )
        body = {
            "short_description": item.title[:160],
            "description": item.description,
            "correlation_id": key,
            "correlation_display": "Nexora Operations",
            "urgency": str(min(3, max(1, (item.priority + 1) // 2))),
            "impact": str(min(3, max(1, (item.priority + 1) // 2))),
            "category": item.category,
            **({"cmdb_ci": item.asset_ref} if item.asset_ref else {}),
            **({"assignment_group": self.assignment_group} if self.assignment_group else {}),
        }
        failure, created = _call(
            self.name,
            "POST",
            f"{self.base}/api/now/table/incident",
            self.headers,
            body,
            self.timeout,
        )
        if failure:
            return failure
        result = (created or {}).get("result") or {}
        return WorkResult(
            True,
            self.name,
            ref=result.get("number"),
            created=True,
            url=f"{self.base}/nav_to.do?uri=incident.do?sys_id={result.get('sys_id')}",
        )

    def status(self, ref: str) -> TicketStatus:
        query = urllib.parse.urlencode(
            {
                "sysparm_query": f"number={ref}",
                "sysparm_limit": "1",
                "sysparm_fields": "number,state,resolved_at,closed_at,close_code",
                "sysparm_display_value": "false",
            }
        )
        failure, found = _call(
            self.name,
            "GET",
            f"{self.base}/api/now/table/incident?{query}",
            self.headers,
            None,
            self.timeout,
        )
        if failure:
            return TicketStatus(False, ref, error=failure.error)
        rows = (found or {}).get("result") or []
        if not rows:
            return TicketStatus(False, ref, error="ticket not found")
        row = rows[0]
        raw = str(row.get("state") or "")
        return TicketStatus(
            True,
            ref,
            state=SERVICENOW_STATES.get(raw, "in_progress"),
            raw_state=raw,
            resolved_at=row.get("resolved_at") or row.get("closed_at") or None,
            resolution=row.get("close_code") or None,
        )


class MaximoProvider:
    """Work order via the Maximo REST API (``mxapiwodetail``); ``externalrefid`` carries the key."""

    name = "maximo"

    def __init__(
        self,
        base_url: str,
        api_key: str,
        site_id: str,
        org_id: str | None = None,
        work_type: str = "CM",
        timeout: float = 20.0,
    ):
        _require_https(base_url, False)
        if not api_key or not site_id:
            raise ValueError("Maximo needs an API key and a site id")
        self.base = base_url.rstrip("/")
        self.headers = {"apikey": api_key}
        self.site_id, self.org_id, self.work_type, self.timeout = (
            site_id,
            org_id,
            work_type,
            timeout,
        )

    def submit(self, item: WorkItem) -> WorkResult:
        key = item.idempotency_key[:100].replace('"', "")
        query = urllib.parse.urlencode(
            {
                "lean": "1",
                "oslc.select": "wonum,workorderid",
                "oslc.where": f'externalrefid="{key}"',
            }
        )
        failure, found = _call(
            self.name,
            "GET",
            f"{self.base}/maximo/api/os/mxapiwodetail?{query}",
            self.headers,
            None,
            self.timeout,
        )
        if failure:
            return failure
        members = (found or {}).get("member") or []
        if members:
            return WorkResult(True, self.name, ref=members[0].get("wonum"), created=False)
        body = {
            "description": item.title[:100],
            "description_longdescription": item.description,
            "siteid": item.site or self.site_id,
            "worktype": self.work_type,
            "wopriority": max(1, min(5, item.priority)),
            "externalrefid": key,
            **({"assetnum": item.asset_ref} if item.asset_ref else {}),
            **({"orgid": self.org_id} if self.org_id else {}),
        }
        headers = {**self.headers, "properties": "wonum,workorderid"}
        failure, created = _call(
            self.name,
            "POST",
            f"{self.base}/maximo/api/os/mxapiwodetail?lean=1",
            headers,
            body,
            self.timeout,
        )
        if failure:
            return failure
        return WorkResult(True, self.name, ref=(created or {}).get("wonum"), created=True)

    def status(self, ref: str) -> TicketStatus:
        where = (
            f'wonum="{ref.replace(chr(34), "")}" and siteid="{self.site_id.replace(chr(34), "")}"'
        )
        query = urllib.parse.urlencode(
            {"lean": "1", "oslc.select": "wonum,status,actfinish,statusdate", "oslc.where": where}
        )
        failure, found = _call(
            self.name,
            "GET",
            f"{self.base}/maximo/api/os/mxapiwodetail?{query}",
            self.headers,
            None,
            self.timeout,
        )
        if failure:
            return TicketStatus(False, ref, error=failure.error)
        members = (found or {}).get("member") or []
        if not members:
            return TicketStatus(False, ref, error="work order not found")
        raw = str(members[0].get("status") or "")
        state = MAXIMO_STATES.get(raw, "in_progress")
        done_at = members[0].get("actfinish") or (
            members[0].get("statusdate") if state in ("resolved", "closed", "cancelled") else None
        )
        return TicketStatus(True, ref, state=state, raw_state=raw, resolved_at=done_at)


class TeamsProvider:
    """Adaptive Card to a Teams channel (incoming webhook or Workflows URL); notifications only."""

    name = "teams"

    def __init__(self, webhook_url: str, timeout: float = 10.0):
        _require_https(webhook_url, False)
        self.url, self.timeout = webhook_url, timeout

    def card(self, item: WorkItem) -> dict[str, Any]:
        facts = [{"title": str(k), "value": str(v)} for k, v in list(item.details.items())[:10]]
        body: list[dict[str, Any]] = [
            {
                "type": "TextBlock",
                "size": "Medium",
                "weight": "Bolder",
                "text": item.title,
                "wrap": True,
            },
            {"type": "TextBlock", "text": item.description, "wrap": True},
        ]
        if facts:
            body.append({"type": "FactSet", "facts": facts})
        return {
            "type": "message",
            "attachments": [
                {
                    "contentType": "application/vnd.microsoft.card.adaptive",
                    "content": {
                        "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
                        "type": "AdaptiveCard",
                        "version": "1.4",
                        "body": body,
                    },
                }
            ],
        }

    def submit(self, item: WorkItem) -> WorkResult:
        failure, _ = _call(self.name, "POST", self.url, {}, self.card(item), self.timeout)
        return failure or WorkResult(True, self.name, created=True)


WORK_PROVIDERS = ("dry_run", "servicenow", "maximo", "teams")


def work_provider_from_config(config: Mapping[str, Any], secret: str | None = None) -> WorkProvider:
    """Build a provider from non-secret settings plus one secret (password, token or API key)."""
    kind = str(config.get("provider") or "dry_run")
    if kind == "dry_run":
        return DryRunWorkProvider()
    if kind == "servicenow":
        if config.get("auth") == "oauth":
            return ServiceNowProvider(
                str(config["instance_url"]),
                token=secret,
                assignment_group=config.get("assignment_group"),
            )
        return ServiceNowProvider(
            str(config["instance_url"]),
            username=config.get("username"),
            password=secret,
            assignment_group=config.get("assignment_group"),
        )
    if kind == "maximo":
        return MaximoProvider(
            str(config["base_url"]),
            secret or "",
            str(config.get("site_id") or ""),
            config.get("org_id"),
            str(config.get("work_type") or "CM"),
        )
    if kind == "teams":
        return TeamsProvider(secret or str(config.get("webhook_url") or ""))
    raise ValueError(f"unknown work provider '{kind}' (use one of {', '.join(WORK_PROVIDERS)})")
