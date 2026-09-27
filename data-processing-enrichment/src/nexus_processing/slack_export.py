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

"""Slack conversations: export parsing and live Events API helpers.

Export files (workspace export .zip or a single channel's .json) and live messages
(Events API / conversations.history) share one chunking function,
``messages_to_chunks``, so both paths produce identical, comparable knowledge.
``verify_slack_signature`` implements Slack's v0 request signing for event delivery.

Slack's "Export data" produces ``users.json``, ``channels.json`` and one folder
per channel with a JSON file per day. Conversation chunks are built the way people
read Slack:

  * thread replies are grouped with their parent message (one chunk per thread)
  * top-level messages are windowed per channel/day, capped by characters
  * user IDs and ``<@U123>`` mentions are resolved to display names
  * join/leave/bot noise and empty messages are dropped
"""

from __future__ import annotations

import hashlib
import hmac
import io
import json
import re
import time
import zipfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

MAX_CHUNK_CHARS = 1500
_NOISE_SUBTYPES = {"channel_join", "channel_leave", "channel_purpose", "channel_topic", "bot_add", "bot_remove"}
_MENTION = re.compile(r"<@([A-Z0-9]+)(?:\|[^>]+)?>")
_LINK = re.compile(r"<(https?://[^|>]+)\|([^>]+)>")


@dataclass
class SlackChunk:
    channel: str
    kind: str  # "thread" | "window"
    date: str
    text: str
    participants: list[str] = field(default_factory=list)
    message_count: int = 0
    thread_ts: str | None = None


def looks_like_slack_export(data: bytes, filename: str = "") -> bool:
    name = filename.lower()
    if data[:2] == b"PK":
        try:
            names = zipfile.ZipFile(io.BytesIO(data)).namelist()
        except zipfile.BadZipFile:
            return False
        return any(n.endswith("channels.json") for n in names) or any(n.endswith("users.json") for n in names)
    if name.endswith(".json"):
        try:
            payload = json.loads(data.decode("utf-8", errors="ignore"))
        except json.JSONDecodeError:
            return False
        return isinstance(payload, list) and bool(payload) and isinstance(payload[0], dict) and "ts" in payload[0] and (
            "text" in payload[0] or "subtype" in payload[0]
        )
    return False


def _day(ts: str) -> str:
    try:
        return datetime.fromtimestamp(float(ts), tz=timezone.utc).strftime("%Y-%m-%d")
    except (TypeError, ValueError):
        return ""


def _time(ts: str) -> str:
    try:
        return datetime.fromtimestamp(float(ts), tz=timezone.utc).strftime("%H:%M")
    except (TypeError, ValueError):
        return ""


def _clean(text: str, users: dict[str, str]) -> str:
    text = _MENTION.sub(lambda m: "@" + users.get(m.group(1), m.group(1)), text or "")
    text = _LINK.sub(lambda m: f"{m.group(2)} ({m.group(1)})", text)
    return text.replace("&lt;", "<").replace("&gt;", ">").replace("&amp;", "&").strip()


def _speaker(msg: dict[str, Any], users: dict[str, str]) -> str:
    profile = msg.get("user_profile") or {}
    return (
        users.get(msg.get("user", ""))
        or profile.get("display_name") or profile.get("real_name")
        or msg.get("username") or msg.get("user") or "unknown"
    )


def messages_to_chunks(
    channel: str, messages: list[dict[str, Any]], users: dict[str, str] | None = None
) -> list[SlackChunk]:
    """Group Slack messages (export or API shape) into thread and time-window chunks."""
    users = users or {}
    msgs = [
        m for m in messages
        if isinstance(m, dict) and m.get("subtype") not in _NOISE_SUBTYPES and (m.get("text") or m.get("files"))
    ]
    msgs.sort(key=lambda m: float(m.get("ts", 0) or 0))
    threads: dict[str, list[dict[str, Any]]] = {}
    top_level: list[dict[str, Any]] = []
    for m in msgs:
        thread_ts = m.get("thread_ts")
        if thread_ts and (thread_ts != m.get("ts") or m.get("reply_count")):
            threads.setdefault(thread_ts, []).append(m)
        else:
            top_level.append(m)

    def line(m: dict[str, Any]) -> str:
        body = _clean(m.get("text", ""), users)
        files = ", ".join(f.get("name", "file") for f in m.get("files") or [] if isinstance(f, dict))
        if files:
            body = f"{body} [files: {files}]".strip()
        return f"{_time(m.get('ts'))} {_speaker(m, users)}: {body}"

    chunks: list[SlackChunk] = []
    for thread_ts, items in threads.items():
        items.sort(key=lambda m: float(m.get("ts", 0) or 0))
        text = f"[Slack #{channel} | Thread started {_day(thread_ts)}]\n" + "\n".join(line(m) for m in items)
        chunks.append(SlackChunk(channel, "thread", _day(thread_ts), text[: MAX_CHUNK_CHARS * 3],
                                 sorted({_speaker(m, users) for m in items}), len(items), thread_ts))

    window: list[dict[str, Any]] = []
    size = 0

    def flush() -> None:
        nonlocal window, size
        if window:
            day = _day(window[0].get("ts"))
            text = f"[Slack #{channel} | {day}]\n" + "\n".join(line(m) for m in window)
            chunks.append(SlackChunk(channel, "window", day, text, sorted({_speaker(m, users) for m in window}), len(window)))
        window, size = [], 0

    for m in top_level:
        rendered = len(line(m))
        if window and (_day(m.get("ts")) != _day(window[0].get("ts")) or size + rendered > MAX_CHUNK_CHARS):
            flush()
        window.append(m)
        size += rendered + 1
    flush()
    chunks.sort(key=lambda c: (c.date, c.kind))
    return chunks


def parse_slack_export(data: bytes, filename: str = "export.json") -> tuple[list[SlackChunk], dict[str, Any]]:
    """Parse a Slack workspace export (.zip) or one channel's message list (.json)."""
    if data[:2] != b"PK":
        messages = json.loads(data.decode("utf-8", errors="ignore"))
        channel = re.sub(r"\.json$", "", filename.rsplit("/", 1)[-1]) or "channel"
        chunks = messages_to_chunks(channel, messages, {})
        return chunks, {"channels": [channel], "users": 0, "messages": sum(c.message_count for c in chunks)}

    archive = zipfile.ZipFile(io.BytesIO(data))
    names = archive.namelist()

    def load(name: str) -> Any:
        try:
            return json.loads(archive.read(name).decode("utf-8", errors="ignore"))
        except (KeyError, json.JSONDecodeError):
            return []

    users_file = next((n for n in names if n.endswith("users.json")), None)
    users = {
        u.get("id"): (u.get("profile") or {}).get("display_name") or u.get("real_name") or u.get("name") or u.get("id")
        for u in (load(users_file) if users_file else []) if isinstance(u, dict)
    }
    per_channel: dict[str, list[dict[str, Any]]] = {}
    for name in names:
        parts = name.strip("/").split("/")
        if len(parts) >= 2 and name.endswith(".json") and re.match(r"\d{4}-\d{2}-\d{2}\.json$", parts[-1]):
            day_messages = load(name)
            if isinstance(day_messages, list):
                per_channel.setdefault(parts[-2], []).extend(day_messages)
    chunks: list[SlackChunk] = []
    for channel, messages in sorted(per_channel.items()):
        chunks.extend(messages_to_chunks(channel, messages, users))
    return chunks, {
        "channels": sorted(per_channel),
        "users": len(users),
        "messages": sum(c.message_count for c in chunks),
    }


def verify_slack_signature(
    signing_secret: str,
    body: bytes,
    timestamp: str | None,
    signature: str | None,
    tolerance_seconds: int = 300,
) -> bool:
    """Verify ``X-Slack-Signature`` (v0 = HMAC-SHA256 of ``"v0:<ts>:<body>"``); rejects replays."""
    if not signing_secret or not timestamp or not signature:
        return False
    try:
        if abs(time.time() - int(timestamp)) > tolerance_seconds:
            return False
    except ValueError:
        return False
    base = b"v0:" + timestamp.encode() + b":" + body
    expected = "v0=" + hmac.new(signing_secret.encode("utf-8"), base, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature.strip())


def slack_event_message(event: dict[str, Any]) -> tuple[str, dict[str, Any] | None, str | None]:
    """Map an Events API ``message`` event to ``(action, message, deleted_ts)``.

    action is ``"upsert"`` (new or edited message), ``"delete"`` or ``"ignore"``
    (joins, bot noise, non-message events). Edited messages are returned in their
    new form so callers can replace the stored copy by ``ts``.
    """
    if not isinstance(event, dict) or event.get("type") != "message":
        return "ignore", None, None
    subtype = event.get("subtype")
    if subtype == "message_deleted":
        return "delete", None, event.get("deleted_ts") or (event.get("previous_message") or {}).get("ts")
    if subtype == "message_changed":
        message = dict(event.get("message") or {})
        if not message.get("ts"):
            return "ignore", None, None
        message.setdefault("thread_ts", message.get("thread_ts"))
        return "upsert", message, None
    if subtype in _NOISE_SUBTYPES or not (event.get("text") or event.get("files")):
        return "ignore", None, None
    keep = ("ts", "thread_ts", "user", "username", "text", "files", "reply_count", "user_profile", "bot_id")
    return "upsert", {k: event[k] for k in keep if k in event}, None
