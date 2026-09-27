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

"""pgoutput decoding, built byte-for-byte from the documented message formats."""

import struct
from datetime import UTC, datetime

import pytest

try:
    from nexus.processing import cdc, pgoutput
except (ImportError, ModuleNotFoundError):
    from nexus_processing import cdc, pgoutput

PG_EPOCH = datetime(2000, 1, 1, tzinfo=UTC)
TS = int((datetime(2026, 9, 27, 13, 0, tzinfo=UTC) - PG_EPOCH).total_seconds() * 1_000_000)


def s(text: str) -> bytes:
    return text.encode() + b"\x00"


def relation(
    rel_id: int, ns: str, name: str, cols: list[tuple[str, int, bool]], identity: bytes = b"d"
) -> bytes:
    body = (
        b"R" + struct.pack("!I", rel_id) + s(ns) + s(name) + identity + struct.pack("!h", len(cols))
    )
    for col, oid, key in cols:
        body += struct.pack("!b", 1 if key else 0) + s(col) + struct.pack("!Ii", oid, -1)
    return body


def tup(values: list) -> bytes:
    out = struct.pack("!h", len(values))
    for v in values:
        if v is None:
            out += b"n"
        elif v == "<unchanged>":
            out += b"u"
        else:
            data = str(v).encode()
            out += b"t" + struct.pack("!i", len(data)) + data
    return out


def begin(xid: int = 700) -> bytes:
    return b"B" + struct.pack("!qqI", 0x16B3748, TS, xid)


def commit(lsn: int = 0x16B3748) -> bytes:
    return b"C" + struct.pack("!bqqq", 0, lsn, lsn + 40, TS)


LOANS = relation(
    16401,
    "core",
    "loan_accounts",
    [
        ("loan_account_no", 1043, True),
        ("dpd", 23, False),
        ("overdue_amount", 1700, False),
        ("restructured_flag", 16, False),
        ("next_due_date", 1082, False),
        ("updated_at", 1184, False),
        ("remarks", 25, False),
        ("meta", 3802, False),
    ],
)


def feed_all(decoder, *messages):
    out = None
    for m in messages:
        out = decoder.feed(m) or out
    return out


def test_insert_converts_types_and_keys_by_primary_key():
    row = [
        "PL42",
        12,
        "12500.50",
        "f",
        "2026-10-05",
        "2026-09-27 18:30:00+05:30",
        None,
        '{"src": "finacle"}',
    ]
    txn = feed_all(
        pgoutput.PgOutputDecoder(),
        LOANS,
        begin(),
        b"I" + struct.pack("!I", 16401) + b"N" + tup(row),
        commit(),
    )
    assert txn.xid == 700 and txn.end_lsn == 0x16B3748 + 40 and txn.committed_at.year == 2026
    (event,) = txn.events
    assert (event.operation, event.source_format, event.database, event.table, event.key) == (
        "INSERT",
        "pgoutput",
        "core",
        "loan_accounts",
        "PL42",
    )
    assert event.record == {
        "loan_account_no": "PL42",
        "dpd": 12,
        "overdue_amount": 12500.5,
        "restructured_flag": False,
        "next_due_date": "2026-10-05",
        "updated_at": "2026-09-27T18:30:00+05:30",
        "remarks": None,
        "meta": {"src": "finacle"},
    }
    assert event.timestamp_ms == int(datetime(2026, 9, 27, 13, 0, tzinfo=UTC).timestamp() * 1000)


def test_update_with_unchanged_toast_is_partial_and_omits_the_column():
    decoder = pgoutput.PgOutputDecoder()
    row = ["PL42", 0, "0", "f", "2026-11-05", "2026-10-05 19:05:00+05:30", "<unchanged>", "{}"]
    txn = feed_all(
        decoder, LOANS, begin(), b"U" + struct.pack("!I", 16401) + b"N" + tup(row), commit()
    )
    (event,) = txn.events
    assert event.operation == "UPDATE" and event.partial and "remarks" not in event.record


def test_primary_key_change_becomes_delete_plus_insert():
    old_key = ["PL42", None, None, None, None, None, None, None]
    new_row = ["PL43", 0, "0", "f", "2026-11-05", "2026-10-05 19:05:00+05:30", None, "{}"]
    txn = feed_all(
        pgoutput.PgOutputDecoder(),
        LOANS,
        begin(),
        b"U" + struct.pack("!I", 16401) + b"K" + tup(old_key) + b"N" + tup(new_row),
        commit(),
    )
    assert [(e.operation, e.key) for e in txn.events] == [("DELETE", "PL42"), ("INSERT", "PL43")]


def test_delete_with_key_only_old_tuple():
    txn = feed_all(
        pgoutput.PgOutputDecoder(),
        LOANS,
        begin(),
        b"D"
        + struct.pack("!I", 16401)
        + b"K"
        + tup(["PL42", None, None, None, None, None, None, None]),
        commit(),
    )
    (event,) = txn.events
    assert (event.operation, event.key, event.record) == (
        "DELETE",
        "PL42",
        {"loan_account_no": "PL42"},
    )
    assert event.is_delete


def test_composite_keys_match_the_snapshot_convention():
    schedule = relation(
        16402,
        "core",
        "emi_schedule",
        [("loan_account_no", 1043, True), ("installment_no", 23, True), ("status", 1043, False)],
    )
    txn = feed_all(
        pgoutput.PgOutputDecoder(),
        schedule,
        begin(),
        b"I" + struct.pack("!I", 16402) + b"N" + tup(["PL42", 7, "PAID"]),
        commit(),
    )
    snapshot = cdc.normalize_change_event(
        {
            "op": "insert",
            "database": "core",
            "table": "emi_schedule",
            "record": {"loan_account_no": "PL42", "installment_no": 7},
            "key": {"loan_account_no": "PL42", "installment_no": 7},
        }
    )
    assert txn.events[0].key == snapshot.key == "7|PL42"  # key columns ordered by name


def test_relation_resend_picks_up_new_columns_and_truncate_is_reported():
    decoder = pgoutput.PgOutputDecoder()
    small = relation(16403, "core", "notes", [("id", 20, True), ("body", 25, False)])
    grown = relation(
        16403, "core", "notes", [("id", 20, True), ("body", 25, False), ("lang", 1043, False)]
    )
    first = feed_all(
        decoder, small, begin(), b"I" + struct.pack("!I", 16403) + b"N" + tup([1, "hi"]), commit()
    )
    second = feed_all(
        decoder,
        grown,
        begin(),
        b"I" + struct.pack("!I", 16403) + b"N" + tup([2, "namaste", "hi"]),
        b"T" + struct.pack("!ib", 1, 0) + struct.pack("!I", 16403),
        commit(),
    )
    assert first.events[0].record == {"id": 1, "body": "hi"}
    assert second.events[0].record == {"id": 2, "body": "namaste", "lang": "hi"}
    assert second.events[1].operation == "TRUNCATE" and not second.events[1].is_data_change


def test_origin_type_and_message_are_ignored():
    decoder = pgoutput.PgOutputDecoder()
    assert decoder.feed(b"O" + struct.pack("!q", 1) + s("upstream")) is None
    assert decoder.feed(b"Y" + struct.pack("!I", 99999) + s("public") + s("mood")) is None


@pytest.mark.parametrize(
    "payload, message",
    [
        (b"I" + struct.pack("!I", 1) + b"N" + tup([1]), "unknown relation"),
        (b"S" + struct.pack("!Ib", 1, 1), "streamed"),
        (b"Z", "unknown pgoutput message"),
        (b"B" + b"\x00" * 5, "truncated"),
    ],
)
def test_bad_input_raises_a_decoding_error(payload, message):
    with pytest.raises(pgoutput.PgOutputError, match=message):
        pgoutput.PgOutputDecoder().feed(payload)


def test_column_count_mismatch_and_binary_values_are_rejected():
    decoder = pgoutput.PgOutputDecoder()
    decoder.feed(LOANS)
    with pytest.raises(pgoutput.PgOutputError, match="columns"):
        decoder.feed(b"I" + struct.pack("!I", 16401) + b"N" + tup(["PL1"]))
    notes = relation(5, "public", "n", [("id", 23, True)])
    decoder.feed(notes)
    with pytest.raises(pgoutput.PgOutputError, match="binary"):
        decoder.feed(
            b"I"
            + struct.pack("!I", 5)
            + b"N"
            + struct.pack("!h", 1)
            + b"b"
            + struct.pack("!i", 4)
            + b"\x00\x00\x00\x01"
        )


def test_lsn_helpers_round_trip():
    assert pgoutput.lsn_to_str(0x16B3748) == "0/16B3748"
    assert pgoutput.str_to_lsn("1/0") == 1 << 32
    assert pgoutput.str_to_lsn(pgoutput.lsn_to_str(123456789012)) == 123456789012


class _Msg:
    def __init__(self, payload):
        self.payload = payload


class _FakeCursor:
    def __init__(self, payloads):
        self.payloads = list(payloads)
        self.feedback = []
        self.wal_end = 0x2000

    def read_message(self):
        return _Msg(self.payloads.pop(0)) if self.payloads else None

    def send_feedback(self, **kw):
        self.feedback.append(kw)

    def fileno(self):  # used by select()
        return 0


def test_stream_yields_transactions_confirms_only_on_request_and_advances_when_idle(monkeypatch):
    stream = pgoutput.PostgresLogicalStream(
        "postgresql://x", "nexora_ops_1", "nexora_pub", status_interval=0
    )
    fake = _FakeCursor(
        [
            LOANS,
            begin(),
            b"I"
            + struct.pack("!I", 16401)
            + b"N"
            + tup(["PL42", 0, "1", "t", "2026-10-05", "2026-09-27 10:00:00+00", None, "{}"]),
            commit(),
        ]
    )
    stream._cur = fake
    stream._streaming = True
    monkeypatch.setattr(pgoutput.select, "select", lambda r, w, x, t: ([], [], []))
    it = stream.transactions(idle_timeout=0)
    txn = next(it)
    assert txn.events[0].key == "PL42"
    assert next(it) is None
    assert fake.feedback == [{}]  # a transaction is pending: keepalive only, no LSN advance
    stream.confirm(txn.end_lsn)
    assert fake.feedback[-1]["flush_lsn"] == txn.end_lsn
    assert next(it) is None
    assert fake.feedback[-1]["flush_lsn"] == 0x2000  # nothing pending: confirm the server's WAL end


def test_stream_validates_identifiers():
    with pytest.raises(ValueError):
        pgoutput.PostgresLogicalStream("dsn", "Bad-Slot", "pub")
    with pytest.raises(ValueError):
        pgoutput.PostgresLogicalStream("dsn", "ok_slot", "pub; DROP TABLE x")
