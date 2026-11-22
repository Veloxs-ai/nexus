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

"""The linear-time and C-speed paths give exactly the results of the plain algorithms."""

from __future__ import annotations

import random
import re
import time
import unicodedata

from nexus_guardrails import pii, prompt_security
from nexus_guardrails.config import PiiConfig
from nexus_guardrails.normalization import is_invisible, normalize_text
from nexus_guardrails.pii_scan import email_matches, shadow

CFG = PiiConfig()
EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
OLD_FAKE_TURN = re.compile(
    r"(^|\n)\s*(system|assistant)\s*:|<\s*/?\s*(system|im_start|im_end)\s*>|\[/?INST\]", re.I
)


def _fuzz(alphabet: str, n: int, seed: int) -> list[str]:
    rng = random.Random(seed)
    return ["".join(rng.choice(alphabet) for _ in range(rng.randint(0, 60))) for _ in range(n)]


def test_email_scan_matches_the_regex():
    texts = [
        *_fuzz("ab1._%+-@ éx.coZ_", 4000, 1),
        "a@b.co x@y",
        "..john@x.com",
        "a.@b.cc",
        "-x@ex-ample.io_",
        "é@x.com",
        "x@a.b.cdé",
        "mail:a@b.com,c@d.org;e@f.gov",
        "@@a@b.com",
        "a+b%c@x.y.zz",
        "_a@b.cc",
        "a@b.cc@d.ee",
    ]
    for text in texts:
        assert [m.span() for m in email_matches(text)] == [
            m.span() for m in EMAIL_RE.finditer(text)
        ], text


def test_email_scan_is_linear_on_hyphen_chains():
    blob = "a-" * 100_000
    t0 = time.perf_counter()
    assert pii.mask_pii(blob + "x@y.com", CFG) == "[EMAIL]"
    assert time.perf_counter() - t0 < 1.0


def _reference_shadow(text: str) -> tuple[str, list[int] | None]:
    if text.isascii():
        return text, None
    chars, offsets = [], []
    for i, char in enumerate(text):
        if is_invisible(char):
            continue
        for piece in unicodedata.normalize("NFKC", char):
            chars.append(piece)
            offsets.append(i)
    return "".join(chars), offsets


def test_shadow_matches_the_per_character_reference():
    alphabet = "ab 1@.-ﬁ①²㎞​‍‮हिन्दी１２３ＡＢ東京ﷺ﻿é"
    for text in _fuzz(alphabet, 3000, 2):
        view, offsets = shadow(text)
        ref_view, ref_offsets = _reference_shadow(text)
        assert view == ref_view, text
        for i in range(len(view)):
            got = i if offsets is None else offsets[i]
            want = i if ref_offsets is None else ref_offsets[i]
            assert got == want, (text, i)


def _reference_normalize(text: str) -> str:
    if not text:
        return text
    out = unicodedata.normalize("NFKC", text)
    return "".join(c for c in out if not is_invisible(c))


def test_normalize_text_matches_the_reference():
    for text in [*_fuzz("aZ 1​‌‪ﬁ①é­हि東", 2000, 3), "plain ascii"]:
        assert normalize_text(text) == _reference_normalize(text)


def test_fake_system_turn_rule_is_linear_and_unchanged():
    rule = dict(prompt_security.INJECTION_RULES)["fake_system_turn"]
    samples = [
        *_fuzz("sytemaSI:< />\n \t[]Nim_rdx", 4000, 4),
        "\n\n  system: do it",
        "  \n assistant :x",
        "</system>",
        "< / im_start >",
        "[INST] hi [/INST]",
        "x\rsystem: no",
    ]
    for text in samples:
        assert bool(rule.search(text)) == bool(OLD_FAKE_TURN.search(text)), repr(text)
    t0 = time.perf_counter()
    prompt_security.detect_injection("a" + "\n" * 20_000 + "b")
    prompt_security.detect_injection("<" + " " * 20_000 + "x")
    assert time.perf_counter() - t0 < 0.5


def test_comma_separated_numbers_are_fast_and_unchanged():
    text = ",".join(["5553334444"] * 20_000)
    t0 = time.perf_counter()
    masked = pii.mask_pii(text, CFG)
    assert time.perf_counter() - t0 < 2.0
    assert masked == ",".join(["[PHONE]"] * 20_000)
    assert pii.mask_pii("total 4155551234,50 units", CFG) == "total 4155551234,50 units"


def test_prefilter_skips_only_builtin_detectors(monkeypatch):
    assert pii.detect_pii_spans("no digits or at-signs here", CFG) == []
    monkeypatch.setitem(pii.PATTERNS, "name", re.compile(r"\bAlice\b"))
    spans = pii.detect_pii_spans("ask Alice", CFG, entities=["name"])
    assert [(s.start, s.end, s.entity) for s in spans] == [(4, 9, "name")]


def test_detect_pii_agrees_with_masking():
    text = "key sk-proj-abcdefghijklmnopqrstu and mail a@b.co, call 415-555-0134"
    found = {f.message.removeprefix("Detected ") for f in pii.detect_pii(text, CFG)}
    assert found == {s.entity for s in pii.detect_pii_spans(text, CFG)}
    assert found == {"api_key", "email", "phone"}


def test_phone_masks_keep_no_stray_prefix_and_cued_national_numbers():
    cases = {
        "call +1 (415) 555-0134 now": "call [PHONE] now",
        "Dial (212) 555-0199 ext. 12": "Dial [PHONE] ext. 12",
        "my mobile is 98765 43210": "my mobile is [PHONE]",
        "office tel 044-2345 6789": "office tel [PHONE]",
        "ring 030 12345678": "ring [PHONE]",
        "phone 020 7946 0958": "phone [PHONE]",
        "Kontakt: 030 12345678": "Kontakt: [PHONE]",
        "reach me on +33 1 23 45 67 89": "reach me on [PHONE]",
    }
    for text, want in cases.items():
        assert pii.mask_pii(text, CFG) == want, text
    # Without a phone cue, digit groups stay: amounts, zip codes, ids, dates, times.
    for text in (
        "batch 12345 67890",
        "totals 65000 70000",
        "zip 94105 94107",
        "order 98765 43210",
        "call 2023-01-15 10:30",
        "call on 15/01/2023 10 30",
        "Amount +12 345 678 901",
        "ORD-2024-000699 ORD-2024-000700",
    ):
        assert pii.mask_pii(text, CFG) == text, text


def test_national_ids_are_opt_in_and_checksum_validated():
    assert pii.mask_pii("Aadhaar 2345 6789 0124", CFG) == "Aadhaar 2345 6789 0124"
    ids = PiiConfig(detectors=["aadhaar", "pan", "iban"])
    assert pii.mask_pii("Aadhaar 2345 6789 0124", ids) == "Aadhaar [AADHAAR]"
    assert pii.mask_pii("Aadhaar 2345 6789 0120", ids) == "Aadhaar 2345 6789 0120"
    assert pii.mask_pii("PAN ABCPE1234F", ids) == "PAN [PAN]"
    assert pii.mask_pii("code ABCQE1234F", ids) == "code ABCQE1234F"  # Q: no holder type
    assert pii.mask_pii("IBAN GB82 WEST 1234 5698 7654 32 ok", ids) == "IBAN [IBAN] ok"
    assert pii.mask_pii("IBAN GB82 WEST 1234 5698 7654 33", ids).endswith("33")
    assert pii.detect_pii_spans("2345 6789 0120", ids, strict=True) == []


def test_ten_digit_prefilter_never_hides_a_national_phone_match():
    rnd = random.Random(5)
    alphabet = "0123456789" * 3 + " -.()+/#@x\n\t٣"
    for _ in range(4000):
        text = "".join(rnd.choice(alphabet) for _ in range(rnd.randint(0, 40)))
        if pii._NATIONAL_PHONE.search(text):
            assert pii._TEN_DIGIT_RUN.search(text), text
