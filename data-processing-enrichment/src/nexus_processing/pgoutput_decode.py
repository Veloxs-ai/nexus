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

"""The ``pgoutput`` binary protocol decoder (pure Python) and value conversion by type OID."""

from __future__ import annotations

import json
import struct
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any

from .cdc import ChangeEvent, _derive_key

PG_EPOCH = datetime(2000, 1, 1, tzinfo=UTC)


class PgOutputError(ValueError):
    """A message could not be decoded (corrupt input or an unsupported protocol feature)."""


def _ts(text: str) -> str:
    try:
        return datetime.fromisoformat(text).isoformat()
    except ValueError:
        return text  # infinity, BC dates, unusual formats: keep the database text


def _date(text: str) -> str:
    try:
        return date.fromisoformat(text).isoformat()
    except ValueError:
        return text


def _numeric(text: str) -> Decimal | str:
    try:
        return Decimal(text)  # exact: money must never pass through float here
    except (InvalidOperation, ValueError):
        return text


def _json(text: str) -> Any:
    try:
        return json.loads(text)
    except ValueError:
        return text


_CONVERTERS: dict[int, Callable[[str], Any]] = {
    16: lambda t: t == "t",  # bool
    20: int,
    21: int,
    23: int,
    26: int,  # int8, int2, int4, oid
    700: float,
    701: float,  # float4, float8
    1700: _numeric,  # numeric
    1082: _date,  # date
    1114: _ts,
    1184: _ts,  # timestamp, timestamptz
    114: _json,
    3802: _json,  # json, jsonb
}


def convert_value(type_oid: int, text: str) -> Any:
    """Convert one text-format value by type OID; unknown types stay as text."""
    converter = _CONVERTERS.get(type_oid)
    if converter is None:
        return text
    try:
        return converter(text)
    except ValueError:
        return text


def lsn_to_str(lsn: int) -> str:
    return f"{lsn >> 32:X}/{lsn & 0xFFFFFFFF:X}"


def str_to_lsn(text: str) -> int:
    high, low = text.split("/")
    return (int(high, 16) << 32) | int(low, 16)


@dataclass
class Column:
    name: str
    type_oid: int
    is_key: bool


@dataclass
class Relation:
    relation_id: int
    namespace: str
    name: str
    replica_identity: str  # d(efault) | n(othing) | f(ull) | i(ndex)
    columns: list[Column]

    @property
    def qualified_name(self) -> str:
        return f"{self.namespace}.{self.name}"


@dataclass
class PgTransaction:
    xid: int
    final_lsn: int
    commit_lsn: int = 0
    end_lsn: int = 0
    committed_at: datetime | None = None
    events: list[ChangeEvent] = field(default_factory=list)


class _Reader:
    __slots__ = ("buf", "pos")

    def __init__(self, buf: bytes) -> None:
        self.buf, self.pos = buf, 0

    def take(self, n: int) -> bytes:
        if self.pos + n > len(self.buf):
            raise PgOutputError("message truncated")
        chunk = self.buf[self.pos : self.pos + n]
        self.pos += n
        return chunk

    def byte(self) -> str:
        return self.take(1).decode("ascii")

    def int8(self) -> int:
        return struct.unpack("!b", self.take(1))[0]

    def int16(self) -> int:
        return struct.unpack("!h", self.take(2))[0]

    def int32(self) -> int:
        return struct.unpack("!i", self.take(4))[0]

    def uint32(self) -> int:
        return struct.unpack("!I", self.take(4))[0]

    def int64(self) -> int:
        return struct.unpack("!q", self.take(8))[0]

    def string(self) -> str:
        end = self.buf.find(b"\x00", self.pos)
        if end < 0:
            raise PgOutputError("unterminated string in message")
        text = self.buf[self.pos : end].decode("utf-8")
        self.pos = end + 1
        return text


def _timestamp(micros: int) -> datetime:
    return PG_EPOCH + timedelta(microseconds=micros)


class PgOutputDecoder:
    """Stateful decoder for one replication connection.

    Feed every ``pgoutput`` payload in order with :meth:`feed`; it returns a
    :class:`PgTransaction` when a Commit completes one, otherwise ``None``.
    """

    def __init__(self, database: str = "") -> None:
        self.database = database
        self.relations: dict[int, Relation] = {}
        self.current: PgTransaction | None = None

    # -- tuples ------------------------------------------------------------------
    def _tuple(self, reader: _Reader, relation: Relation) -> tuple[dict[str, Any], list[str]]:
        count = reader.int16()
        if count != len(relation.columns):
            raise PgOutputError(
                f"{relation.qualified_name}: tuple has {count} columns, relation has "
                f"{len(relation.columns)} (missing Relation message?)"
            )
        values: dict[str, Any] = {}
        unchanged: list[str] = []
        for column in relation.columns:
            kind = reader.byte()
            if kind == "n":
                values[column.name] = None
            elif kind == "u":
                unchanged.append(column.name)
            elif kind == "t":
                text = reader.take(reader.int32()).decode("utf-8")
                values[column.name] = convert_value(column.type_oid, text)
            elif kind == "b":
                raise PgOutputError("binary tuple data is not supported; do not set binary=true")
            else:
                raise PgOutputError(f"unknown tuple column kind {kind!r}")
        return values, unchanged

    def _event(
        self,
        relation: Relation,
        operation: str,
        record: dict[str, Any],
        key_source: dict[str, Any],
        partial: bool = False,
    ) -> ChangeEvent:
        key_columns = [c.name for c in relation.columns if c.is_key]
        explicit = {c: key_source.get(c) for c in key_columns} if key_columns else None
        committed = self.current.committed_at if self.current else None
        return ChangeEvent(
            operation=operation,
            source_format="pgoutput",
            database=relation.namespace,
            table=relation.name,
            key=_derive_key(record, explicit),
            record=record,
            partial=partial,
            timestamp_ms=int(committed.timestamp() * 1000) if committed else 0,
        )

    def _relation(self, relation_id: int) -> Relation:
        relation = self.relations.get(relation_id)
        if relation is None:
            raise PgOutputError(
                f"change for unknown relation {relation_id} (Relation message not seen)"
            )
        return relation

    # -- messages ------------------------------------------------------------------
    def feed(self, payload: bytes) -> PgTransaction | None:
        reader = _Reader(bytes(payload))
        tag = reader.byte()

        if tag == "B":
            final_lsn, commit_ts, xid = reader.int64(), reader.int64(), reader.uint32()
            self.current = PgTransaction(
                xid=xid, final_lsn=final_lsn, committed_at=_timestamp(commit_ts)
            )
            return None
        if tag == "C":
            reader.int8()  # flags (unused)
            commit_lsn, end_lsn, commit_ts = reader.int64(), reader.int64(), reader.int64()
            txn = self.current or PgTransaction(xid=0, final_lsn=commit_lsn)
            txn.commit_lsn, txn.end_lsn, txn.committed_at = (
                commit_lsn,
                end_lsn,
                _timestamp(commit_ts),
            )
            self.current = None
            return txn
        if tag == "R":
            relation_id = reader.uint32()
            namespace, name = reader.string(), reader.string()
            identity = chr(reader.int8() & 0xFF)
            columns = []
            for _ in range(reader.int16()):
                flags = reader.int8()
                col_name = reader.string()
                type_oid = reader.uint32()
                reader.int32()  # type modifier
                columns.append(Column(col_name, type_oid, bool(flags & 1)))
            self.relations[relation_id] = Relation(
                relation_id, namespace or "public", name, identity, columns
            )
            return None
        if tag in ("O", "Y", "M"):
            return None  # origin, type and logical messages carry nothing we store
        if tag == "I":
            relation = self._relation(reader.uint32())
            if reader.byte() != "N":
                raise PgOutputError("insert without new tuple")
            record, _ = self._tuple(reader, relation)
            self._append(self._event(relation, "INSERT", record, record))
            return None
        if tag == "U":
            relation = self._relation(reader.uint32())
            marker = reader.byte()
            old: dict[str, Any] = {}
            if marker in ("K", "O"):
                old, _ = self._tuple(reader, relation)
                marker = reader.byte()
            if marker != "N":
                raise PgOutputError("update without new tuple")
            record, unchanged = self._tuple(reader, relation)
            # A changed primary key arrives as the old key ('K') plus the new row: delete + insert.
            key_cols = [c.name for c in relation.columns if c.is_key]
            if (
                old
                and key_cols
                and any(old.get(c) != record.get(c) for c in key_cols if old.get(c) is not None)
            ):
                self._append(self._event(relation, "DELETE", old, old))
                self._append(
                    self._event(relation, "INSERT", record, record, partial=bool(unchanged))
                )
            else:
                self._append(
                    self._event(relation, "UPDATE", record, record, partial=bool(unchanged))
                )
            return None
        if tag == "D":
            relation = self._relation(reader.uint32())
            if reader.byte() not in ("K", "O"):
                raise PgOutputError("delete without old key or old row")
            old, _ = self._tuple(reader, relation)
            self._append(
                self._event(
                    relation, "DELETE", {k: v for k, v in old.items() if v is not None}, old
                )
            )
            return None
        if tag == "T":
            count = reader.int32()
            reader.int8()  # options: cascade / restart identity
            for _ in range(count):
                relation = self._relation(reader.uint32())
                self._append(
                    ChangeEvent("TRUNCATE", "pgoutput", relation.namespace, relation.name, key="*")
                )
            return None
        if tag in ("S", "E", "c", "A"):
            raise PgOutputError(
                "streamed in-progress transactions are not supported; do not set streaming=on"
            )
        raise PgOutputError(f"unknown pgoutput message type {tag!r}")

    def _append(self, event: ChangeEvent) -> None:
        if self.current is None:  # DML outside Begin/Commit should not happen; keep it anyway
            self.current = PgTransaction(xid=0, final_lsn=0)
        self.current.events.append(event)
