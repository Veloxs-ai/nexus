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

"""Word heading paths and content controls, PowerPoint tables as Markdown, OCR line order."""

from __future__ import annotations

import io
import zipfile

from nexus_processing.ml_providers import EasyOCRProvider, order_ocr_boxes
from nexus_processing.office import process_presentation_binary, process_word_binary

W = 'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"'


def _para(text: str, style: str = "") -> str:
    ppr = f'<w:pPr><w:pStyle w:val="{style}"/></w:pPr>' if style else ""
    return f"<w:p>{ppr}<w:r><w:t>{text}</w:t></w:r></w:p>"


def _docx(body: str) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr(
            "word/document.xml",
            f'<?xml version="1.0"?><w:document {W}><w:body>{body}</w:body></w:document>',
        )
    return buf.getvalue()


def test_word_sections_carry_the_heading_path_and_content_controls_are_read():
    body = (
        _para("Guide", "Heading1")
        + _para("Install", "Heading2")
        + _para("Run setup.")
        + "<w:sdt><w:sdtContent>"
        + _para("Clause inside a content control.")
        + "</w:sdtContent></w:sdt>"
        + _para("Usage", "Heading2")
        + _para("Open the app.")
    )
    chunks = process_word_binary(_docx(body), auto_extract=False).chunks
    by_text = {c.text: c for c in chunks}
    assert by_text["Run setup."].section_title == "Guide > Install"
    assert by_text["Clause inside a content control."].section_title == "Guide > Install"
    assert by_text["Open the app."].section_title == "Guide > Usage"


def test_pptx_tables_are_markdown_tables():
    p = "http://schemas.openxmlformats.org/presentationml/2006/main"
    a = "http://schemas.openxmlformats.org/drawingml/2006/main"
    cell = lambda t: f"<a:tc><a:txBody><a:p><a:r><a:t>{t}</a:t></a:r></a:p></a:txBody></a:tc>"  # noqa: E731
    slide = (
        f'<p:sld xmlns:p="{p}" xmlns:a="{a}"><p:cSld><p:spTree>'
        "<p:graphicFrame><a:graphic><a:graphicData>"
        f"<a:tbl><a:tr>{cell('Quarter')}{cell('Revenue')}</a:tr><a:tr>{cell('Q1')}{cell('$10M')}</a:tr></a:tbl>"
        "</a:graphicData></a:graphic></p:graphicFrame></p:spTree></p:cSld></p:sld>"
    )
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("ppt/slides/slide1.xml", slide)
    deck = process_presentation_binary(buf.getvalue(), auto_extract=False)
    assert "| Quarter | Revenue |\n| --- | --- |\n| Q1 | $10M |" in deck.slides[0].body_text


def test_ocr_boxes_become_lines_in_reading_order_with_confidence():
    results = [
        ([[200, 10], [260, 10], [260, 30], [200, 30]], "world", 0.8),
        ([[10, 12], [80, 12], [80, 28], [10, 28]], "Hello", 0.9),
        ([[10, 50], [90, 50], [90, 70], [10, 70]], "Next line", 0.2),
    ]
    assert order_ocr_boxes(results) == [("Hello world", 0.85), ("Next line", 0.2)]

    class Reader:
        def readtext(self, image, detail):
            assert detail == 1
            return results

    provider = EasyOCRProvider()
    provider._reader = Reader()
    assert provider.read_lines(b"img") == [("Hello world", 0.85), ("Next line", 0.2)]
    assert provider.extract_text(b"img") == "Hello world"  # the 0.2-confidence line is dropped
