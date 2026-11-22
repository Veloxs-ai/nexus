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

"""PDF decryption (standard security handler), two-column reading order, tiled scans and
the lazily loaded OCR engine."""

from __future__ import annotations

import pytest
from pdf_builders import build_pdf, stream, text_pages
from pdf_crypt_builders import encrypt_objects

from nexus_processing import ml_providers
from nexus_processing.pdf_crypt import aes_cbc_decrypt, aes_cbc_encrypt, rc4
from nexus_processing.pdf_extract import extract_pdf_pages
from nexus_processing.pdf_reader import PdfDocument

LINES = [
    [
        (72, 700, 12, "Quarterly statement for account holder"),
        (72, 680, 12, "Balance due 1,234.50"),
    ],
    [(72, 700, 12, "Second page mentions the refund policy"), (72, 680, 12, "Thank you")],
]


def _info(objects: dict) -> dict:
    objects = dict(objects)
    objects[90] = "<< /Title (Secured statement) /Author (Billing team) >>"
    return objects


# ---- ciphers -------------------------------------------------------------------------
def test_aes_matches_fips_197_vectors_both_ways():
    block = bytes.fromhex("00112233445566778899aabbccddeeff")
    for key, expected in (
        (bytes(range(16)), "69c4e0d86a7b0430d8cdb78070b4c55a"),
        (bytes(range(24)), "dda97ca4864cdfe06eaf70a0ec0d7191"),
        (bytes(range(32)), "8ea2b7ca516745bfeafc49904b496089"),
    ):
        sealed = aes_cbc_encrypt(key, bytes(16), block)
        assert sealed.hex() == expected
        assert aes_cbc_decrypt(key, sealed, bytes(16), unpad=False) == block


def test_aes_cbc_round_trip_strips_pkcs_padding_and_rc4_vector():
    key, iv = bytes(range(16)), bytes(range(16, 32))
    data = b"thirteen byte" + bytes([3]) * 3
    assert aes_cbc_decrypt(key, iv + aes_cbc_encrypt(key, iv, data)) == b"thirteen byte"
    assert rc4(b"Key", b"Plaintext").hex() == "bbf316e8d940af0ad3"


# ---- encrypted documents -------------------------------------------------------------
@pytest.mark.parametrize("method", ["rc4-40", "rc4-128", "aes-128", "aes-256"])
def test_empty_user_password_files_are_decrypted(method):
    objects, trailer = encrypt_objects(_info(text_pages(LINES)), method)
    data = build_pdf(objects, trailer=trailer, info=90)
    doc = PdfDocument(data)
    assert doc.encrypted and not doc.needs_password
    ex = extract_pdf_pages(data, auto_extract=False)
    text = "\n".join(p.text for p in ex.pages)
    assert "Quarterly statement for account holder" in text and "refund policy" in text
    assert [p.source for p in ex.pages] == ["text_layer", "text_layer"]
    assert ex.encrypted and ex.title == "Secured statement" and ex.author == "Billing team"


def test_encrypted_file_reads_like_the_plain_file():
    plain = extract_pdf_pages(build_pdf(text_pages(LINES)), auto_extract=False)
    objects, trailer = encrypt_objects(text_pages(LINES), "aes-128")
    sealed = extract_pdf_pages(build_pdf(objects, trailer=trailer), auto_extract=False)
    assert [p.text for p in sealed.pages] == [p.text for p in plain.pages]


@pytest.mark.parametrize("method", ["rc4-128", "aes-256"])
def test_file_that_needs_a_password_is_flagged_not_guessed(method):
    objects, trailer = encrypt_objects(text_pages(LINES), method, user_password=b"s3cret")
    data = build_pdf(objects, trailer=trailer)
    assert PdfDocument(data).needs_password
    pages = extract_pdf_pages(data, auto_extract=False).pages
    assert [p.source for p in pages] == ["encrypted", "encrypted"]
    assert all(p.text == "" for p in pages)


# ---- two-column pages ----------------------------------------------------------------
def _two_columns(row_wise: bool) -> tuple[bytes, list[str], list[str]]:
    left = [f"left column line {i} reads downwards" for i in range(10)]
    right = [f"right column line {i} goes on" for i in range(10)]
    lines = [(72, 740, 16, "Newsletter title across the page")]
    if row_wise:
        for i in range(10):
            lines += [(50, 700 - 14 * i, 10, left[i]), (320, 700 - 14 * i, 10, right[i])]
    else:
        lines += [(50, 700 - 14 * i, 10, t) for i, t in enumerate(left)]
        lines += [(320, 700 - 14 * i, 10, t) for i, t in enumerate(right)]
    return build_pdf(text_pages([lines])), left, right


@pytest.mark.parametrize("row_wise", [True, False])
def test_two_column_page_reads_left_column_then_right(row_wise):
    data, left, right = _two_columns(row_wise)
    text = extract_pdf_pages(data, auto_extract=False).pages[0].text
    body = [ln for ln in text.splitlines() if ln.strip() and not ln.startswith("#")]
    assert body == left + right


def test_table_rows_and_single_column_text_keep_their_order():
    rows = [(50, 700 - 14 * i, 10, f"Item {i}") for i in range(12)]
    cells = [(330, 700 - 14 * i, 10, f"{i}.00") for i in range(12)]
    table = [x for pair in zip(rows, cells, strict=True) for x in pair]
    text = extract_pdf_pages(build_pdf(text_pages([table])), auto_extract=False).pages[0].text
    assert text.splitlines()[:2] == ["Item 0 0.00", "Item 1 1.00"]
    prose = [
        (72, 700 - 14 * i, 10, f"a full width line of prose number {i} " * 2) for i in range(12)
    ]
    text = extract_pdf_pages(build_pdf(text_pages([prose])), auto_extract=False).pages[0].text
    assert text.splitlines()[0].startswith("a full width line of prose number 0")


# ---- tiled scans and lazy OCR --------------------------------------------------------
class TileOCR:
    def __init__(self) -> None:
        self.calls = 0

    def read_lines(self, image: bytes):
        self.calls += 1
        return [(f"strip {self.calls}", 0.8)]


def _tiled_scan(strips: int) -> bytes:
    gray = " /Subtype /Image /Width 4 /Height 1 /ColorSpace /DeviceGray /BitsPerComponent 8"
    objects: dict[int, bytes | str] = {
        1: "<< /Type /Catalog /Pages 2 0 R >>",
        2: "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
    }
    names = " ".join(f"/Im{i} {10 + i} 0 R" for i in range(strips))
    objects[3] = (
        "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R "
        f"/Resources << /XObject << {names} >> >> >>"
    )
    height = 792 / strips
    ops = [
        f"q 612 0 0 {height:.2f} 0 {792 - height * (i + 1):.2f} cm /Im{i} Do Q"
        for i in range(strips)
    ]
    objects[4] = stream("\n".join(ops).encode())
    for i in range(strips):
        objects[10 + i] = stream(bytes([i * 10] * 4), extra=gray)
    return build_pdf(objects)


def test_page_scanned_in_strips_is_ocrd_top_to_bottom():
    ocr = TileOCR()
    page = extract_pdf_pages(_tiled_scan(8), ocr_provider=ocr).pages[0]
    assert page.source == "ocr" and ocr.calls == 8
    assert page.text.splitlines() == [f"strip {i}" for i in range(1, 9)]
    assert page.ocr_confidence == 0.8


def test_ocr_engine_is_not_loaded_for_a_born_digital_pdf(monkeypatch):
    loads = []
    monkeypatch.setattr(ml_providers, "auto_detect_ocr_provider", lambda: loads.append(1))
    extract_pdf_pages(build_pdf(text_pages(LINES)))
    assert loads == []
    extract_pdf_pages(_tiled_scan(2))
    assert loads == [1]
