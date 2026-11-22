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

"""PostgreSQL change data capture through logical replication (``pgoutput``).

``pgoutput`` is the logical decoding plugin built into PostgreSQL 10+, so change
capture needs no extension on the database (unlike wal2json). This module has two parts:

``PgOutputDecoder`` (pure Python, no dependencies)
    Decodes the binary protocol ("Logical Replication Message Formats"): Begin, Commit,
    Origin, Relation, Type, Insert, Update, Delete, Truncate and Message. Relation
    messages carry the current column list and replica-identity key columns, so schema
    changes are picked up as they happen. Rows become :class:`ChangeEvent` objects (the
    same type the other CDC formats produce), keyed by the table's replica-identity key.
    Values arrive in PostgreSQL text format and are converted by column type (integers,
    ``numeric`` to exact ``Decimal``, booleans, dates and timestamps to ISO strings, JSON).
    Unchanged TOASTed
    values (large columns an UPDATE did not touch) are omitted and the event is marked
    ``partial`` so consumers merge it with the stored record.

``PostgresLogicalStream`` (requires ``psycopg2``, the ``[postgres]`` extra)
    A consumer over a replication slot with an at-least-once contract:

    * ``prerequisites()`` checks ``wal_level``, the publication and the role, and returns
      actionable problems instead of failing mid-stream
    * ``ensure_slot()`` creates the slot once; ``slot_info()`` reports lag and
      ``wal_status`` (a ``lost`` slot means the consumer must re-snapshot)
    * ``transactions()`` yields committed transactions; nothing is confirmed until the
      caller calls ``confirm(lsn)`` after durably applying them, so a crash replays
      instead of losing changes
    * on a quiet database, idle periods confirm the server's WAL position when nothing
      is pending, so the slot does not hold back WAL (the classic disk-fill risk)
    * ``drop_slot()`` for when a consumer is removed

Security notes: the role needs the ``REPLICATION`` attribute and ``SELECT`` on the
published tables, not superuser. The publication should be created by the database
owner and can use column lists / row filters (PostgreSQL 15+) to exclude data the
consumer must not see. Connect with TLS (``sslmode=verify-full``) in production, and
set ``max_slot_wal_keep_size`` on the server to cap WAL retained by an abandoned slot.
"""

from __future__ import annotations

import re
import select
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any

from .cdc import ChangeEvent, _derive_key  # noqa: F401 (re-export)
from .pgoutput_decode import (  # noqa: F401 (re-export)
    _CONVERTERS,
    PG_EPOCH,
    Column,
    PgOutputDecoder,
    PgOutputError,
    PgTransaction,
    Relation,
    _date,
    _json,
    _numeric,
    _Reader,
    _timestamp,
    _ts,
    convert_value,
    lsn_to_str,
    str_to_lsn,
)

_SLOT_NAME = re.compile(r"^[a-z0-9_]{1,63}$")


# ---------------------------------------------------------------------------
# Stream client (psycopg2)
# ---------------------------------------------------------------------------


# Session settings that make text output deterministic: ISO dates, UTC timestamps,
# ISO-8601 intervals and round-trip-exact floats. Use them for snapshot reads too.
SESSION_OPTIONS = (
    "-c DateStyle=ISO,MDY -c IntervalStyle=iso_8601 -c TimeZone=UTC -c extra_float_digits=3"
)


@dataclass
class SlotInfo:
    exists: bool
    active: bool = False
    active_pid: int | None = None
    confirmed_flush_lsn: str | None = None
    wal_status: str | None = None  # reserved | extended | unreserved | lost (PostgreSQL 13+)
    invalidation_reason: str | None = None  # PostgreSQL 17+
    conflicting: bool = False  # PostgreSQL 16+
    lag_bytes: int | None = None

    @property
    def lost(self) -> bool:
        """The slot can no longer deliver every change: the consumer must re-snapshot."""
        return self.wal_status == "lost" or bool(self.invalidation_reason) or self.conflicting


@dataclass
class PublishedTable:
    schema: str
    table: str
    columns: list[str] | None = None  # publication column list (PostgreSQL 15+), None = all
    row_filter: str | None = None  # publication row filter (PostgreSQL 15+)

    @property
    def qualified_name(self) -> str:
        return f"{self.schema}.{self.table}"


class PostgresLogicalStream:
    """At-least-once consumer of a ``pgoutput`` replication slot.

    ``dsn`` is a libpq connection string or URL. Nothing is confirmed to the server
    until :meth:`confirm` is called, so callers acknowledge only what they have
    durably applied. Typical first start with an exact initial copy::

        stream = PostgresLogicalStream(dsn, "my_slot", "my_pub")
        start_lsn, snapshot = stream.create_slot_with_snapshot()
        with stream.snapshot_session(snapshot) as cur:     # consistent with start_lsn
            for table in stream.published_tables():
                for rows in stream.iter_table(cur, table):
                    upsert(rows)
        for txn in stream.transactions(start_lsn=start_lsn):
            ...
    """

    def __init__(
        self,
        dsn: str,
        slot_name: str,
        publication: str,
        *,
        proto_version: int = 1,
        status_interval: float = 10.0,
    ) -> None:
        if not _SLOT_NAME.match(slot_name):
            raise ValueError("slot_name must be 1-63 characters of a-z, 0-9 and _")
        if not re.match(r"^[A-Za-z_][A-Za-z0-9_]{0,62}$", publication):
            raise ValueError("publication must be a plain PostgreSQL identifier")
        self.dsn, self.slot_name, self.publication = dsn, slot_name, publication
        self.proto_version, self.status_interval = proto_version, status_interval
        self._conn: Any = None
        self._cur: Any = None
        self._streaming = False
        self._pending = 0  # transactions handed out but not yet confirmed
        self._last_feedback = 0.0
        self._server_version: int | None = None
        self.decoder = PgOutputDecoder()

    # -- connections --------------------------------------------------------------------
    def _connect(self, replication: bool = False) -> Any:
        import psycopg2
        from psycopg2.extras import LogicalReplicationConnection

        kwargs: dict[str, Any] = {"options": SESSION_OPTIONS, "application_name": "nexus-cdc"}
        if replication:
            kwargs["connection_factory"] = LogicalReplicationConnection
        return psycopg2.connect(self.dsn, **kwargs)

    def _query(self, sql: str, params: tuple = ()) -> list[tuple]:
        conn = self._connect()
        try:
            with conn.cursor() as cur:
                cur.execute(sql, params)
                return cur.fetchall() if cur.description else []
        finally:
            conn.close()

    @property
    def server_version(self) -> int:
        if self._server_version is None:
            ((self._server_version,),) = self._query(
                "SELECT current_setting('server_version_num')::int"
            )
        return self._server_version

    # -- checks & metadata -------------------------------------------------------------
    def prerequisites(self) -> list[str]:
        """Problems that prevent streaming, each phrased as the fix a DBA should apply."""
        problems = []
        ((wal_level,),) = self._query("SHOW wal_level")
        if wal_level != "logical":
            problems.append(
                f"wal_level is '{wal_level}': set wal_level=logical and restart PostgreSQL "
                "(RDS/Aurora: rds.logical_replication=1; Cloud SQL: cloudsql.logical_decoding=on)"
            )
        ((can_replicate,),) = self._query(
            "SELECT rolreplication OR rolsuper FROM pg_roles WHERE rolname = current_user"
        )
        if not can_replicate:
            problems.append(
                "the connecting role needs the REPLICATION attribute: "
                "ALTER ROLE <user> REPLICATION (RDS/Aurora: GRANT rds_replication TO <user>)"
            )
        if not self._query("SELECT 1 FROM pg_publication WHERE pubname = %s", (self.publication,)):
            problems.append(
                f"publication '{self.publication}' does not exist: CREATE PUBLICATION "
                f"{self.publication} FOR TABLE <tables> (run by the tables' owner)"
            )
        else:
            no_identity = self._query(
                """SELECT pt.schemaname || '.' || pt.tablename
                   FROM pg_publication_tables pt
                   JOIN pg_namespace n ON n.nspname = pt.schemaname
                   JOIN pg_class c ON c.relname = pt.tablename AND c.relnamespace = n.oid
                   WHERE pt.pubname = %s AND c.relreplident IN ('d', 'n')
                     AND (c.relreplident = 'n' OR NOT EXISTS (
                          SELECT 1 FROM pg_index i WHERE i.indrelid = c.oid AND i.indisprimary))""",
                (self.publication,),
            )
            if no_identity:
                names = ", ".join(r[0] for r in no_identity)
                problems.append(
                    "tables without a replica identity make UPDATE/DELETE fail on the source "
                    f"once published: {names} "
                    "(add a primary key or ALTER TABLE ... REPLICA IDENTITY FULL)"
                )
        return problems

    def identify_system(self) -> str:
        """The cluster's system identifier (changes on a restored or different cluster)."""
        conn = self._connect(replication=True)
        try:
            cur = conn.cursor()
            cur.execute("IDENTIFY_SYSTEM")
            return str(cur.fetchone()[0])
        finally:
            conn.close()

    def published_tables(self) -> list[PublishedTable]:
        """Tables in the publication with their column lists and row filters (data minimization)."""
        if self.server_version >= 150000:
            rows = self._query(
                "SELECT schemaname, tablename, attnames::text[], rowfilter "
                "FROM pg_publication_tables WHERE pubname = %s ORDER BY 1, 2",
                (self.publication,),
            )
            return [PublishedTable(s, t, list(cols) if cols else None, f) for s, t, cols, f in rows]
        rows = self._query(
            "SELECT schemaname, tablename FROM pg_publication_tables "
            "WHERE pubname = %s ORDER BY 1, 2",
            (self.publication,),
        )
        return [PublishedTable(s, t) for s, t in rows]

    def primary_key(self, schema: str, table: str) -> list[str]:
        rows = self._query(
            """SELECT a.attname FROM pg_index i
               JOIN pg_attribute a ON a.attrelid = i.indrelid AND a.attnum = ANY(i.indkey)
               WHERE i.indrelid = (quote_ident(%s) || '.' || quote_ident(%s))::regclass
                 AND i.indisprimary
               ORDER BY array_position(i.indkey::int2[], a.attnum)""",
            (schema, table),
        )
        return [r[0] for r in rows]

    def slot_info(self) -> SlotInfo:
        version = self.server_version
        cols = [
            "active",
            "active_pid",
            "confirmed_flush_lsn::text",
            "wal_status" if version >= 130000 else "NULL::text",
            "invalidation_reason" if version >= 170000 else "NULL::text",
            "conflicting" if version >= 160000 else "false",
            "pg_wal_lsn_diff(pg_current_wal_lsn(), confirmed_flush_lsn)::bigint",
        ]
        rows = self._query(
            f"SELECT {', '.join(cols)} FROM pg_replication_slots "
            "WHERE slot_name = %s AND plugin = 'pgoutput' AND database = current_database()",
            (self.slot_name,),
        )
        if not rows:
            return SlotInfo(exists=False)
        active, pid, confirmed, wal_status, reason, conflicting, lag = rows[0]
        return SlotInfo(
            True,
            bool(active),
            pid,
            confirmed,
            wal_status,
            reason,
            bool(conflicting),
            int(lag) if lag is not None else None,
        )

    # -- slot lifecycle ----------------------------------------------------------------
    def create_slot_with_snapshot(self, failover: bool = False) -> tuple[int, str]:
        """Create the slot and export a snapshot consistent with its start position.

        Returns ``(start_lsn, snapshot_name)``. The snapshot stays importable until the
        stream starts (:meth:`transactions`) or :meth:`close` is called, so copy the
        tables inside :meth:`snapshot_session` first.
        """
        if self._streaming:
            raise RuntimeError("the stream is already running")
        opts = ["SNAPSHOT 'export'"]
        if failover and self.server_version >= 170000:
            opts.append("FAILOVER true")
        if self.server_version >= 150000:
            command = (
                f'CREATE_REPLICATION_SLOT "{self.slot_name}" LOGICAL pgoutput ({", ".join(opts)})'
            )
        else:
            command = f'CREATE_REPLICATION_SLOT "{self.slot_name}" LOGICAL pgoutput EXPORT_SNAPSHOT'
        self._conn = self._connect(replication=True)
        self._cur = self._conn.cursor()
        self._cur.execute(command)
        _slot, consistent_point, snapshot_name, _plugin = self._cur.fetchone()
        return str_to_lsn(consistent_point), snapshot_name

    @contextmanager
    def snapshot_session(self, snapshot_name: str) -> Iterator[Any]:
        """A read-only REPEATABLE READ cursor that sees exactly the exported snapshot."""
        if not re.match(r"^[0-9A-Fa-f-]+$", snapshot_name):
            raise ValueError("unexpected snapshot name")
        conn = self._connect()
        try:
            conn.set_session(isolation_level="REPEATABLE READ", readonly=True)
            with conn.cursor() as cur:
                cur.execute("SET TRANSACTION SNAPSHOT %s", (snapshot_name,))
                yield cur
            conn.rollback()
        finally:
            conn.close()

    def iter_table(
        self, cursor: Any, table: PublishedTable, *, batch_size: int = 500, limit: int | None = None
    ) -> Iterator[list[dict[str, Any]]]:
        """Read a published table in batches, honouring its publication column list and row
        filter, so the initial copy contains exactly what the stream will send."""
        from psycopg2 import sql

        columns = (
            sql.SQL(", ").join(sql.Identifier(c) for c in table.columns)
            if table.columns
            else sql.SQL("*")
        )
        query = sql.SQL("SELECT {} FROM {}.{}").format(
            columns, sql.Identifier(table.schema), sql.Identifier(table.table)
        )
        if table.row_filter:  # text of the publication's WHERE clause, from the catalog
            query = query + sql.SQL(" WHERE ") + sql.SQL(table.row_filter)
        if limit:
            query = query + sql.SQL(" LIMIT {}").format(sql.Literal(int(limit)))
        cursor.execute(query)
        names = [d[0] for d in cursor.description]
        while rows := cursor.fetchmany(batch_size):
            yield [dict(zip(names, row, strict=True)) for row in rows]

    def ensure_slot(self) -> bool:
        """Create the logical slot without a snapshot if missing. True when created now."""
        if self.slot_info().exists:
            return False
        from psycopg2.extras import REPLICATION_LOGICAL

        conn = self._connect(replication=True)
        try:
            conn.cursor().create_replication_slot(
                self.slot_name, slot_type=REPLICATION_LOGICAL, output_plugin="pgoutput"
            )
        finally:
            conn.close()
        return True

    def drop_slot(self) -> bool:
        """Drop the slot (releases retained WAL). Returns False when it did not exist."""
        if not self.slot_info().exists:
            return False
        self._query("SELECT pg_drop_replication_slot(%s)", (self.slot_name,))
        return True

    # -- streaming --------------------------------------------------------------------
    def _open(self, start_lsn: int) -> None:
        if self._conn is None:  # reuse the connection that created the slot, if any
            self._conn = self._connect(replication=True)
            self._cur = self._conn.cursor()
        self._cur.start_replication(
            slot_name=self.slot_name,
            decode=False,
            start_lsn=start_lsn,
            status_interval=self.status_interval,
            options={
                "proto_version": str(self.proto_version),
                "publication_names": self.publication,
            },
        )
        self._streaming = True
        self.decoder = PgOutputDecoder()  # relations are re-sent on every new session

    def transactions(
        self, idle_timeout: float = 1.0, start_lsn: int = 0
    ) -> Iterator[PgTransaction | None]:
        """Yield committed transactions in order; yields ``None`` after ``idle_timeout``
        seconds without one, so the caller can flush batches and check for shutdown.
        The server resumes from the slot's confirmed position (or ``start_lsn`` if later)."""
        if not self._streaming:
            self._open(start_lsn)
        while True:
            message = self._cur.read_message()
            if message is not None:
                txn = self.decoder.feed(message.payload)
                if txn is not None:
                    self._pending += 1
                    yield txn
                continue
            self._keepalive()
            ready = select.select([self._cur], [], [], idle_timeout)[0]
            if not ready:
                yield None

    def confirm(self, lsn: int) -> None:
        """Acknowledge everything up to ``lsn`` as durably applied (lets the server free WAL).
        Pass the ``end_lsn`` of the last applied transaction, never a row position."""
        self._pending = 0
        self._cur.send_feedback(write_lsn=lsn, flush_lsn=lsn, apply_lsn=lsn, force=True)
        self._last_feedback = time.monotonic()

    def _keepalive(self) -> None:
        if time.monotonic() - self._last_feedback < self.status_interval:
            return
        if self._pending == 0 and getattr(self._cur, "wal_end", 0):
            # Nothing handed out is unconfirmed: everything before the server's current WAL
            # position is either applied or irrelevant to this publication.
            wal_end = self._cur.wal_end
            self._cur.send_feedback(write_lsn=wal_end, flush_lsn=wal_end, apply_lsn=wal_end)
        else:
            self._cur.send_feedback()
        self._last_feedback = time.monotonic()

    def close(self) -> None:
        for resource in (self._cur, self._conn):
            try:
                if resource is not None:
                    resource.close()
            except Exception:
                pass
        self._cur = self._conn = None
        self._streaming = False
