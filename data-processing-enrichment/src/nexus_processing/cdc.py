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

"""Change Data Capture (CDC) / webhook event normalization.

One entry point for the change-event formats databases actually emit:

  * Debezium (MySQL, PostgreSQL, SQL Server...) — with or without the
    schema/payload envelope; primary key taken from the message key when present
  * Maxwell (MySQL binlog)                      — ``type``/``data``/``old``
  * MongoDB change streams                      — ``operationType``/``documentKey``;
    partial updates (no ``fullDocument``) are flagged so consumers can merge
  * generic webhooks                            — ``{"op", "table", "record"}``

Payloads may be a single event, a list, ``{"events": [...]}`` or NDJSON text.
``verify_webhook_signature`` implements HMAC-SHA256 request signing with optional
timestamp binding (replay protection).
"""

from __future__ import annotations

import hashlib
import hmac
import json
import time
from dataclasses import dataclass, field
from typing import Any

MAX_EVENTS_PER_BATCH = 1000

_OPS = {
    "c": "INSERT", "create": "INSERT", "insert": "INSERT", "i": "INSERT",
    "u": "UPDATE", "update": "UPDATE", "replace": "UPDATE",
    "d": "DELETE", "delete": "DELETE", "remove": "DELETE",
    "r": "READ", "read": "READ", "bootstrap-insert": "READ",
    "t": "TRUNCATE", "truncate": "TRUNCATE", "drop": "TRUNCATE",
    "m": "HEARTBEAT", "heartbeat": "HEARTBEAT", "bootstrap-start": "HEARTBEAT", "bootstrap-complete": "HEARTBEAT",
}
_KEY_CANDIDATES = ("id", "_id", "uuid", "pk", "key")


@dataclass
class ChangeEvent:
    operation: str  # INSERT | UPDATE | DELETE | READ | TRUNCATE | HEARTBEAT | UNKNOWN
    source_format: str  # debezium | maxwell | mongodb | generic
    database: str
    table: str
    key: str
    record: dict[str, Any] = field(default_factory=dict)
    removed_fields: list[str] = field(default_factory=list)
    partial: bool = False  # only changed fields are present (merge with stored record)
    timestamp_ms: int = 0

    @property
    def is_delete(self) -> bool:
        return self.operation == "DELETE"

    @property
    def is_data_change(self) -> bool:
        return self.operation in ("INSERT", "UPDATE", "DELETE", "READ")


def _jsonable(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        if set(value) == {"$oid"}:
            return str(value["$oid"])
        if set(value) == {"$date"}:
            return value["$date"]
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    return str(value)


def _derive_key(record: dict[str, Any] | None, explicit: Any = None) -> str:
    if isinstance(explicit, dict):
        explicit = explicit.get("payload", explicit)
        if isinstance(explicit, dict) and explicit:
            values = [str(_jsonable(v)) for _, v in sorted(explicit.items())]
            return values[0] if len(values) == 1 else "|".join(values)
    elif explicit not in (None, ""):
        return str(_jsonable(explicit))
    record = record or {}
    for name in _KEY_CANDIDATES:
        if record.get(name) not in (None, ""):
            return str(_jsonable(record[name]))
    digest = json.dumps(_jsonable(record), sort_keys=True, default=str).encode("utf-8")
    return "h:" + hashlib.sha256(digest).hexdigest()[:24]


def normalize_change_event(event: dict[str, Any]) -> ChangeEvent:
    """Detect the CDC format of one event and normalize it."""
    if not isinstance(event, dict):
        raise ValueError("change event must be a JSON object")

    # MongoDB change stream
    if "operationType" in event:
        ns = event.get("ns") or {}
        doc_key = (event.get("documentKey") or {}).get("_id", event.get("_id"))
        full = event.get("fullDocument")
        update = event.get("updateDescription") or {}
        partial = full is None and bool(update)
        record = _jsonable(full if full is not None else update.get("updatedFields") or {})
        return ChangeEvent(
            operation=_OPS.get(str(event["operationType"]).lower(), "UNKNOWN"),
            source_format="mongodb",
            database=str(ns.get("db", event.get("db", ""))),
            table=str(ns.get("coll", event.get("collection", ""))),
            key=_derive_key(record, doc_key),
            record=record if isinstance(record, dict) else {},
            removed_fields=list(update.get("removedFields") or []),
            partial=partial,
            timestamp_ms=int((event.get("wallTime") or {}).get("$date", 0) or 0) if isinstance(event.get("wallTime"), dict) else 0,
        )

    # Maxwell: {"database","table","type","ts","data","old","primary_key"}
    if "type" in event and "data" in event and "database" in event:
        op = _OPS.get(str(event["type"]).lower(), "UNKNOWN")
        record = _jsonable(event.get("data") or {})
        return ChangeEvent(
            operation=op,
            source_format="maxwell",
            database=str(event.get("database", "")),
            table=str(event.get("table", "")),
            key=_derive_key(record, event.get("primary_key")),
            record=record,
            timestamp_ms=int(event.get("ts", 0) or 0) * 1000,
        )

    # Debezium (optionally wrapped: {"schema":..,"payload":..}; Kafka key may ride along)
    payload = event.get("payload", event) if isinstance(event.get("payload", event), dict) else event
    if "op" in payload and ("before" in payload or "after" in payload or "source" in payload):
        op = _OPS.get(str(payload["op"]).lower(), "UNKNOWN")
        source = payload.get("source") or {}
        before, after = payload.get("before"), payload.get("after")
        record = _jsonable((before if op == "DELETE" else after) or {})
        return ChangeEvent(
            operation=op,
            source_format="debezium",
            database=str(source.get("db", "")),
            table=str(source.get("table", source.get("collection", ""))),
            key=_derive_key(record, event.get("key")),
            record=record,
            timestamp_ms=int(payload.get("ts_ms") or source.get("ts_ms") or 0),
        )

    # Generic webhook: {"op"/"operation", "table"/"collection", "record"/"after"/"data", "key"?}
    op_raw = event.get("operation", event.get("op", "insert"))
    record = _jsonable(event.get("record") or event.get("after") or event.get("data") or event.get("before") or {})
    return ChangeEvent(
        operation=_OPS.get(str(op_raw).lower(), "UNKNOWN"),
        source_format="generic",
        database=str(event.get("database", event.get("db", ""))),
        table=str(event.get("table", event.get("collection", "events"))),
        key=_derive_key(record if isinstance(record, dict) else {}, event.get("key", event.get("primary_key"))),
        record=record if isinstance(record, dict) else {"value": record},
        timestamp_ms=int(event.get("ts_ms", event.get("timestamp_ms", 0)) or 0),
    )


def normalize_change_events(payload: Any) -> list[ChangeEvent]:
    """Normalize a single event, a list, ``{"events": [...]}`` or NDJSON text."""
    if isinstance(payload, (bytes, bytearray)):
        payload = payload.decode("utf-8")
    if isinstance(payload, str):
        text = payload.strip()
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            payload = [json.loads(line) for line in text.splitlines() if line.strip()]
    if isinstance(payload, dict) and isinstance(payload.get("events"), list):
        payload = payload["events"]
    events = payload if isinstance(payload, list) else [payload]
    if len(events) > MAX_EVENTS_PER_BATCH:
        raise ValueError(f"batch too large: {len(events)} events (max {MAX_EVENTS_PER_BATCH})")
    return [normalize_change_event(e) for e in events]


def change_event_text(event: ChangeEvent) -> str:
    """Self-describing chunk text for one record's current state."""
    location = ".".join(p for p in (event.database, event.table) if p)
    fields = " | ".join(f"{k}: {v}" for k, v in event.record.items() if v not in (None, ""))
    return f"[Table: {location} | Record: {event.key}] {fields}"


def sign_webhook_payload(secret: str, body: bytes, timestamp: str | None = None) -> str:
    """``sha256=<hex>`` HMAC of ``body`` (or ``"<timestamp>.<body>"`` when timestamped)."""
    message = f"{timestamp}.".encode() + body if timestamp else body
    return "sha256=" + hmac.new(secret.encode("utf-8"), message, hashlib.sha256).hexdigest()


def verify_webhook_signature(
    secret: str,
    body: bytes,
    signature: str | None,
    timestamp: str | None = None,
    tolerance_seconds: int = 300,
) -> bool:
    """Constant-time HMAC-SHA256 verification; rejects stale timestamps (replay)."""
    if not secret or not signature:
        return False
    if timestamp:
        try:
            if abs(time.time() - float(timestamp)) > tolerance_seconds:
                return False
        except ValueError:
            return False
    expected = sign_webhook_payload(secret, body, timestamp)
    provided = signature.strip()
    if not provided.startswith("sha256="):
        provided = "sha256=" + provided
    return hmac.compare_digest(expected, provided)
