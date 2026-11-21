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

"""Coverage contract: every processor stores (almost) all of the content it extracts.

``coverage`` is the share of the source's words (as a multiset) found in the stored
chunk texts: headers and overlaps cannot inflate it, and any truncation lowers it.
Every processor must keep at least 90%; every chunk must also fit the token budget.
"""

from __future__ import annotations

import io
import json
import math
import random
import re
import sqlite3
import struct
import wave
import zipfile
from collections import Counter
from xml.sax.saxutils import escape

import pytest
from test_nexus_pdf import make_test_pdf
from test_nexus_video import make_test_mp4

from nexus import NexusClient

MIN_COVERAGE = 0.9
SML = 'xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"'
REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PKG_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
_WORDS = re.findall(
    r"\w+",
    "revenue customer invoice renewal contract policy refund region quarter forecast pipeline "
    "warehouse shipment supplier audit escalation onboarding latency outage incident budget "
    "approval payroll benefits compliance retention churn segment analytics dashboard workflow",
)


def prose(n_words: int, seed: int) -> str:
    rnd = random.Random(seed)
    words = [
        f"{rnd.choice(_WORDS)}{rnd.randint(0, 99)}" if i % 7 == 3 else rnd.choice(_WORDS)
        for i in range(n_words)
    ]
    sentences = [" ".join(words[i : i + 12]).capitalize() + "." for i in range(0, n_words, 12)]
    return " ".join(sentences)


def coverage(source: str, texts: list[str]) -> float:
    want = Counter(re.findall(r"\w+", source.lower()))
    got: Counter[str] = Counter()
    for text in texts:
        got.update(re.findall(r"\w+", text.lower()))
    return sum(min(n, got[w]) for w, n in want.items()) / max(1, sum(want.values()))


@pytest.fixture(scope="module")
def client() -> NexusClient:
    return NexusClient(in_memory_only=True)


def check(client: NexusClient, source: str, doc) -> None:
    texts = [c.text for c in doc.chunks]
    assert coverage(source, texts) >= MIN_COVERAGE, (
        f"{doc.file_type}: {coverage(source, texts):.2f}"
    )
    limit = client.chunk_limiter.max_tokens
    assert max(client.count_tokens(t) for t in texts) <= limit


# --- text formats ----------------------------------------------------------------


def test_markdown_txt_and_other_text_keep_their_words(client):
    md = "# Handbook\n\n" + "\n\n".join(f"## Part {i}\n\n{prose(400, i)}" for i in range(6))
    check(client, md, client.process_document("md", "h.md", md, enable_guardrails=False))
    txt = prose(5000, 7)
    check(client, txt, client.process_document("txt", "a.txt", txt, enable_guardrails=False))
    log = "\n".join(prose(30, i) for i in range(150))
    check(client, log, client.process_document("log", "a.log", log, enable_guardrails=False))


def test_json_and_csv_keep_every_record(client):
    records = [{"id": i, "note": prose(60, i), "region": f"r{i % 7}"} for i in range(80)]
    blob = json.dumps({"data": records})
    check(client, blob, client.process_document("j", "a.json", blob, enable_guardrails=False))
    csv_text = "id,region,note\n" + "\n".join(f"{i},r{i % 5},{prose(40, i)}" for i in range(200))
    doc = client.process_document("c", "a.csv", csv_text, enable_guardrails=False)
    check(client, csv_text, doc)
    assert sum(len(c.metadata.get("records", [])) for c in doc.chunks) == 200


# --- office ------------------------------------------------------------------------


def _xlsx(rows: list[list[str]]) -> bytes:
    def cell(col: int, row: int, value: str) -> str:
        ref = f"{chr(65 + col)}{row}"
        return f'<c r="{ref}" t="inlineStr"><is><t>{escape(value)}</t></is></c>'

    sheet_rows = "".join(
        f'<row r="{r}">' + "".join(cell(c, r, v) for c, v in enumerate(vals)) + "</row>"
        for r, vals in enumerate(rows, start=1)
    )
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr(
            "xl/workbook.xml",
            f'<workbook {SML} xmlns:r="{REL_NS}">'
            '<sheets><sheet name="Data" sheetId="1" r:id="rId1"/></sheets></workbook>',
        )
        zf.writestr(
            "xl/_rels/workbook.xml.rels",
            f'<Relationships xmlns="{PKG_NS}"><Relationship Id="rId1" '
            'Target="worksheets/sheet1.xml" Type="worksheet"/></Relationships>',
        )
        zf.writestr(
            "xl/worksheets/sheet1.xml",
            f"<worksheet {SML}><sheetData>{sheet_rows}</sheetData></worksheet>",
        )
    return buf.getvalue()


def test_spreadsheet_keeps_every_cell(client):
    rows = [["Region", "Owner", "Notes"]] + [
        [f"r{i}", f"owner{i}", prose(120, i)] for i in range(60)
    ]
    doc = client.process_spreadsheet("x", "book.xlsx", _xlsx(rows), enable_guardrails=False)
    check(client, " ".join(" ".join(r) for r in rows[1:]), doc)


def test_word_document_keeps_paragraphs_and_tables(client):
    paras = [prose(150, i) for i in range(12)]
    body = "".join(f"<w:p><w:r><w:t>{escape(p)}</w:t></w:r></w:p>" for p in paras)
    cells = [prose(80, 100 + i) for i in range(8)]
    table = (
        "<w:tbl>"
        + "".join(
            f"<w:tr><w:tc><w:p><w:r><w:t>{escape(a)}</w:t></w:r></w:p></w:tc>"
            f"<w:tc><w:p><w:r><w:t>{escape(b)}</w:t></w:r></w:p></w:tc></w:tr>"
            for a, b in zip(cells[::2], cells[1::2], strict=True)
        )
        + "</w:tbl>"
    )
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr(
            "word/document.xml",
            '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body>'
            + body
            + table
            + "</w:body></w:document>",
        )
    doc = client.process_word("w", "d.docx", docx_bytes=buf.getvalue(), enable_guardrails=False)
    check(client, " ".join(paras + cells), doc)


def test_presentation_keeps_slide_text(client):
    texts = [prose(250, i) for i in range(3)]
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        ids = "".join(f'<p:sldId id="{256 + i}" r:id="rId{i + 1}"/>' for i in range(3))
        zf.writestr(
            "ppt/presentation.xml",
            '<p:presentation xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><p:sldIdLst>'
            + ids
            + "</p:sldIdLst></p:presentation>",
        )
        rels = "".join(
            f'<Relationship Id="rId{i + 1}" Type="slide" Target="slides/slide{i + 1}.xml"/>'
            for i in range(3)
        )
        zf.writestr(
            "ppt/_rels/presentation.xml.rels",
            f'<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">{rels}</Relationships>',
        )
        for i, text in enumerate(texts):
            zf.writestr(
                f"ppt/slides/slide{i + 1}.xml",
                '<p:sld xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main" xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"><p:cSld><p:spTree><p:sp><p:txBody><a:p><a:r><a:t>'
                + escape(text)
                + "</a:t></a:r></a:p></p:txBody></p:sp></p:spTree></p:cSld></p:sld>",
            )
    doc = client.process_presentation(
        "p", "deck.pptx", presentation_bytes=buf.getvalue(), enable_guardrails=False
    )
    check(client, " ".join(texts), doc)


def test_pdf_keeps_page_text(client):
    pages = [prose(120, i) for i in range(3)]
    doc = client.process_pdf(
        "pdf", "a.pdf", pdf_bytes=make_test_pdf(pages), enable_guardrails=False
    )
    check(client, " ".join(pages), doc)


# --- communication -------------------------------------------------------------------


def test_email_and_chat_keep_their_messages(client):
    body = prose(2500, 3)
    eml = f"From: a@example.com\r\nTo: b@example.com\r\nSubject: Q3\r\n\r\n{body}\r\n".encode()
    check(
        client, body, client.process_email("e", "m.eml", email_bytes=eml, enable_guardrails=False)
    )
    msgs = [
        {"user": f"u{i % 4}", "text": prose(40, i), "ts": str(1726000000 + i)} for i in range(120)
    ]
    doc = client.process_chat("c", "chat", chat_data=msgs, enable_guardrails=False)
    check(client, " ".join(m["text"] for m in msgs), doc)


def test_long_slack_thread_is_split_not_truncated(client):
    parent = {
        "ts": "1726000000.000100",
        "thread_ts": "1726000000.000100",
        "reply_count": 59,
        "user": "U1",
        "text": prose(30, 0),
    }
    replies = [
        {
            "ts": f"{1726000001 + i}.000100",
            "thread_ts": parent["ts"],
            "user": f"U{i % 3}",
            "text": prose(30, i + 1),
        }
        for i in range(59)
    ]
    doc = client.process_slack_export(
        "s", "general.json", json.dumps([parent, *replies]).encode(), enable_guardrails=False
    )
    check(client, " ".join(m["text"] for m in [parent, *replies]), doc)
    assert all(c.text.startswith("[Slack #general | Thread started") for c in doc.chunks)


# --- code ------------------------------------------------------------------------------


PY_SOURCE = (
    '"""Billing jobs."""\nimport os\n\n'
    'RATES = {"gold": 3, "silver": 2}\nREGIONS = ["north", "south"]\n\n\n'
    "class Ledger:\n    currency = 'INR'\n    precision = 4\n\n    def total(self, rows):\n"
    "        return sum(r['amount'] for r in rows)\n\n\n"
    "def settle(ledger):\n    return ledger.total([])\n\n\n"
    'if __name__ == "__main__":\n    print(settle(Ledger()), os.getcwd(), RATES, REGIONS)\n'
)


def test_code_keeps_module_level_code_and_class_attributes(client):
    doc = client.process_code("py", "billing.py", code_input=PY_SOURCE, enable_guardrails=False)
    check(client, PY_SOURCE, doc)
    script = "\n".join(
        f"UPDATE accounts SET tier = 'gold{i}' WHERE region = 'r{i}';" for i in range(120)
    )
    doc = client.process_code("sql", "migrate.py", code_input=script, enable_guardrails=False)
    check(client, script, doc)
    js = (
        "const LIMIT = 10;\nimport x from 'y';\n\n"
        "function run(a) {\n  return a + LIMIT;\n}\n\nrun(LIMIT);\n"
    )
    check(client, js, client.process_code("js", "app.js", code_input=js, enable_guardrails=False))


def test_openapi_keeps_operations(client):
    paths = {
        f"/items{i}": {"get": {"summary": prose(20, i), "description": prose(60, i + 50)}}
        for i in range(15)
    }
    spec = {"openapi": "3.0.0", "info": {"title": "Items", "version": "1"}, "paths": paths}
    doc = client.process_openapi("o", "openapi.json", spec_data=spec, enable_guardrails=False)
    source = " ".join(f"{op['get']['summary']} {op['get']['description']}" for op in paths.values())
    check(client, source, doc)


# --- databases --------------------------------------------------------------------------


def test_mongo_keeps_every_array_element(client):
    docs = [
        {"_id": f"o{i}", "lines": [{"sku": f"sku{i}x{j}", "qty": j} for j in range(25)]}
        for i in range(4)
    ]
    doc = client.process_mongo_collection("orders", docs, enable_guardrails=False)
    source = " ".join(f"sku{i}x{j}" for i in range(4) for j in range(25))
    check(client, source, doc)


def test_mysql_and_sqlite_keep_long_rows(client):
    rows = [{"id": i, "note": prose(900 if i == 0 else 40, i)} for i in range(30)]
    check(
        client,
        " ".join(r["note"] for r in rows),
        client.process_mysql_table("notes", rows, enable_guardrails=False),
    )
    db = sqlite3.connect(":memory:")
    db.execute("CREATE TABLE t (id INTEGER PRIMARY KEY, note TEXT)")
    db.executemany("INSERT INTO t VALUES (?, ?)", [(r["id"], r["note"]) for r in rows])
    raw = db.serialize()
    doc = client.process_sqlite("db", "a.db", db_bytes=raw, enable_guardrails=False)
    check(client, " ".join(r["note"] for r in rows), doc)


# --- media ---------------------------------------------------------------------------------


def _silent_wav(seconds: float, rate: int = 8000) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(rate)
        frames = int(seconds * rate)
        wf.writeframes(
            b"".join(struct.pack("<h", int(800 * math.sin(i / 9))) for i in range(frames))
        )
    return buf.getvalue()


class _Transcriber:
    def __init__(self, segments: list[dict]) -> None:
        self.segments = segments

    def transcribe(self, _audio: bytes) -> tuple[str, list[dict]]:
        return " ".join(s["text"] for s in self.segments), self.segments


def test_audio_keeps_every_transcribed_word(client):
    segs = [{"start": i * 4.0, "end": i * 4.0 + 3.5, "text": prose(9, i)} for i in range(20)]
    doc = client.process_audio(
        "a",
        "call.wav",
        audio_bytes=_silent_wav(81.0),
        transcriber=_Transcriber(segs),
        enable_guardrails=False,
    )
    check(client, " ".join(s["text"] for s in segs), doc)
    assert not any("RMS:" in c.text for c in doc.chunks)


def test_mp3_keeps_every_transcribed_word(client):
    """72 s of speech in an MP3: chunks come from the transcript, not from a duration
    guessed out of the compressed bytes (which kept ~1 s, 8 of 146 words)."""
    mp3 = b"ID3\x03\x00\x00\x00\x00\x00\x00" + b"\xff\xfb\x90\x00" * 4000
    segs = [{"start": i * 3.8, "end": i * 3.8 + 3.6, "text": prose(8, i)} for i in range(19)]
    doc = client.process_audio(
        "m", "talk.mp3", audio_bytes=mp3, transcriber=_Transcriber(segs), enable_guardrails=False
    )
    check(client, " ".join(s["text"] for s in segs), doc)
    assert doc.metadata["duration_seconds"] >= segs[-1]["end"]


def test_video_keeps_full_scene_dialogue(client):
    segs = [{"start": i * 10.0, "end": i * 10.0 + 9.0, "text": prose(45, i)} for i in range(6)]
    doc = client.process_video(
        "v", "intro.mp4", video_bytes=make_test_mp4(duration_s=60.0), transcript_segments=segs
    )
    check(client, " ".join(s["text"] for s in segs), doc)


def test_image_keeps_ocr_text(client):
    from test_nexus_image import make_png_bytes

    ocr = prose(700, 5)
    doc = client.process_image("i", "scan.png", image_bytes=make_png_bytes(), ocr_text=ocr)
    check(client, ocr, doc)
