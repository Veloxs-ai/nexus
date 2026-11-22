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

"""Speed paths that must give exactly the old results: glyph advances, font decoding
tables, image byte transforms, hyphen re-joining, lazy OCR and image OCR de-duplication."""

from __future__ import annotations

import io
import random
import zipfile

from nexus_processing import images, ml_providers, office, pdf_content, pdf_filters, pdf_scan
from nexus_processing.pdf_content import _advance, _mul
from nexus_processing.pdf_fonts import PdfFont
from nexus_processing.pdf_layout import Line, hyphenated_words, page_markdown


def _advance_reference(tm, widths, spaces, size, tc, tw, th):
    for width, is_space in zip(widths, spaces, strict=True):
        advance = (width * size + tc + (tw if is_space else 0.0)) * th
        tm = _mul((1.0, 0.0, 0.0, 1.0, advance, 0.0), tm)
    return tm


def test_glyph_advances_are_bit_identical_to_per_glyph_matrix_products():
    rnd = random.Random(3)
    for _ in range(3000):
        tm = (
            *(rnd.choice([1.0, 0.0, -1.0, rnd.uniform(-3, 3)]) for _ in range(4)),
            rnd.uniform(-500, 500),
            rnd.uniform(-500, 500),
        )
        n = rnd.randint(0, 40)
        widths = tuple(rnd.choice([0.25, 0.5, 0.556, 0.278, rnd.uniform(0, 1)]) for _ in range(n))
        spaces = tuple(rnd.random() < 0.2 for _ in range(n))
        args = (
            rnd.uniform(1, 30),
            rnd.choice([0.0, 0.3]),
            rnd.choice([0.0, 1.5]),
            rnd.choice([1.0, 0.9]),
        )
        assert _advance(tm, widths, spaces, *args) == _advance_reference(tm, widths, spaces, *args)


def _font(**font):
    return PdfFont(font, lambda value: value)


def test_decode_run_matches_decode_for_simple_and_identity_fonts():
    simple = _font(Subtype="TrueType", FirstChar=32, Widths=[250 + i for i in range(95)])
    cid = _font(Subtype="Type0", DescendantFonts=[{"DW": 1000, "W": [1, [500, 600]]}])
    cid.to_unicode = {1: "A", 2: "B", 0x4E2D: "中"}
    cid._maps = None
    for font, samples in (
        (simple, [b"Hello, World!", bytes(range(256))]),
        (cid, [b"\x00\x01\x00\x02\x4e\x2d", b"\x00\x01\x00"]),
    ):
        for data in samples:
            parts = font.decode(data)
            text, widths, spaces = font.decode_run(data)
            assert text == "".join(p[0] for p in parts)
            assert widths == tuple(p[1] for p in parts)
            assert spaces == tuple(p[2] for p in parts)
            assert font.decode_run(data) is font.decode_run(data)  # memoised


def test_form_xobjects_are_decoded_once_per_document(monkeypatch):
    from nexus_processing.pdf_lexer import PdfRef, PdfStream

    calls = []
    monkeypatch.setattr(
        pdf_content, "decode_stream", lambda stream, resolve: calls.append(1) or stream.raw
    )

    class _Doc:
        def __init__(self):
            self.form_cache = {}

        def resolve(self, value):
            return value

    doc = _Doc()
    form = PdfStream({}, b"BT /F1 9 Tf (Letterhead) Tj ET")
    for _page in range(3):  # one interpreter per page, one cache per document
        interp = pdf_content._Interpreter(doc, {})
        assert interp._form_data(PdfRef(7, 0), form) == form.raw
    assert len(calls) == 1


def test_image_byte_transforms_match_the_per_byte_loops():
    rnd = random.Random(5)
    cmyk = bytes(rnd.randrange(256) for _ in range(4 * 2000 + 3))
    expected = bytearray()
    for i in range(0, len(cmyk) - 3, 4):
        c, m, y, k = cmyk[i : i + 4]
        expected += bytes((255 - min(255, c + k), 255 - min(255, m + k), 255 - min(255, y + k)))
    assert pdf_scan._cmyk_to_rgb(cmyk) == bytes(expected)
    cols = 50
    rows = [bytes(rnd.randrange(256) for _ in range(cols)) for _ in range(20)]
    data = b"".join(b"\x02" + r for r in rows)
    out, prev = bytearray(), bytearray(cols)
    for r in rows:
        prev = bytearray((a + b) & 0xFF for a, b in zip(r, prev, strict=True))
        out += prev
    assert pdf_filters._predict(data, {"Predictor": 12, "Columns": cols}) == bytes(out)


def test_hyphen_kept_only_for_compounds_the_document_writes():
    pages = [
        [
            Line("The user-level setting."),
            Line("Change the user-"),
            Line("level and the infor-"),
            Line("mation."),
        ]
    ]
    text, _ = page_markdown(pages[0], {}, hyphenated_words(pages))
    assert "user-level value" not in text and "user-level and the information." in text
    plain, _ = page_markdown(pages[0], {})
    assert "userlevel and the information." in plain  # without document evidence: joined


def test_easyocr_provider_construction_does_not_import_torch(monkeypatch):
    def boom():
        raise AssertionError("device resolved at construction")

    monkeypatch.setattr(ml_providers, "best_torch_device", boom)
    provider = ml_providers.EasyOCRProvider()
    assert provider._gpu is None and provider._reader is None


def test_ml_threads_reads_the_environment(monkeypatch):
    monkeypatch.setenv("NEXUS_ML_THREADS", "2")
    assert ml_providers.ml_threads() == 2
    monkeypatch.setenv("NEXUS_ML_THREADS", "zero")
    assert ml_providers.ml_threads() is None


class _CountingOCR:
    def __init__(self):
        self.calls = 0

    def extract_text(self, data):
        self.calls += 1
        return "INVOICE 42"


def _png(width, height):
    import struct
    import zlib

    raw = b"".join(b"\x00" + b"\xff" * (3 * width) for _ in range(height))

    def chunk(kind, body):
        return (
            struct.pack(">I", len(body)) + kind + body + struct.pack(">I", zlib.crc32(kind + body))
        )

    header = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", header)
        + chunk(b"IDAT", zlib.compress(raw))
        + chunk(b"IEND", b"")
    )


def test_icons_are_not_ocrd():
    ocr = _CountingOCR()
    images.process_image_binary(_png(16, 16), ocr_provider=ocr)
    assert ocr.calls == 0
    images.process_image_binary(_png(120, 40), ocr_provider=ocr)
    assert ocr.calls == 1


def test_duplicate_embedded_images_are_ocrd_once():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for name in ("a.png", "b.png"):
            z.writestr(f"word/media/{name}", _png(120, 40))
    ocr = _CountingOCR()
    texts = office._extract_images_from_zip(zipfile.ZipFile(buf), "word/media/", ocr)
    assert texts == ["[Image: a.png] INVOICE 42", "[Image: b.png] INVOICE 42"] and ocr.calls == 1


def test_video_without_demuxer_does_not_load_ocr(monkeypatch):
    from nexus_processing import video

    monkeypatch.setattr(ml_providers, "auto_detect_demuxer", lambda: None)
    monkeypatch.setattr(ml_providers, "auto_detect_transcriber", lambda: None)

    def no_ocr():
        raise AssertionError("OCR provider loaded without a demuxer")

    monkeypatch.setattr(ml_providers, "auto_detect_ocr_provider", no_ocr)
    try:
        video.process_video_binary(
            b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 64, filename="v.mp4", auto_extract=True
        )
    except AssertionError:
        raise
    except Exception:
        pass  # a malformed container may be rejected; OCR must still not have been loaded


def _penalty_reference(text):
    """The per-occurrence scoring loop that ``charset_detect._penalty`` memoises."""
    from nexus_processing.charset_detect import _word_penalty

    non_ascii, penalty, letters, han_words, spaced_han = 0, 0.0, {}, 0, 0
    for word in text.split():
        if word.isascii():
            continue
        word_penalty, word_non_ascii, han = _word_penalty(word, letters)
        penalty += word_penalty
        non_ascii += word_non_ascii
        if han:
            han_words += 1
            spaced_han += han <= 4
    if letters:
        penalty += 1.5 * (sum(letters.values()) - max(letters.values()))
    if han_words >= 4 and spaced_han >= 0.6 * han_words:
        penalty += 0.8 * non_ascii
    return penalty / max(1, non_ascii), non_ascii


def test_charset_word_memo_scores_exactly_like_the_per_word_loop():
    from nexus_processing.charset_detect import CANDIDATES, _penalty, _sample_text

    rnd = random.Random(11)
    words = ["Grüße", "Zażółć", "Привет", "Καλημέρα", "日本語", "한국어", "café", "naïve", "plain"]
    samples = [
        " ".join(rnd.choice(words) for _ in range(rnd.randint(1, 300))).encode(codec, "ignore")
        for codec in ("cp1252", "cp1250", "cp1251", "cp1253", "cp932", "euc_kr", "gb18030")
        for _ in range(6)
    ]
    samples += [bytes(rnd.randrange(256) for _ in range(rnd.randint(1, 2000))) for _ in range(60)]
    for sample in samples:
        for encoding in CANDIDATES:
            text = _sample_text(sample, encoding)
            if text is not None:
                assert _penalty(text) == _penalty_reference(text)


def test_stopword_index_counts_like_scanning_every_profile():
    from nexus_processing.language import _profiles, _stopword_index

    rnd = random.Random(19)
    vocabulary = [*sorted({w for stop in _profiles().values() for w in stop}), "zzz", "qwerty"]
    index = _stopword_index()
    for _ in range(300):
        words = [rnd.choice(vocabulary) for _ in range(rnd.randint(0, 80))]
        expected = {lang: sum(1 for w in words if w in stop) for lang, stop in _profiles().items()}
        got = dict.fromkeys(_profiles(), 0)
        for word in words:
            for lang in index.get(word, ()):
                got[lang] += 1
        assert list(got.items()) == list(expected.items())
