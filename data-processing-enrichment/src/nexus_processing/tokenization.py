# Copyright 2026 Veloxs AI Inc. All rights reserved.
#
# This file is part of Nexus, proprietary and confidential software of
# Veloxs AI Inc. Use is subject to the Nexus Proprietary Software License;
# see the LICENSE file in the project root. Unauthorized copying,
# distribution, or modification of this file, via any medium, is strictly
# prohibited.
#
# SPDX-License-Identifier: LicenseRef-Veloxs-AI-Proprietary
"""Reversible, format-preserving tokenization for sensitive numbers (e.g. PANs).

Implements NIST SP 800-38G **FF1** format-preserving encryption (AES-based) and a
PAN tokenizer on top of it:

- **Reversible** — ``detokenize_pan`` recovers the original with the key.
- **Format-preserving** — a 16-digit PAN tokenizes to a 16-digit value.
- **Deterministic** — same PAN + key → same token (referential integrity for joins
  and source↔target sync).
- **BIN / last-4 preserved** — first 6 and last 4 digits are kept for routing/display.
- **Optional Luhn-valid output** via cycle-walking.

The AES key is HKDF-derived from a secret that, in production, must come from a KMS/HSM
(here read from the ``NEXUS_FPE_KEY`` environment variable), never from config files.
"""
from __future__ import annotations

import math
import os

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

_HKDF_INFO = b"nexus-processing/fpe/v1"
_KEY_ENV = "NEXUS_FPE_KEY"


class TokenizationError(Exception):
    """Raised when a value cannot be tokenized or detokenized."""


# --- AES primitives -----------------------------------------------------------

def _aes_encrypt_block(key: bytes, block: bytes) -> bytes:
    enc = Cipher(algorithms.AES(key), modes.ECB()).encryptor()  # noqa: S305 - single-block PRP
    return enc.update(block) + enc.finalize()


def _prf(key: bytes, data: bytes) -> bytes:
    """CBC-MAC over 16-byte blocks with a zero IV (the FF1 PRF)."""
    y = b"\x00" * 16
    for i in range(0, len(data), 16):
        block = bytes(a ^ b for a, b in zip(y, data[i : i + 16]))
        y = _aes_encrypt_block(key, block)
    return y


def _num(numerals: list[int], radix: int) -> int:
    value = 0
    for d in numerals:
        value = value * radix + d
    return value


def _str(value: int, length: int, radix: int) -> list[int]:
    out = [0] * length
    for i in range(length - 1, -1, -1):
        out[i] = value % radix
        value //= radix
    return out


# --- NIST SP 800-38G FF1 ------------------------------------------------------

def _ff1(key: bytes, tweak: bytes, numerals: list[int], radix: int, *, encrypt: bool) -> list[int]:
    n = len(numerals)
    if n < 2:
        raise TokenizationError("FF1 requires at least 2 numerals")
    t = len(tweak)
    u = n // 2
    v = n - u
    a, b = numerals[:u], numerals[u:]
    bbytes = math.ceil(math.ceil(v * math.log2(radix)) / 8)
    d = 4 * math.ceil(bbytes / 4) + 4
    p = bytes([1, 2, 1]) + radix.to_bytes(3, "big") + bytes([10, u % 256]) + n.to_bytes(4, "big") + t.to_bytes(4, "big")
    pad = (-t - bbytes - 1) % 16

    rounds = range(10) if encrypt else range(9, -1, -1)
    for i in rounds:
        side = b if encrypt else a
        q = tweak + bytes(pad) + bytes([i]) + _num(side, radix).to_bytes(bbytes, "big")
        r = _prf(key, p + q)
        s = bytearray(r)
        j = 1
        while len(s) < d:
            s += _aes_encrypt_block(key, bytes(x ^ y for x, y in zip(r, j.to_bytes(16, "big"))))
            j += 1
        y_val = int.from_bytes(bytes(s[:d]), "big")
        m = u if i % 2 == 0 else v
        if encrypt:
            c = (_num(a, radix) + y_val) % (radix**m)
            a, b = b, _str(c, m, radix)
        else:
            c = (_num(b, radix) - y_val) % (radix**m)
            b, a = a, _str(c, m, radix)
    return a + b


def ff1_encrypt(key: bytes, tweak: bytes, numerals: list[int], radix: int = 10) -> list[int]:
    return _ff1(key, tweak, numerals, radix, encrypt=True)


def ff1_decrypt(key: bytes, tweak: bytes, numerals: list[int], radix: int = 10) -> list[int]:
    return _ff1(key, tweak, numerals, radix, encrypt=False)


# --- Luhn ---------------------------------------------------------------------

def luhn_check_digit(digits: list[int]) -> int:
    total = 0
    for index, digit in enumerate(reversed(digits)):
        doubled = digit * 2 if index % 2 == 0 else digit
        total += doubled - 9 if doubled > 9 else doubled
    return (10 - total % 10) % 10


def luhn_valid(digits: list[int]) -> bool:
    return luhn_check_digit(digits[:-1]) == digits[-1]


# --- PAN tokenizer ------------------------------------------------------------

def _load_key(secret: str | None) -> bytes:
    material = secret if secret is not None else os.environ.get(_KEY_ENV)
    if not material:
        raise TokenizationError(
            f"FPE key is required: pass secret= or set {_KEY_ENV} (sourced from KMS/HSM in prod)."
        )
    return HKDF(algorithm=hashes.SHA256(), length=16, salt=b"nexus-pan", info=_HKDF_INFO).derive(
        material.encode("utf-8")
    )


class PanTokenizer:
    """Format-preserving, reversible PAN tokenizer.

    Preserves the first ``bin_len`` and last ``last_len`` digits; format-preserving-
    encrypts the middle. With ``luhn=True`` the token also passes the Luhn check
    (via cycle-walking) while still preserving BIN and last-4.
    """

    def __init__(self, secret: str | None = None, *, bin_len: int = 6, last_len: int = 4,
                 luhn: bool = False) -> None:
        self._key = _load_key(secret)
        self.bin_len = bin_len
        self.last_len = last_len
        self.luhn = luhn

    def _split(self, pan: str) -> tuple[str, list[int], str]:
        if not pan.isdigit():
            raise TokenizationError("PAN must contain digits only (strip spaces/dashes first)")
        if len(pan) < self.bin_len + self.last_len + 2:
            raise TokenizationError("PAN too short to tokenize with the configured BIN/last-4")
        head = pan[: self.bin_len]
        tail = pan[len(pan) - self.last_len :]
        middle = [int(c) for c in pan[self.bin_len : len(pan) - self.last_len]]
        return head, middle, tail

    def _tweak(self, head: str, tail: str) -> bytes:
        # Bind the token to its BIN + last-4 so identical middles differ across cards.
        return (head + tail).encode("ascii")

    def _full_valid(self, head: str, middle: list[int], tail: str) -> bool:
        return luhn_valid([int(c) for c in head] + middle + [int(c) for c in tail])

    def tokenize(self, pan: str) -> str:
        head, middle, tail = self._split(pan)
        tweak = self._tweak(head, tail)
        out = ff1_encrypt(self._key, tweak, middle)
        if self.luhn:
            guard = 0
            while not self._full_valid(head, out, tail):
                out = ff1_encrypt(self._key, tweak, out)
                guard += 1
                if guard > 1000:
                    raise TokenizationError("cycle-walk did not converge")
        return head + "".join(str(d) for d in out) + tail

    def detokenize(self, token: str) -> str:
        head, middle, tail = self._split(token)
        tweak = self._tweak(head, tail)
        out = ff1_decrypt(self._key, tweak, middle)
        if self.luhn:
            guard = 0
            while not self._full_valid(head, out, tail):
                out = ff1_decrypt(self._key, tweak, out)
                guard += 1
                if guard > 1000:
                    raise TokenizationError("cycle-walk did not converge")
        return head + "".join(str(d) for d in out) + tail


def tokenize_pan(pan: str, secret: str | None = None, **kwargs) -> str:
    return PanTokenizer(secret, **kwargs).tokenize(pan)


def detokenize_pan(token: str, secret: str | None = None, **kwargs) -> str:
    return PanTokenizer(secret, **kwargs).detokenize(token)
