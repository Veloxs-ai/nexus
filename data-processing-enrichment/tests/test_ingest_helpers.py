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

"""Text decoding, storage-ready chunks, JSON tables, passages, outlines, language, quality."""

from __future__ import annotations

import json
import random
import re
import time

from nexus_processing.chunk_store import document_digest, prepare_chunks
from nexus_processing.chunking import chunk_json, chunk_markdown, chunk_smart_text, split_table
from nexus_processing.json_table import compact_json, json_table
from nexus_processing.language import detect_language, detect_script
from nexus_processing.outline import build_outline, plan_sections, section_text
from nexus_processing.passages import join_adjacent, stitch
from nexus_processing.quality import assess_text
from nexus_processing.text_decode import decode_text, looks_binary
from nexus_processing.token_budget import fit_text, split_header


# ---- decode_text ---------------------------------------------------------------------------
def test_decode_text_never_drops_characters():
    assert decode_text("café".encode()).encoding == "utf-8"
    cp = decode_text("café ’q’ €5".encode("cp1252"))
    assert cp.text == "café ’q’ €5" and cp.encoding == "cp1252"
    u16 = decode_text("hello wörld".encode("utf-16"))
    assert u16.text == "hello wörld" and u16.bom
    no_bom = decode_text("hello world, plain".encode("utf-16-le"))
    assert no_bom.text == "hello world, plain" and no_bom.encoding == "utf-16-le"
    assert decode_text(b"\xef\xbb\xbfbom").text == "bom"
    assert decode_text(bytes([0x81, 0x41])).encoding == "latin-1"  # 0x81 is undefined in cp1252


def test_looks_binary():
    assert looks_binary(b"PK\x03\x04\x00\x00binary")
    assert not looks_binary("text".encode("utf-16"))
    assert not looks_binary(b"plain text")


# ---- prepare_chunks / document_digest ----------------------------------------------------
def test_prepare_chunks_splits_by_tokens_and_keeps_records_on_the_first_part():
    long_text = "order note " + "words and more words. " * 400
    out = prepare_chunks(
        [{"text": long_text, "metadata": {"record_key": "7", "record": {"id": 7}}}], max_tokens=100
    )
    assert len(out) > 1
    assert all(o["metadata"]["record_key"] == "7" for o in out)
    assert [o["metadata"].get("record") for o in out] == [{"id": 7}] + [None] * (len(out) - 1)
    assert [(o["metadata"]["part"], o["metadata"]["parts"]) for o in out] == [
        (n + 1, len(out)) for n in range(len(out))
    ]


def test_prepare_chunks_bounds_chunks_a_char_threshold_left_whole():
    # 2,800 characters of numbers: under the old 3,000-character threshold, far over 450 tokens.
    text = " ".join(str(100000 + i) for i in range(400))
    out = prepare_chunks([{"text": text, "metadata": {}}])
    assert len(out) > 1 and all(len(o["text"]) < len(text) for o in out)


def test_prepare_chunks_packs_tiny_rows_and_never_packs_keyed_rows():
    rows = [
        {"text": f"[Row {i}] a: {i} | b: {i * 2}", "metadata": {"row_index": i, "data": {"a": i}}}
        for i in range(200)
    ]
    packed = prepare_chunks(rows)
    assert 1 < len(packed) < 20
    assert sum(p["metadata"]["packed_rows"] for p in packed) == 200
    assert packed[0]["metadata"]["row_range"] == [0, packed[0]["metadata"]["packed_rows"] - 1]
    assert all("data" not in p["metadata"] and len(p["text"]) <= 1500 for p in packed)
    keyed = [
        {"text": f"r{i}", "metadata": {"record_key": str(i), "record": {"id": i}}}
        for i in range(25)
    ]
    assert [o["metadata"]["record_key"] for o in prepare_chunks(keyed)] == [
        str(i) for i in range(25)
    ]


def test_prepare_chunks_drops_caller_keys_and_empty_chunks():
    out = prepare_chunks(
        [{"text": "a", "metadata": {"doc_stats": 1, "x": 1}}, {"text": " \x00 "}],
        drop_keys=("data", "doc_stats"),
    )
    assert out == [{"text": "a", "metadata": {"x": 1}}]


def test_document_digest_reads_every_processor_structure():
    items = [
        {"text": "Section: Handbook > PTO\nEmployees get 20 days.", "metadata": {}},
        {"text": "[Workbook: f | Sheet: Q1 | Row 2] a: 1", "metadata": {"sheet_name": "Q1"}},
        {"text": "Body", "metadata": {"heading_path": ["Guide", "Install"]}},
    ]
    digest = document_digest("handbook.md", "md", items)
    assert digest.startswith("Document: handbook.md (type: md, 3 chunks).")
    assert "Handbook > PTO; Q1; Guide > Install" in digest


# ---- chunk_smart_text (linear) and Markdown tables -----------------------------------------
def _old_chunk_smart_text(text, chunk_size=1000, chunk_overlap=200):
    clean_text = text.replace("\r\n", "\n").replace("\r", "\n").strip()
    if not clean_text:
        return []
    chunks, remaining_text = [], clean_text
    while len(remaining_text) > 0:
        if len(remaining_text) <= chunk_size:
            if remaining_text.strip():
                chunks.append(remaining_text.strip())
            break
        split_point = remaining_text.rfind("\n\n", 0, chunk_size)
        if split_point == -1 or split_point < chunk_size * 0.4:
            split_point = remaining_text.rfind(". ", 0, chunk_size)
            if split_point != -1:
                split_point += 1
        if split_point == -1 or split_point < chunk_size * 0.4:
            split_point = remaining_text.rfind(" ", 0, chunk_size)
        if split_point == -1 or split_point < chunk_size * 0.4:
            split_point = chunk_size
        chunk = remaining_text[:split_point].strip()
        if chunk:
            chunks.append(chunk)
        next_start = max(0, split_point - chunk_overlap)
        if 0 < next_start < split_point:
            boundary = remaining_text.find(" ", next_start, split_point)
            if boundary != -1:
                next_start = boundary + 1
        remaining_text = remaining_text[next_start:].strip()
    return chunks


def test_linear_chunk_smart_text_matches_the_previous_output():
    rng = random.Random(7)
    words = ["alpha", "beta.", "gamma", "delta\n\n", "eps", "x" * 50, "Zeta.", "\n", "omega"]
    for _ in range(30):
        text = " ".join(rng.choice(words) for _ in range(rng.randint(50, 800)))
        size = rng.choice([200, 500, 1000])
        assert chunk_smart_text(text, size, size // 5) == _old_chunk_smart_text(
            text, size, size // 5
        )


def test_benchmark_chunk_smart_text_is_linear():
    text = ("Lorem ipsum dolor sit amet, consectetur adipiscing elit. " * 18) + "\n\n"
    big = text * 8000  # ~8 MB
    started = time.perf_counter()
    chunks = chunk_smart_text(big)
    elapsed = time.perf_counter() - started
    assert len(chunks) > 8000
    assert elapsed < 2.0  # ~0.2 s; the re-slicing version took ~4.4 s on 8 MB


def test_split_markdown_table_repeats_the_header_on_every_piece():
    rows = "\n".join(f"| {i} | val{i} | {i * 3} |" for i in range(80))
    md = "# T\n\nIntro text.\n\n| a | b | c |\n| --- | --- | --- |\n" + rows + "\n\nAfter."
    chunks = chunk_markdown(md)
    table_chunks = [c for c in chunks if "| 4" in c or "| 7" in c]
    assert len(table_chunks) >= 2
    assert all("| a | b | c |\n| --- | --- | --- |" in c for c in table_chunks)
    assert (
        sum(len(re.findall(r"^\| \d+ \|", c, re.M)) for c in chunks) == 80
    )  # every row exactly once
    assert split_table(["| h |", "|---|", "| 1 |", "| 2 |"], 12) == [
        "| h |\n|---|\n| 1 |",
        "| h |\n|---|\n| 2 |",
    ]


def test_token_budget_repeats_a_table_header_on_split_parts():
    table = "Section: Prices\n| item | price |\n| --- | --- |\n" + "\n".join(
        f"| thing {i} | {i}.00 |" for i in range(300)
    )
    header, _, _ = split_header(table)
    assert header == "Section: Prices\n| item | price |\n| --- | --- |"
    parts = fit_text(table, 120)
    assert len(parts) > 1 and all(p.startswith(header) for p in parts)


# ---- JSON tables ------------------------------------------------------------------------------
def test_json_table_finds_the_largest_record_array_at_any_depth():
    data = {
        "meta": {"page": 1, "tags": ["a", "b"]},
        "result": {"items": [{"id": i, "c": {"n": i}} for i in range(50)]},
        "small": [{"x": 1}, {"x": 2}],
    }
    table = json_table(json.dumps(data))
    assert table.path == "result.items[]" and len(table.rows) == 50
    assert table.columns == ["id", "c.n"] and table.rows[3] == {"id": 3, "c.n": 3}
    assert "meta.page: 1" in table.context and "meta.tags: a, b" in table.context
    assert json_table("[1, 2, 3]") is None and json_table("not json") is None
    assert json_table('```json\n[{"a": 1}, {"a": 2}]\n```').path == "[]"


def test_chunk_json_is_compact():
    chunks = chunk_json(json.dumps({"a": [1, 2], "b": {"c": "d"}}, indent=2))
    assert chunks == ['{"a":[1,2],"b":{"c":"d"}}'] and compact_json({"é": 1}) == '{"é":1}'


# ---- passages and outlines --------------------------------------------------------------------
def test_join_adjacent_drops_repeated_headers_and_overlap():
    prev = (
        "Section: Guide > Install\nRun the installer and then restart the machine to finish setup."
    )
    nxt = "Section: Guide > Install\nrestart the machine to finish setup. Then log in."
    assert join_adjacent(prev, nxt) == prev + " Then log in."
    rows = ["Columns: a, b\n[Row ID: 1] a: 1", "Columns: a, b\n[Row ID: 2] a: 2"]
    assert stitch(rows) == "Columns: a, b\n[Row ID: 1] a: 1\n[Row ID: 2] a: 2"


def test_plan_sections_and_build_outline_with_an_injected_model():
    chunks = [
        {"text": f"part {i} " + "word " * 300, "chunk_index": i, "token_count": 1000}
        for i in range(40)
    ]
    runs, left_out = plan_sections(chunks)
    assert 2 <= len(runs) <= 12 and left_out == 0 and sum(len(r) for r in runs) == 40
    calls = []

    def complete(system, prompt, max_tokens):
        calls.append((system[:20], max_tokens))
        return "summary" if "SECTION" not in prompt else "notes"

    outline = build_outline("doc.pdf", chunks, complete)
    assert outline.summary == "summary" and len(outline.sections) == len(runs)
    assert outline.sections[0].first_index == 0 and outline.sections[-1].last_index == 39
    assert len(calls) == len(runs) + 1
    assert section_text([{"text": "a"}, {"text": "b"}]) == "a\nb"


# ---- language and quality ---------------------------------------------------------------------
def test_language_detection():
    assert detect_language("The quick brown fox jumps over the lazy dog and the cat")[0] == "en"
    assert detect_language("El perro de la casa es muy grande y los niños juegan con él")[0] == "es"
    assert detect_language("यह एक हिंदी वाक्य है जो परीक्षण के लिए है")[0] == "hi"
    assert detect_language("这是一个用于测试的中文句子")[0] == "zh"
    assert detect_language("これはテストのための日本語の文です")[0] == "ja"
    assert detect_language("12345 ...")[0] == "und"
    assert next(iter(detect_script("Привет мир"))) == "CYRILLIC"


def test_quality_flags_garbled_and_empty_output():
    good = assess_text(["A normal sentence about invoices and payments."])
    assert good["flags"] == [] and good["language"] == "en"
    garbled = assess_text(["%$#@!*&^%$#@!~~~^^^%%%$$$###@@@"])
    assert "garbled_text" in garbled["flags"]
    assert "no_text" in assess_text(["   "])["flags"]
    assert "replacement_chars" in assess_text(["bad �� bytes"])["flags"]
