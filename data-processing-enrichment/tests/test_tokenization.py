# Copyright 2026 Veloxs AI Inc. All rights reserved.
#
# This file is part of Nexus, proprietary and confidential software of
# Veloxs AI Inc. Use is subject to the Nexus Proprietary Software License;
# see the LICENSE file in the project root. Unauthorized copying,
# distribution, or modification of this file, via any medium, is strictly
# prohibited.
#
# SPDX-License-Identifier: LicenseRef-Veloxs-AI-Proprietary
import pytest

from nexus_processing.tokenization import (
    PanTokenizer,
    TokenizationError,
    detokenize_pan,
    ff1_decrypt,
    ff1_encrypt,
    luhn_valid,
    tokenize_pan,
)

_NIST_KEY = bytes.fromhex("2B7E151628AED2A6ABF7158809CF4F3C")
SECRET = "unit-test-fpe-secret"


# --- FF1 correctness against NIST SP 800-38G sample vectors -------------------

def test_ff1_nist_vector_no_tweak():
    pt = [0, 1, 2, 3, 4, 5, 6, 7, 8, 9]
    ct = ff1_encrypt(_NIST_KEY, b"", pt, radix=10)
    assert ct == [2, 4, 3, 3, 4, 7, 7, 4, 8, 4]
    assert ff1_decrypt(_NIST_KEY, b"", ct, radix=10) == pt


def test_ff1_nist_vector_with_tweak():
    tweak = bytes.fromhex("3938373635343332313029")[:10]  # b"9876543210"
    pt = [0, 1, 2, 3, 4, 5, 6, 7, 8, 9]
    ct = ff1_encrypt(_NIST_KEY, b"9876543210", pt, radix=10)
    assert ct == [6, 1, 2, 4, 2, 0, 0, 7, 7, 3]
    assert ff1_decrypt(_NIST_KEY, b"9876543210", ct, radix=10) == pt


def test_ff1_roundtrip_various_lengths():
    for n in (2, 6, 9, 19):
        pt = [(i * 7 + 3) % 10 for i in range(n)]
        ct = ff1_encrypt(_NIST_KEY, b"tw", pt)
        assert ff1_decrypt(_NIST_KEY, b"tw", ct) == pt


# --- PAN tokenizer -----------------------------------------------------------

def test_roundtrip_and_format_preserved():
    pan = "4242424242424242"
    token = tokenize_pan(pan, SECRET)
    assert len(token) == len(pan) and token.isdigit()
    assert token != pan
    assert detokenize_pan(token, SECRET) == pan


def test_bin_and_last4_preserved():
    pan = "5500005555555559"
    token = tokenize_pan(pan, SECRET)
    assert token[:6] == pan[:6]    # BIN preserved
    assert token[-4:] == pan[-4:]  # last 4 preserved


def test_deterministic():
    pan = "4000056655665556"
    assert tokenize_pan(pan, SECRET) == tokenize_pan(pan, SECRET)


def test_distinct_pans_distinct_tokens():
    a = tokenize_pan("4242424242424242", SECRET)
    b = tokenize_pan("4242424242424259", SECRET)
    assert a != b


def test_luhn_mode_outputs_valid_card_and_roundtrips():
    pan = "4242424242424242"
    tok = PanTokenizer(SECRET, luhn=True)
    token = tok.tokenize(pan)
    assert luhn_valid([int(c) for c in token])      # token passes Luhn
    assert token[:6] == pan[:6] and token[-4:] == pan[-4:]
    assert tok.detokenize(token) == pan


def test_wrong_key_does_not_recover():
    token = tokenize_pan("4242424242424242", SECRET)
    assert detokenize_pan(token, "a-different-secret") != "4242424242424242"


def test_requires_key():
    with pytest.raises(TokenizationError):
        tokenize_pan("4242424242424242", None)


def test_rejects_non_digits_and_short_pan():
    with pytest.raises(TokenizationError):
        tokenize_pan("4242-4242-4242-4242", SECRET)
    with pytest.raises(TokenizationError):
        tokenize_pan("123456789", SECRET)  # too short for BIN6 + last4
