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

"""Encrypted PDFs for the reader tests: the standard security handler run forwards
(ISO 32000 algorithms 2-5 and 2.A/2.B), standard library plus ``pdf_crypt``'s ciphers."""

from __future__ import annotations

import hashlib
import os
import re

from nexus_processing.pdf_crypt import _PAD, _hash_r6, aes_cbc_encrypt, rc4

FILE_ID = bytes.fromhex("00112233445566778899aabbccddeeff")


def _owner_entry(owner: bytes, user: bytes, revision: int, n: int) -> bytes:
    key = hashlib.md5((owner + _PAD)[:32]).digest()
    if revision >= 3:
        for _ in range(50):
            key = hashlib.md5(key[:n]).digest()
    key = key[:n]
    x = rc4(key, (user + _PAD)[:32])
    if revision >= 3:
        for i in range(1, 20):
            x = rc4(bytes(b ^ i for b in key), x)
    return x


def _file_key(o: bytes, p: int, revision: int, n: int) -> bytes:
    key = hashlib.md5(_PAD + o + (p & 0xFFFFFFFF).to_bytes(4, "little") + FILE_ID).digest()
    if revision >= 3:
        for _ in range(50):
            key = hashlib.md5(key[:n]).digest()
    return key[:n]


def _user_entry(key: bytes, revision: int) -> bytes:
    if revision == 2:
        return rc4(key, _PAD)
    x = rc4(key, hashlib.md5(_PAD + FILE_ID).digest())
    for i in range(1, 20):
        x = rc4(bytes(b ^ i for b in key), x)
    return x + bytes(16)


def _pad(data: bytes) -> bytes:
    n = 16 - len(data) % 16
    return data + bytes([n]) * n


def _hex(b: bytes) -> str:
    return "<" + b.hex() + ">"


def encrypt_objects(
    objects: dict[int, bytes | str], method: str, user_password: bytes = b""
) -> tuple[dict[int, bytes], str]:
    """``objects`` with strings and streams encrypted; returns ``(objects, trailer extra)``.

    ``method``: ``rc4-40`` (R2), ``rc4-128`` (R3), ``aes-128`` (R4 AESV2) or ``aes-256``
    (R6 AESV3). A non-empty ``user_password`` makes a file that needs that password.
    """
    p = -3904
    if method == "aes-256":
        key = os.urandom(32)
        vs, ks = os.urandom(8), os.urandom(8)
        u = _hash_r6(user_password, vs, b"", 6) + vs + ks
        ue = aes_cbc_encrypt(_hash_r6(user_password, ks, b"", 6), bytes(16), key)
        ovs, oks = os.urandom(8), os.urandom(8)
        o = _hash_r6(b"owner", ovs, u, 6) + ovs + oks
        oe = aes_cbc_encrypt(_hash_r6(b"owner", oks, u, 6), bytes(16), key)
        enc = (
            f"<< /Filter /Standard /V 5 /R 6 /Length 256 /P {p} /O {_hex(o)} /U {_hex(u)} "
            f"/OE {_hex(oe)} /UE {_hex(ue)} /Perms {_hex(bytes(16))} "
            "/CF << /StdCF << /CFM /AESV3 /AuthEvent /DocOpen /Length 32 >> >> "
            "/StmF /StdCF /StrF /StdCF >>"
        )
    else:
        revision, n, v = {"rc4-40": (2, 5, 1), "rc4-128": (3, 16, 2), "aes-128": (4, 16, 4)}[method]
        o = _owner_entry(b"owner", user_password, revision, n)
        key = _file_key(o, p, revision, n)
        if user_password:  # a key from the real password: the empty one no longer matches
            padded = (user_password + _PAD)[:32]
            h = hashlib.md5(padded + o + (p & 0xFFFFFFFF).to_bytes(4, "little") + FILE_ID)
            key = h.digest()[:n]
            if revision >= 3:
                for _ in range(50):
                    key = hashlib.md5(key[:n]).digest()[:n]
        u = _user_entry(key, revision)
        cf = (
            " /CF << /StdCF << /CFM /AESV2 /Length 16 >> >> /StmF /StdCF /StrF /StdCF"
            if method == "aes-128"
            else ""
        )
        enc = (
            f"<< /Filter /Standard /V {v} /R {revision} /Length {n * 8} /P {p} "
            f"/O {_hex(o)} /U {_hex(u)}{cf} >>"
        )

    def object_key(num: int) -> bytes:
        if method == "aes-256":
            return key
        salt = b"sAlT" if method == "aes-128" else b""
        seed = key + num.to_bytes(3, "little") + (0).to_bytes(2, "little") + salt
        return hashlib.md5(seed).digest()[: min(len(key) + 5, 16)]

    def seal(num: int, data: bytes) -> bytes:
        if method.startswith("aes"):
            iv = os.urandom(16)
            return iv + aes_cbc_encrypt(object_key(num), iv, _pad(data))
        return rc4(object_key(num), data)

    out: dict[int, bytes] = {}
    for num, body in objects.items():
        raw = body.encode("latin-1") if isinstance(body, str) else body
        head, sep, rest = raw.partition(b"stream\n")
        if sep:
            data = rest[: rest.rindex(b"\nendstream")]
            sealed = seal(num, data)
            head = re.sub(rb"/Length \d+", b"/Length %d" % len(sealed), head)
            raw = head + sep + sealed + b"\nendstream"
        if not sep:  # literal strings of a plain object (streams were sealed whole)
            raw = re.sub(
                rb"\(([^()\\]*)\)", lambda m, num=num: _hex(seal(num, m.group(1))).encode(), raw
            )
        out[num] = raw
    enc_num = max(out) + 1
    out[enc_num] = enc.encode()
    return out, f" /Encrypt {enc_num} 0 R /ID [{_hex(FILE_ID)} {_hex(FILE_ID)}]"
