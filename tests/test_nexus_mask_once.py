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

"""NexusClient masks once: whole documents before chunking, table cells once, CDC keys once."""

from __future__ import annotations

import re

import pytest

from nexus.chunk_limits import ChunkLimiter
from nexus.client import NexusClient
from nexus.models import ProcessedChunk
from nexus.table_records import mask_rows

try:
    from nexus.processing.csv_table import parse_csv_table
    from nexus.processing.csv_table import row_text as csv_row_text
except (ImportError, ModuleNotFoundError):
    from nexus_processing.csv_table import parse_csv_table
    from nexus_processing.csv_table import row_text as csv_row_text

LEAK = re.compile(r"\d{3}[-.\s]\d{4}|\d{4} \d{4}|@")


@pytest.fixture(scope="module")
def client():
    return NexusClient(in_memory_only=True, chunk_max_tokens=120)


def _document(n: int) -> str:
    parts = []
    for i in range(n):
        parts.append(
            f"Paragraph {i} explains the refund window and the escalation path in detail. "
            f"Reach Sam at sam{i}@example.com or call +1 (415) 555-{1000 + i:04d}; "
            f"the backup card is 4111 1111 1111 1111. "
        )
    return "".join(parts)


def test_no_pii_fragment_survives_chunk_boundaries(client):
    payload = client.process_document("d1", "notes.txt", _document(300), file_type="txt")
    assert len(payload.chunks) > 5
    assert not [c.text for c in payload.chunks if LEAK.search(c.text)]
    assert payload.metadata["emails"] == []
    assert payload.execution_trace[3].details["chunks_with_pii"] > 0


def test_guardrails_off_keeps_text_and_emails(client):
    text = "Mail sam@example.com about the refund."
    payload = client.process_document("d2", "a.txt", text, file_type="txt", enable_guardrails=False)
    assert payload.chunks[0].text == text
    assert payload.metadata["emails"] == ["sam@example.com"]


CSV = (
    "order_id,email,phone,amount,zip,notes\n"
    'ORD-1,ann@x.com,415-555-0134,"1,234.50",02139,call me at 415-555-0199\n'
    "ORD-2,bob@y.org,N/A,10.00,00501,all good\n"
    "ORD-3,,+44 20 7946 0958,7,10001,mail c@d.co\n"
)


def test_csv_cells_masked_once_match_masking_the_display_rows(client):
    payload = client.process_document("t", "orders.csv", CSV, file_type="csv")
    table = parse_csv_table(CSV)
    kinds = client.guardrails.classify_columns(table.typed_rows)
    shown, _ = mask_rows(client.guardrails, table.rows, True, kinds)
    expected = [csv_row_text(n, row) for n, row in enumerate(shown, start=1)]
    text = "\n".join(c.text for c in payload.chunks)
    for line in expected:
        assert line in text
    assert "1,234.50" in text and "02139" in text and "@" not in text
    assert payload.metadata["emails"] == []
    records = [r for c in payload.chunks for r in c.metadata.get("records", [])]
    assert [r["order_id"] for r in records] == ["ORD-1", "ORD-2", "ORD-3"]


def test_row_groups_carry_a_token_bound_the_limiter_trusts(client, monkeypatch):
    limiter = client.chunk_limiter
    rows = "\n".join(f"{i},note number {i} about refunds" for i in range(400))
    csv_text = "id,note\n" + rows + "\n"
    calls: list[int] = []
    original = limiter.count_many

    def counting(texts):
        calls.append(len(texts))
        return original(texts)

    monkeypatch.setattr(limiter, "count_many", counting)
    payload = client.process_document("b", "b.csv", csv_text, file_type="csv")
    assert calls and calls[0] == 400  # rows counted once for packing
    if limiter.additive:  # packed groups are not tokenized again by ``bound``
        assert all(n == 0 for n in calls[1:])
    for chunk in payload.chunks:
        assert limiter.count(chunk.text) <= limiter.max_tokens


def test_limiter_skips_only_trusted_bounds():
    limiter = ChunkLimiter(32)
    assert limiter.additive
    chunk = ProcessedChunk(chunk_id="c", document_id="d", chunk_index=0, text="word " * 200)
    chunk._token_bound = 10  # a wrong bound is trusted only for additive counters
    assert len(limiter.bound([chunk])) == 1
    strict = ChunkLimiter(32, count=lambda t: len(t.split()))
    assert not strict.additive
    assert len(strict.bound([chunk])) > 1
    assert ProcessedChunk.model_validate(chunk.model_dump()).model_dump() == chunk.model_dump()


def _dbz(op: str, rid: int, amount: int, lsn: int) -> dict:
    after = None if op == "d" else {"id": rid, "amount": amount, "email": f"u{rid}@x.com"}
    before = {"id": rid} if op == "d" else None
    source = {"connector": "postgresql", "db": "shop", "table": "orders", "lsn": lsn}
    return {"payload": {"op": op, "before": before, "after": after, "source": source}}


def test_cdc_batch_emits_final_state_per_key_and_skips_stale_redelivery(client):
    events = [
        _dbz("c", 1, 10, 100),
        _dbz("u", 1, 20, 200),
        _dbz("c", 2, 5, 150),
        None,  # Kafka tombstone after a delete
        _dbz("u", 1, 15, 120),  # redelivered older update: must not win
        _dbz("d", 2, 0, 300),
    ]
    state: dict = {}
    positions: dict = {}
    chunks, _ = client.process_change_events(events, state=state, positions=positions)
    assert [(c.key, c.delete) for c in chunks] == [("1", False), ("2", True)]
    assert chunks[0].record["amount"] == 20 and chunks[0].record["email"] == "[EMAIL]"
    assert state == {"1": chunks[0].record}
    assert positions == {"1": "lsn:200", "2": "lsn:300"}
    later, _ = client.process_change_events(
        [_dbz("u", 1, 99, 200)], state=state, positions=positions
    )
    assert later == []  # already applied in the previous batch


def test_json_documents_are_masked_after_parsing(client):
    text = '{"owner": {"phone": 4155550134, "email": "a@b.co"}, "plan": "pro"}'
    payload = client.process_document("j", "cfg.json", text, file_type="json")
    joined = "\n".join(c.text for c in payload.chunks)
    assert "4155550134" not in joined and "a@b.co" not in joined
    assert "pro" in joined
    assert payload.metadata["emails"] == []
