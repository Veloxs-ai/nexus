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

"""Standard-library PDF reader: xref streams, object streams, fonts, layout, scans."""

from __future__ import annotations

import struct
import time
import zlib

import pytest
from pdf_builders import build_pdf, stream, text_pages

from nexus_processing.pdf import process_pdf_binary
from nexus_processing.pdf_extract import extract_pdf_pages
from nexus_processing.pdf_filters import apply_filters
from nexus_processing.pdf_fonts import glyph_to_unicode, parse_cmap
from nexus_processing.pdf_reader import PdfDocument, PdfError


def test_classic_xref_and_page_order_follow_the_page_tree():
    objects = text_pages([[(72, 700, 12, "first page")], [(72, 700, 12, "second page")]])
    # Kids listed in reverse object-number order: reading order is the tree, not object numbers.
    objects[2] = "<< /Type /Pages /Kids [6 0 R 4 0 R] /Count 2 >>"
    ex = extract_pdf_pages(build_pdf(objects), auto_extract=False)
    assert [p.text for p in ex.pages] == ["second page", "first page"]
    assert ex.repaired is False


def test_xref_stream_and_object_stream():
    objects = text_pages([[(72, 700, 12, "compressed objects work")]])
    data = build_pdf(objects, xref_stream=True, compress_into={20: [1, 2, 3, 4]})
    doc = PdfDocument(data)
    assert doc.xref[1][0] == 2  # catalog lives in object stream 20
    assert extract_pdf_pages(data, auto_extract=False).pages[0].text == "compressed objects work"


def test_broken_xref_is_rebuilt_by_scanning():
    data = build_pdf(text_pages([[(72, 700, 12, "recovered text")]]))
    data = data.replace(b"startxref", b"startxrxf")
    ex = extract_pdf_pages(data, auto_extract=False)
    assert ex.repaired is True and ex.pages[0].text == "recovered text"


def test_not_a_pdf_raises_and_legacy_path_handles_it():
    with pytest.raises(PdfError):
        PdfDocument(b"hello")
    assert process_pdf_binary(b"%PDF-1.4 garbage").pages  # legacy scanner: no exception


def test_type0_font_with_tounicode_cmap_and_cid_widths():
    cmap = (
        b"/CIDInit /ProcSet findresource begin 12 dict begin begincmap\n"
        b"1 begincodespacerange <0000> <FFFF> endcodespacerange\n"
        b"2 beginbfchar <0001> <0048> <0002> <0069> endbfchar\n"
        b"1 beginbfrange <0003> <0004> [<0020> <0915094D>] endbfrange\n"
        b"endcmap CMapName currentdict /CMap defineresource pop end end"
    )
    objects = {
        1: "<< /Type /Catalog /Pages 2 0 R >>",
        2: "<< /Type /Pages /Kids [4 0 R] /Count 1 >>",
        3: "<< /Type /Font /Subtype /Type0 /BaseFont /ABC+Noto /Encoding /Identity-H "
        "/DescendantFonts [6 0 R] /ToUnicode 7 0 R >>",
        4: "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 5 0 R "
        "/Resources << /Font << /F1 3 0 R >> >> >>",
        5: stream(b"BT /F1 10 Tf 72 700 Td <0001000200030004> Tj ET"),
        6: "<< /Type /Font /Subtype /CIDFontType2 /BaseFont /ABC+Noto /DW 500 /W [1 [600 300]] >>",
        7: stream(cmap),
    }
    text = extract_pdf_pages(build_pdf(objects), auto_extract=False).pages[0].text
    assert text == "Hi क्"


def test_differences_encoding_and_glyph_names():
    assert glyph_to_unicode("quoteright") == "’"
    assert glyph_to_unicode("uni20AC") == "€"
    assert glyph_to_unicode("eacute") == "é"
    assert glyph_to_unicode("fi") == "fi"
    objects = text_pages([[(72, 700, 12, "x")]])
    objects[3] = (
        "<< /Type /Font /Subtype /Type1 /BaseFont /Times "
        "/Encoding << /BaseEncoding /WinAnsiEncoding "
        "/Differences [120 /eacute] >> >>"
    )
    assert extract_pdf_pages(build_pdf(objects), auto_extract=False).pages[0].text == "é"


def test_cmap_ranges_with_offsets():
    mapping, spaces = parse_cmap(
        b"1 begincodespacerange <00> <FF> endcodespacerange "
        b"1 beginbfrange <41> <43> <0061> endbfrange"
    )
    assert mapping == {0x41: "a", 0x42: "b", 0x43: "c"} and spaces == [(1, 0, 255)]


def test_tj_kerning_gap_becomes_a_space_and_runs_join_into_lines():
    objects = text_pages([[(72, 700, 12, "x")]])
    objects[5] = stream(
        b"BT /F1 12 Tf 72 700 Td [(Hello) -400 (world)] TJ ET "
        b"BT /F1 12 Tf 72 680 Td (next line) Tj ET"
    )
    assert (
        extract_pdf_pages(build_pdf(objects), auto_extract=False).pages[0].text
        == "Hello world\nnext line"
    )


def test_running_headers_footers_and_page_numbers_are_removed():
    pages = [
        [
            (72, 760, 9, "ACME Corp - Confidential"),
            (72, 700, 11, f"Body text of page {n} with content."),
            (300, 30, 9, f"Page {n} of 5"),
        ]
        for n in range(1, 6)
    ]
    ex = extract_pdf_pages(build_pdf(text_pages(pages)), auto_extract=False)
    assert ex.running_lines_removed == 10
    assert all("Confidential" not in p.text and "of 5" not in p.text for p in ex.pages)
    assert ex.pages[2].text == "Body text of page 3 with content."


def test_headings_from_font_size_become_markdown_and_paths():
    pages = [
        [
            (72, 740, 20, "Annual Report"),
            (72, 700, 11, "Intro paragraph one."),
            (72, 686, 11, "More intro."),
        ],
        [(72, 740, 15, "Results"), (72, 700, 11, "Revenue grew."), (72, 686, 11, "Costs fell.")],
        [(72, 700, 11, "Continued results text."), (72, 686, 11, "And more text.")],
    ]
    ex = extract_pdf_pages(build_pdf(text_pages(pages)), auto_extract=False)
    assert ex.pages[0].text.startswith("# Annual Report")
    assert ex.pages[1].text.startswith("## Results")
    assert ex.pages[2].heading_path == ["Annual Report", "Results"]


def test_hyphenated_words_are_rejoined():
    pages = [
        [
            (72, 700, 11, "the infor-"),
            (72, 686, 11, "mation is here"),
            (72, 672, 11, "COVID-"),
            (72, 658, 11, "19 stays"),
        ]
    ]
    text = extract_pdf_pages(build_pdf(text_pages(pages)), auto_extract=False).pages[0].text
    assert "information is here" in text and "COVID-\n19" in text


def _scan_pdf(image_stream: bytes) -> bytes:
    objects = {
        1: "<< /Type /Catalog /Pages 2 0 R >>",
        2: "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        3: "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R "
        "/Resources << /XObject << /Im0 5 0 R >> >> >>",
        4: stream(b"q 612 0 0 792 0 0 cm /Im0 Do Q"),
        5: image_stream,
    }
    return build_pdf(objects)


class FakeOCR:
    def __init__(self) -> None:
        self.images: list[bytes] = []

    def read_lines(self, image: bytes):
        self.images.append(image)
        return [("Scanned invoice 42", 0.91), ("noise", 0.1)]


def test_scanned_page_is_ocrd_with_confidence_from_a_png_wrapped_flate_image():
    pixels = bytes([255] * 16)
    image = stream(
        pixels,
        extra=" /Type /XObject /Subtype /Image /Width 4 /Height 4 /ColorSpace /DeviceGray "
        "/BitsPerComponent 8",
    )
    ocr = FakeOCR()
    page = extract_pdf_pages(_scan_pdf(image), ocr_provider=ocr).pages[0]
    assert (
        page.source == "ocr" and page.text == "Scanned invoice 42" and page.ocr_confidence == 0.91
    )
    assert ocr.images[0].startswith(b"\x89PNG")


def test_scanned_page_without_ocr_is_flagged_and_jbig2_is_unsupported():
    jpeg = stream(
        b"\xff\xd8\xff\xe0fakejpeg",
        compress=False,
        extra=" /Subtype /Image /Width 10 /Height 10 /Filter /DCTDecode",
    )
    page = extract_pdf_pages(_scan_pdf(jpeg), auto_extract=False).pages[0]
    assert page.source == "needs_ocr" and page.text == ""
    jbig2 = stream(
        b"\x00\x01",
        compress=False,
        extra=" /Subtype /Image /Width 10 /Height 10 /Filter /JBIG2Decode",
    )
    assert (
        extract_pdf_pages(_scan_pdf(jbig2), ocr_provider=FakeOCR()).pages[0].source
        == "ocr_unsupported"
    )


def test_ccitt_scan_is_wrapped_as_tiff():
    fax = stream(
        b"\x00" * 8,
        compress=False,
        extra=" /Subtype /Image /Width 8 /Height 8 /Filter /CCITTFaxDecode "
        "/DecodeParms << /K -1 /Columns 8 /Rows 8 >>",
    )
    ocr = FakeOCR()
    extract_pdf_pages(_scan_pdf(fax), ocr_provider=ocr)
    tiff = ocr.images[0]
    assert tiff.startswith(b"II*\x00")
    entries = struct.unpack("<H", tiff[8:10])[0]
    assert entries >= 9


def test_external_page_texts_are_cleaned_and_scans_still_ocrd():
    pdf = _scan_pdf(
        stream(
            bytes([0] * 16),
            extra=" /Subtype /Image /Width 4 /Height 4 /ColorSpace /DeviceGray /BitsPerComponent 8",
        )
    )
    ocr = FakeOCR()
    ex = extract_pdf_pages(pdf, page_texts=lambda data: [""], ocr_provider=ocr)
    assert ex.pages[0].source == "ocr"
    texts = ["Header X\nreal text one", "Header X\nreal text two", "Header X\nreal text three"]
    ex = extract_pdf_pages(b"not a pdf", page_texts=texts, auto_extract=False)
    assert [p.text for p in ex.pages] == ["real text one", "real text two", "real text three"]


def test_filters_lzw_ascii85_asciihex_runlength_and_png_predictor():
    assert apply_filters(b"68656c6c6f>", [("ASCIIHexDecode", {})]) == b"hello"
    assert apply_filters(b"<~BOu!rDZ~>", [("ASCII85Decode", {})]) == b"hello"
    assert apply_filters(b"\x02abc\xfeZ\x80", [("RunLengthDecode", {})]) == b"abcZZZ"
    assert (
        apply_filters(
            bytes([0x80, 0x0B, 0x60, 0x50, 0x22, 0x0C, 0x0C, 0x85, 0x01]), [("LZWDecode", {})]
        )
        == b"-----A---B"
    )
    rows = bytes([2, 1, 2, 3]) + bytes([2, 1, 1, 1])  # "Up" filter: second row adds the first
    out = apply_filters(zlib.compress(rows), [("FlateDecode", {"Predictor": 12, "Columns": 3})])
    assert out == bytes([1, 2, 3, 2, 3, 4])


def test_damaged_flate_keeps_what_inflated():
    seed, raw_list = 12345, []
    for _ in range(20000):
        seed = (seed * 1103515245 + 12345) & 0x7FFFFFFF
        raw_list.append((seed >> 16) & 0xFF)
    raw = bytes(raw_list)
    data = zlib.compress(raw)
    damaged = data[: len(data) // 2] + b"\x00\xff" * 50 + data[len(data) // 2 :]
    out = apply_filters(damaged, [("FlateDecode", {})])
    assert len(out) >= 4096 and out[:4096] == raw[:4096]  # everything before the damage survives


def test_benchmark_many_pages_are_read_linearly():
    pages = [
        [
            (72, 700 - 14 * i, 10, f"Line {i} has several words and value {(i + 1) * (n + 1) * 7}.")
            for i in range(40)
        ]
        for n in range(60)
    ]
    data = build_pdf(text_pages(pages))
    started = time.perf_counter()
    ex = extract_pdf_pages(data, auto_extract=False)
    elapsed = time.perf_counter() - started
    assert len(ex.pages) == 60 and all(p.text.count("\n") >= 39 for p in ex.pages)
    assert elapsed < 5.0  # ~0.3 s on a laptop; the regex scanner took minutes on large files


def test_pages_another_engine_left_empty_are_read_by_nexus():
    data = build_pdf(
        text_pages([[(72, 700, 12, "Text the other engine missed")], [(72, 700, 12, "kept")]])
    )
    ex = extract_pdf_pages(data, page_texts=["", "external page two text"], auto_extract=False)
    assert ex.pages[0].text == "Text the other engine missed" and ex.pages[0].source == "text_layer"
    assert ex.pages[1].text == "external page two text" and ex.pages[1].source == "external"
