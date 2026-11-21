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

"""NexusClient ingestion APIs: process_file, extract_text, prepare_chunks, embed_passages,
process_change_events, rerank helpers, JSON records, text decoding and PDF page texts."""

from __future__ import annotations

import io
import json
import zipfile
from typing import ClassVar

import pytest

from nexus.client import NexusClient
from nexus.client_ingest import UnsupportedFormat
from nexus.table_records import coerce_value, flatten_record, rows_from_columns, rows_to_markdown
from tests.test_nexus_pdf import make_test_pdf


@pytest.fixture(scope="module")
def client():
    return NexusClient(in_memory_only=True, chunk_max_tokens=120)


class _StubEmbedder:
    window = 16

    def count_tokens(self, text):
        return len(text.split())

    def count_tokens_batch(self, texts):
        return [self.count_tokens(t) for t in texts]


class StubClient(NexusClient):
    seen: ClassVar[list[str]] = []

    @property
    def text_embedder(self):
        return _StubEmbedder()

    def embed_texts(self, texts):
        StubClient.seen = list(texts)
        return [[0.0] for _ in texts]


def test_embed_passages_prefixes_titles_and_shortens_only_the_title():
    c = StubClient(in_memory_only=True, chunk_max_tokens=0)
    c.embed_passages(["one two", "w " * 12], titles=["Doc A", "A very long document title here"])
    assert StubClient.seen[0] == "Doc A\none two"
    assert (
        StubClient.seen[1] == "A\n" + "w " * 12
    )  # 16 - 2 special - 12 body - 1 newline = 1 title word
    c.embed_passages(["x"], titles=None)
    assert StubClient.seen == ["x"]


def test_process_file_dispatches_by_extension_and_content(client):
    assert client.process_file("d1", "notes.md", b"# Title\n\nBody text").file_type == "md"
    cp1252 = client.process_file("d2", "legacy.txt", "café ’quote’ €5".encode("cp1252"))
    assert cp1252.chunks[0].text == "café ’quote’ €5"
    pdf = client.process_file(
        "d3", "report.pdf", make_test_pdf(["Quarterly report text for routing."])
    )
    assert pdf.file_type == "pdf" and "Quarterly report" in pdf.chunks[0].text
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("a.txt", "x")
    with pytest.raises(UnsupportedFormat):
        client.process_file("d4", "archive.zip", buf.getvalue())
    assert client.process_file("d5", "m.py", b"def f():\n    return 1\n").file_type in (
        "code",
        "python",
        "py",
    )


def test_process_document_decodes_bytes_and_keeps_text_as_written(client):
    doc = client.process_document("b1", "a.md", "# T\n\ncafé".encode())
    assert "café" in doc.chunks[0].text and "b'" not in doc.chunks[0].text
    assert doc.execution_trace[0].details["encoding"] == "utf-8"
    kept = client.process_document("b2", "a.txt", "x² ﬁle क्‍ष")
    assert kept.chunks[0].text == "x² ﬁle क्‍ष"
    assert kept.quality["chunks"] == 1 and "flags" in kept.quality


def test_json_record_arrays_become_masked_records(client):
    data = {
        "meta": {"owner": "jane@example.com"},
        "data": [
            {"id": i, "amount": i * 2.5, "phone": f"55533344{i:02d}", "addr": {"city": "X"}}
            for i in range(60)
        ],
    }
    doc = client.process_document("j1", "export.json", json.dumps(data, indent=2))
    records = [r for c in doc.chunks for r in c.metadata.get("records") or []]
    assert len(records) == 60 and records[3] == {
        "id": 3,
        "amount": 7.5,
        "phone": "[PHONE]",
        "addr.city": "X",
    }
    assert (
        doc.chunks[0].text.startswith("Records: data[] (60 rows)")
        and "[EMAIL]" in doc.chunks[0].text
    )
    assert all(c.text.startswith("Columns: id, amount, phone, addr.city") for c in doc.chunks[1:])
    assert doc.metadata["is_tabular"] is True


def test_prepare_chunks_uses_the_client_budget(client):
    out = client.prepare_chunks(
        [{"text": "word " * 1000, "metadata": {"record": {"id": 1}, "data": {}}}]
    )
    assert (
        len(out) > 1
        and "data" not in out[0]["metadata"]
        and out[0]["metadata"]["record"] == {"id": 1}
    )
    assert client.document_digest("a.md", "md", out).startswith("Document: a.md (type: md")


def test_extract_text_keeps_pages_and_refuses_binary_noise(client):
    pdf = client.extract_text(
        "r.pdf", make_test_pdf(["Alpha page text here.", "Beta page text here."])
    )
    assert pdf.text == "[Page 1]\nAlpha page text here.\n\n[Page 2]\nBeta page text here."
    assert [u[0] for u in pdf.units] == ["Page 1", "Page 2"]
    assert client.extract_text("broken.pdf", b"%PDF-1.4 nothing").readable is False
    assert client.extract_text("img.png", b"\x89PNG\r\n\x1a\n").text == ""
    utf16 = client.extract_text("notes.txt", "hello".encode("utf-16"))
    assert utf16.text == "hello" and utf16.encoding == "utf-16-le"


def test_process_pdf_with_external_page_texts_drops_empty_pages_and_running_lines(client):
    pages = [
        "ACME report\nFirst page body.",
        "",
        "ACME report\nThird page body.",
        "ACME report\nFourth page.",
    ]
    doc = client.process_pdf(
        "p1", "r.pdf", make_test_pdf(["a", "b", "c", "d"]), page_texts=pages, auto_extract=False
    )
    assert [c.metadata["page_number"] for c in doc.chunks] == [1, 3, 4]
    assert doc.chunks[0].text == "[Page 1] First page body." and doc.metadata["empty_pages"] == 1
    assert doc.chunks[0].metadata["text_source"] == "external"


def test_process_change_events_masks_by_stable_column_kinds(client):
    state: dict = {}
    events = [
        {
            "op": "c",
            "table": "orders",
            "record": {
                "id": 5553334444,
                "amount": "5553334444",
                "phone": "5553334444",
                "notes": "my number is 5553334444",
            },
        }
    ]
    chunks, kinds = client.process_change_events(events, state=state)
    text = chunks[0].text
    assert "id: 5553334444" in text and "amount: 5553334444" in text
    assert "phone: [PHONE]" in text and "notes: my number is [PHONE]" in text
    assert kinds["phone"] == "phone" and state[chunks[0].key]["phone"] == "[PHONE]"
    # A later batch with an empty phone value keeps the column a phone column.
    _later, kinds2 = client.process_change_events(
        [{"op": "c", "table": "orders", "record": {"id": 7, "phone": "", "notes": ""}}],
        column_kinds=kinds,
    )
    assert kinds2["phone"] == "phone"
    deleted, _ = client.process_change_events(
        [{"op": "d", "table": "orders", "record": {"id": 7}}], state=state
    )
    assert deleted[0].delete is True


def test_reranker_info_and_rerank_multi(client, monkeypatch):
    info = client.reranker_info()
    assert {"model", "max_chars", "pool", "broad_pool"} <= set(info)
    monkeypatch.setattr(
        NexusClient, "rerank", lambda self, q, ps: [0.9 if q in p else 0.1 for p in ps]
    )
    assert client.rerank_multi(["x", "b"], ["a x", "b"], [set(), {1}]) == [0.9, 0.9]


def test_table_records_helpers():
    md = rows_to_markdown(
        "posts",
        [{"title": "Hello", "body": "Text", "author": "A"}, {"id": 1, "v": None}],
        "Collection",
    )
    assert md == "## Collection: posts\n\n# Hello\n**author:** A\n\nText\n\n\n---\n\n- id: 1"
    assert coerce_value("bigquery", {"type": "TIMESTAMP"}, "0") == "1970-01-01T00:00:00+00:00"
    assert coerce_value(
        "bigquery", {"type": "INT64", "mode": "REPEATED"}, [{"v": "1"}, {"v": None}]
    ) == [1, None]
    assert coerce_value("snowflake", {"type": "date"}, "1") == "1970-01-02"
    assert coerce_value("snowflake", {"type": "fixed", "scale": 2}, "1.50") == 1.5
    assert coerce_value("databricks", {"type_name": "BIGINT"}, "7") == 7
    assert coerce_value("databricks", {"type_name": "BIGINT"}, "x") == "x"
    rows = rows_from_columns(
        "bigquery",
        [
            {"name": "a", "type": "INT64"},
            {"name": "s", "type": "RECORD", "fields": [{"name": "b", "type": "BOOL"}]},
        ],
        [{"f": [{"v": "2"}, {"v": {"f": [{"v": "true"}]}}]}],
    )
    assert rows == [{"a": 2, "s": {"b": True}}]
    assert flatten_record(
        {"attributes": {"type": "X"}, "Account": {"Name": "Acme"}, "Note": "abcdef"},
        max_value_chars=3,
    ) == {"Account.Name": "Acm…", "Note": "abc…"}
