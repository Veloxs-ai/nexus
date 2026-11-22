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

"""Masked, JSON-safe row records for tabular sources.

Every tabular processor (database tables, MongoDB collections, spreadsheets, CSV)
attaches the source row to its chunk as ``metadata.record`` (one row per chunk) or
``metadata.records`` (a row group), so callers can count, total and list rows exactly
instead of reading them back out of chunk text. Records are masked by column
(``GuardrailsEngine.mask_records``): identifiers, numbers, dates and amounts keep their
values; PII columns are masked whole; free text gets the text detectors.
"""

from __future__ import annotations

import base64
import datetime as _dt
import decimal
import hashlib
import json
import uuid
from collections.abc import Iterable, Mapping
from typing import Any, Literal

try:
    from nexus.processing.record_caps import cap_document, cap_record_values
except (ImportError, ModuleNotFoundError):
    from nexus_processing.record_caps import cap_document, cap_record_values

__all__ = [
    "cap_document",
    "cap_record_values",
    "coerce_value",
    "embed_policy",
    "flatten_record",
    "jsonable",
    "mask_rows",
    "needs_vector",
    "row_hash",
    "rows_from_columns",
    "rows_to_markdown",
]

Dialect = Literal["bigquery", "snowflake", "databricks"]


def jsonable(value: Any) -> Any:
    """Driver and parser values (Decimal, datetime, UUID, bytes, ...) -> JSON-safe values."""
    if value is None or isinstance(value, str | bool | int):
        return value
    if isinstance(value, float):
        return value if value == value and value not in (float("inf"), float("-inf")) else None
    if isinstance(value, dict):
        return {str(k): jsonable(v) for k, v in value.items()}
    if isinstance(value, list | tuple | set):
        return [jsonable(v) for v in value]
    if isinstance(value, decimal.Decimal):
        return (
            int(value)
            if value == value.to_integral_value() and abs(value) < 2**53
            else float(value)
        )
    if isinstance(value, _dt.datetime | _dt.date | _dt.time):
        return value.isoformat()
    if isinstance(value, _dt.timedelta):
        return value.total_seconds()
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, bytes | bytearray | memoryview):
        return f"<{len(bytes(value))} bytes>"
    return str(value)


def mask_rows(
    guardrails: Any,
    rows: list[dict[str, Any]],
    apply: bool,
    column_kinds: dict[str, str] | None = None,
) -> tuple[list[dict[str, Any]], int]:
    """Column-aware masking of ``rows``; returns ``(masked rows, rows changed)``.

    Columns are classified once from ``rows`` unless ``column_kinds`` is given. Falls
    back to per-value text masking for a custom guardrails engine that has no
    ``mask_records``.
    """
    if not apply or not rows:
        return list(rows), 0
    if hasattr(guardrails, "mask_records"):
        masked = guardrails.mask_records(rows, column_kinds=column_kinds)
    else:  # pragma: no cover - third-party engines
        masked = [
            {k: guardrails.mask_pii(v) if isinstance(v, str) else v for k, v in row.items()}
            for row in rows
        ]
    changed = sum(1 for before, after in zip(rows, masked, strict=True) if before != after)
    return masked, changed


BODY_KEYS = ("content_md", "content", "text", "body", "description")
TITLE_KEYS = ("title", "name", "header")


def rows_to_markdown(
    name: str,
    rows: list[dict[str, Any]],
    kind: str = "Table",
    *,
    body_keys: tuple[str, ...] = BODY_KEYS,
    title_keys: tuple[str, ...] = TITLE_KEYS,
) -> str:
    """A table or collection as readable Markdown.

    Article-like rows (with a body column such as ``content`` or ``text``) become a
    ``# title`` section with a ``**key:** value`` facts line and the body as prose;
    other rows become ``- key: value | ...`` bullets. ``None`` values are left out.
    """
    sections = []
    for r in rows:
        content = next((r[k] for k in body_keys if r.get(k)), "")
        if content:
            title = next((r[k] for k in title_keys if r.get(k)), "")
            meta = " | ".join(
                f"**{k}:** {v}"
                for k, v in r.items()
                if k not in body_keys + title_keys and v is not None
            )
            sections.append(f"# {title}\n" + (f"{meta}\n\n" if meta else "") + f"{content}\n")
        else:
            sections.append("- " + " | ".join(f"{k}: {v}" for k, v in r.items() if v is not None))
    return f"## {kind}: {name}\n\n" + ("\n\n---\n\n".join(sections) or "_No rows._")


_EPOCH = _dt.datetime(1970, 1, 1, tzinfo=_dt.UTC)
_DATABRICKS_INTS = {"BYTE", "SHORT", "INT", "LONG", "TINYINT", "SMALLINT", "INTEGER", "BIGINT"}


def _bigquery(column: dict[str, Any], raw: Any) -> Any:
    if column.get("mode") == "REPEATED":
        item = {**column, "mode": "NULLABLE"}
        return [
            coerce_value("bigquery", item, x.get("v") if isinstance(x, dict) else x)
            for x in raw or []
        ]
    kind = (column.get("type") or "STRING").upper()
    if kind in ("RECORD", "STRUCT"):
        fields = column.get("fields") or []
        cells = (raw or {}).get("f") or []
        return {
            f["name"]: coerce_value("bigquery", f, c.get("v") if isinstance(c, dict) else None)
            for f, c in zip(fields, cells, strict=False)
        }
    if kind in ("INTEGER", "INT64"):
        return int(raw)
    if kind in ("FLOAT", "FLOAT64"):
        return float(raw)
    if kind in ("BOOLEAN", "BOOL"):
        return str(raw).lower() == "true"
    if kind == "TIMESTAMP":  # seconds since the epoch, as a string
        return _dt.datetime.fromtimestamp(float(raw), tz=_dt.UTC).isoformat()
    if kind == "BYTES":
        return f"<{len(base64.b64decode(raw))} bytes>"
    if kind == "JSON":
        try:
            return json.loads(raw)
        except (TypeError, ValueError):
            return raw
    return raw  # STRING, NUMERIC, BIGNUMERIC, DATE, TIME, DATETIME, GEOGRAPHY: as formatted


def _snowflake(column: dict[str, Any], raw: Any) -> Any:
    kind = (column.get("type") or "text").lower()
    try:
        if kind == "fixed":
            return int(raw) if int(column.get("scale") or 0) == 0 else float(raw)
        if kind == "real":
            return float(raw)
        if kind == "boolean":
            return str(raw).lower() == "true"
        if kind == "date":  # days since the epoch
            return (_dt.date(1970, 1, 1) + _dt.timedelta(days=int(raw))).isoformat()
        if kind == "time":  # seconds since midnight
            return (_dt.datetime.min + _dt.timedelta(seconds=float(raw))).time().isoformat()
        if kind in ("timestamp_ntz", "timestamp_ltz", "timestamp_tz"):  # epoch seconds [offset]
            return (_EPOCH + _dt.timedelta(seconds=float(str(raw).split()[0]))).isoformat()
        if kind in ("variant", "object", "array"):
            return json.loads(raw)
        if kind == "binary":  # hex
            return f"<{len(raw) // 2} bytes>"
    except (TypeError, ValueError):
        return raw
    return raw


def _databricks(column: dict[str, Any], raw: Any) -> Any:
    kind = str(column.get("type_name") or "STRING").upper()
    try:
        if kind in _DATABRICKS_INTS:
            return int(raw)
        if kind in ("FLOAT", "DOUBLE", "DECIMAL"):
            return float(raw)
        if kind == "BOOLEAN":
            return str(raw).lower() == "true"
        if kind in ("STRUCT", "ARRAY", "MAP"):
            return json.loads(raw)
        if kind == "BINARY":
            return "<binary>"
    except (TypeError, ValueError):
        return raw
    return raw


_COERCERS = {"bigquery": _bigquery, "snowflake": _snowflake, "databricks": _databricks}


def coerce_value(dialect: Dialect, column: dict[str, Any], raw: Any) -> Any:
    """A warehouse API wire value as a typed Python value, by the column's declared type.

    - ``bigquery``: ``column`` is a schema field (``type``, ``mode``, ``fields``); ``raw``
      is the ``v`` of a ``{"f": [{"v": ...}]}`` cell. INT64/FLOAT64/BOOL are typed,
      TIMESTAMP (epoch seconds) becomes ISO 8601, BYTES ``<N bytes>``, JSON parsed,
      RECORD/STRUCT and REPEATED recursively.
    - ``snowflake``: SQL API ``rowType`` entries (``type``, ``scale``); FIXED/REAL/BOOLEAN
      typed, DATE (epoch days), TIME and TIMESTAMP_* (epoch seconds) to ISO 8601,
      VARIANT/OBJECT/ARRAY parsed, BINARY (hex) ``<N bytes>``.
    - ``databricks``: Statement API columns (``type_name``); integers, floats, booleans,
      STRUCT/ARRAY/MAP parsed, BINARY ``<binary>``.

    ``None`` stays ``None``; a value that does not parse is returned unchanged.
    """
    if raw is None:
        return None
    try:
        coerce = _COERCERS[dialect]
    except KeyError:
        raise ValueError(f"unknown dialect {dialect!r}") from None
    return coerce(column, raw)


def rows_from_columns(
    dialect: Dialect, columns: list[dict[str, Any]], data: list[Any]
) -> list[dict[str, Any]]:
    """Typed row dicts from a warehouse result: ``columns`` (schema) and ``data`` (rows).

    BigQuery rows are ``{"f": [{"v": ...}, ...]}`` objects; Snowflake and Databricks rows
    are lists of strings in column order.
    """
    if dialect == "bigquery":
        out = []
        for row in data:
            cells = (row or {}).get("f") or []
            out.append(
                {
                    f["name"]: coerce_value(
                        "bigquery", f, c.get("v") if isinstance(c, dict) else None
                    )
                    for f, c in zip(columns, cells, strict=False)
                }
            )
        return out
    return [
        {c["name"]: coerce_value(dialect, c, v) for c, v in zip(columns, row, strict=False)}
        for row in data
    ]


def flatten_record(
    record: dict[str, Any],
    *,
    sep: str = ".",
    skip: tuple[str, ...] = ("attributes",),
    max_value_chars: int | None = None,
    prefix: str = "",
) -> dict[str, Any]:
    """Nested objects as dotted keys (``Account.Name``); ``skip`` keys (Salesforce
    ``attributes``) are left out; strings over ``max_value_chars`` are cut with "…"."""
    out: dict[str, Any] = {}
    for key, value in record.items():
        if key in skip:
            continue
        if isinstance(value, dict):
            out.update(
                flatten_record(
                    value,
                    sep=sep,
                    skip=skip,
                    max_value_chars=max_value_chars,
                    prefix=f"{prefix}{key}{sep}",
                )
            )
        elif (
            isinstance(value, str) and max_value_chars is not None and len(value) > max_value_chars
        ):
            out[f"{prefix}{key}"] = value[:max_value_chars] + "…"
        else:
            out[f"{prefix}{key}"] = value
    return out


def row_hash(record: Mapping[str, Any], *, exclude: Iterable[str] = ()) -> str:
    """A 40-character hex digest of a record's content (keys sorted, ``exclude`` keys left
    out): equal for equal rows whatever their key order, so a re-read table can tell changed,
    new and vanished rows apart without comparing them field by field."""
    skip = set(exclude)
    body = {str(k): v for k, v in record.items() if k not in skip}
    text = json.dumps(body, sort_keys=True, ensure_ascii=False, separators=(",", ":"), default=str)
    return hashlib.sha1(text.encode("utf-8"), usedforsecurity=False).hexdigest()


FREE_TEXT_CHARS = 40  # a text column whose typical value is this long is prose, not a code


def _median_length(rows: list[Mapping[str, Any]], path: tuple[str, ...]) -> float | None:
    lengths = []
    for row in rows:
        value: Any = row
        for key in path:
            value = value.get(key) if isinstance(value, Mapping) else None
        if isinstance(value, str) and value.strip():
            lengths.append(len(value))
    if not lengths:
        return None
    lengths.sort()
    return float(lengths[len(lengths) // 2])


def embed_policy(
    profile: Mapping[str, Any],
    rows: Iterable[Mapping[str, Any]] | None = None,
    *,
    min_text_chars: int = FREE_TEXT_CHARS,
    sample: int = 2000,
) -> dict[str, Any]:
    """Which rows of a table need an embedding vector.

    A table whose columns are numbers, dates, booleans, categories (every value listed in the
    profile) and short codes is answered exactly from its records and keyword search; only
    rows carrying free text need vectors for meaning-based search. A text column is free text
    when its values are not a small known set and (from ``rows``, at most ``sample`` of them)
    its median value has at least ``min_text_chars`` characters; without rows every such
    column counts as free text (any doubt: embed). Returns ``{"embed": "all" | "none" |
    "rows_with_text", "text_columns": [paths], "reason"}``; ``needs_vector`` applies it."""
    sampled = []
    for row in rows or ():
        if len(sampled) >= sample:
            break
        if isinstance(row, Mapping):
            sampled.append(row)
    free, unsure = [], False
    for column in profile.get("columns") or []:
        if column.get("type") not in ("text", "mixed") or column.get("values_complete"):
            continue
        path = tuple(str(p) for p in column.get("path") or [column["name"]])
        if not sampled:
            free.append(list(path))
            unsure = True
            continue
        median = _median_length(sampled, path)
        if median is not None and median >= min_text_chars:
            free.append(list(path))
    if not free:
        return {"embed": "none", "text_columns": [], "reason": "no free-text column"}
    if unsure:
        return {"embed": "all", "text_columns": free, "reason": "text columns, no sample rows"}
    return {"embed": "rows_with_text", "text_columns": free, "reason": "free-text columns"}


def needs_vector(record: Mapping[str, Any], policy: Mapping[str, Any]) -> bool:
    """Whether ``record`` needs an embedding under ``embed_policy``'s ``policy``: every row for
    ``"all"``, none for ``"none"``, else rows with a non-blank value in a free-text column."""
    mode = policy.get("embed", "all")
    if mode == "none":
        return False
    if mode != "rows_with_text":
        return True
    for path in policy.get("text_columns") or []:
        value: Any = record
        for key in path:
            value = value.get(key) if isinstance(value, Mapping) else None
        if isinstance(value, str) and value.strip():
            return True
    return False
