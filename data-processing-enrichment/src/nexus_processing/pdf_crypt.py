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

"""PDF standard security handler (ISO 32000-1 §7.6.3, ISO 32000-2 §7.6.4), stdlib only.

Most "secured" PDFs (statements, government forms) are encrypted with an empty user
password: anyone may open them, the encryption only carries permission flags. This
module derives the file key for such files and decrypts strings and streams:

- revisions 2-4 (RC4 40-128 bit, AESV2 = AES-128) and 5-6 (AESV3 = AES-256), with
  crypt filters (``/CF``, ``/StmF``, ``/StrF``, ``Identity``);
- the empty user password, then the empty owner password, is tried; a file that needs a
  real password reports ``needs_password`` (its text is not guessed).

RC4 and AES are implemented here (key schedules and T-table AES); key derivation uses
``hashlib`` (MD5, SHA-256/384/512).
"""

from __future__ import annotations

import hashlib
import struct
from typing import Any

__all__ = ["SecurityHandler", "aes_cbc_decrypt", "aes_cbc_encrypt", "rc4"]

_PAD = bytes.fromhex("28BF4E5E4E758A4164004E56FFFA01082E2E00B6D0683E802F0CA9FE6453697A")


# --------------------------------------------------------------------------------------
# RC4
# --------------------------------------------------------------------------------------
def rc4(key: bytes, data: bytes) -> bytes:
    """RC4 keystream XOR ``data`` (encryption and decryption are the same)."""
    s = list(range(256))
    j = 0
    klen = len(key) or 1
    for i in range(256):
        j = (j + s[i] + key[i % klen]) & 0xFF
        s[i], s[j] = s[j], s[i]
    out = bytearray(len(data))
    i = j = 0
    for n, byte in enumerate(data):
        i = (i + 1) & 0xFF
        si = s[i]
        j = (j + si) & 0xFF
        sj = s[j]
        s[i], s[j] = sj, si
        out[n] = byte ^ s[(si + sj) & 0xFF]
    return bytes(out)


# --------------------------------------------------------------------------------------
# AES (FIPS-197), T-table implementation
# --------------------------------------------------------------------------------------
def _xtime(a: int) -> int:
    a <<= 1
    return a ^ 0x11B if a & 0x100 else a


def _gmul(a: int, b: int) -> int:
    r = 0
    while b:
        if b & 1:
            r ^= a
        a = _xtime(a)
        b >>= 1
    return r


def _tables() -> tuple[list[int], list[int], list[list[int]], list[list[int]]]:
    inv = [0] * 256
    for a in range(1, 256):
        r, base, e = 1, a, 254
        while e:
            if e & 1:
                r = _gmul(r, base)
            base = _gmul(base, base)
            e >>= 1
        inv[a] = r
    sbox = [0] * 256
    for a in range(256):
        b = inv[a]
        s = b
        for shift in range(1, 5):
            s ^= ((b << shift) | (b >> (8 - shift))) & 0xFF
        sbox[a] = s ^ 0x63
    sinv = [0] * 256
    for a, s in enumerate(sbox):
        sinv[s] = a

    def ror(w: int, n: int) -> int:
        return ((w >> n) | (w << (32 - n))) & 0xFFFFFFFF

    te0 = [(_gmul(s, 2) << 24) | (s << 16) | (s << 8) | _gmul(s, 3) for s in sbox]
    td0 = [
        (_gmul(s, 14) << 24) | (_gmul(s, 9) << 16) | (_gmul(s, 13) << 8) | _gmul(s, 11)
        for s in sinv
    ]
    te = [te0] + [[ror(w, n) for w in te0] for n in (8, 16, 24)]
    td = [td0] + [[ror(w, n) for w in td0] for n in (8, 16, 24)]
    return sbox, sinv, te, td


_SBOX, _SINV, _TE, _TD = _tables()


def _expand(key: bytes) -> tuple[list[int], list[int], int]:
    """(encryption round keys, decryption round keys, rounds) for a 16/24/32-byte key."""
    nk = len(key) // 4
    if len(key) not in (16, 24, 32):
        raise ValueError("AES key must be 16, 24 or 32 bytes")
    rounds = nk + 6
    w = list(struct.unpack(f">{nk}I", key))
    rcon = 1
    sb = _SBOX
    for i in range(nk, 4 * (rounds + 1)):
        t = w[i - 1]
        if i % nk == 0:
            t = ((t << 8) | (t >> 24)) & 0xFFFFFFFF
            t = (
                (sb[t >> 24] << 24)
                | (sb[(t >> 16) & 255] << 16)
                | (sb[(t >> 8) & 255] << 8)
                | sb[t & 255]
            )
            t ^= rcon << 24
            rcon = _xtime(rcon)
        elif nk > 6 and i % nk == 4:
            t = (
                (sb[t >> 24] << 24)
                | (sb[(t >> 16) & 255] << 16)
                | (sb[(t >> 8) & 255] << 8)
                | sb[t & 255]
            )
        w.append(w[i - nk] ^ t)
    td0, td1, td2, td3 = _TD
    dk: list[int] = []
    for r in range(rounds, -1, -1):
        block = w[4 * r : 4 * r + 4]
        if 0 < r < rounds:  # equivalent inverse cipher: InvMixColumns on the middle keys
            block = [
                td0[sb[x >> 24]]
                ^ td1[sb[(x >> 16) & 255]]
                ^ td2[sb[(x >> 8) & 255]]
                ^ td3[sb[x & 255]]
                for x in block
            ]
        dk.extend(block)
    return w, dk, rounds


def _encrypt_block(rk: list[int], rounds: int, s0: int, s1: int, s2: int, s3: int) -> tuple:
    te0, te1, te2, te3 = _TE
    s0 ^= rk[0]
    s1 ^= rk[1]
    s2 ^= rk[2]
    s3 ^= rk[3]
    k = 4
    for _ in range(rounds - 1):
        t0 = te0[s0 >> 24] ^ te1[(s1 >> 16) & 255] ^ te2[(s2 >> 8) & 255] ^ te3[s3 & 255] ^ rk[k]
        t1 = (
            te0[s1 >> 24] ^ te1[(s2 >> 16) & 255] ^ te2[(s3 >> 8) & 255] ^ te3[s0 & 255] ^ rk[k + 1]
        )
        t2 = (
            te0[s2 >> 24] ^ te1[(s3 >> 16) & 255] ^ te2[(s0 >> 8) & 255] ^ te3[s1 & 255] ^ rk[k + 2]
        )
        t3 = (
            te0[s3 >> 24] ^ te1[(s0 >> 16) & 255] ^ te2[(s1 >> 8) & 255] ^ te3[s2 & 255] ^ rk[k + 3]
        )
        s0, s1, s2, s3 = t0, t1, t2, t3
        k += 4
    sb = _SBOX

    def last(a: int, b: int, c: int, d: int, key: int) -> int:
        return ((sb[a >> 24] << 24) | (sb[(b >> 16) & 255] << 16) | (sb[(c >> 8) & 255] << 8)
                | sb[d & 255]) ^ key  # fmt: skip

    return (
        last(s0, s1, s2, s3, rk[k]),
        last(s1, s2, s3, s0, rk[k + 1]),
        last(s2, s3, s0, s1, rk[k + 2]),
        last(s3, s0, s1, s2, rk[k + 3]),
    )


def _decrypt_block(dk: list[int], rounds: int, s0: int, s1: int, s2: int, s3: int) -> tuple:
    td0, td1, td2, td3 = _TD
    s0 ^= dk[0]
    s1 ^= dk[1]
    s2 ^= dk[2]
    s3 ^= dk[3]
    k = 4
    for _ in range(rounds - 1):
        t0 = td0[s0 >> 24] ^ td1[(s3 >> 16) & 255] ^ td2[(s2 >> 8) & 255] ^ td3[s1 & 255] ^ dk[k]
        t1 = (
            td0[s1 >> 24] ^ td1[(s0 >> 16) & 255] ^ td2[(s3 >> 8) & 255] ^ td3[s2 & 255] ^ dk[k + 1]
        )
        t2 = (
            td0[s2 >> 24] ^ td1[(s1 >> 16) & 255] ^ td2[(s0 >> 8) & 255] ^ td3[s3 & 255] ^ dk[k + 2]
        )
        t3 = (
            td0[s3 >> 24] ^ td1[(s2 >> 16) & 255] ^ td2[(s1 >> 8) & 255] ^ td3[s0 & 255] ^ dk[k + 3]
        )
        s0, s1, s2, s3 = t0, t1, t2, t3
        k += 4
    si = _SINV

    def last(a: int, b: int, c: int, d: int, key: int) -> int:
        return ((si[a >> 24] << 24) | (si[(b >> 16) & 255] << 16) | (si[(c >> 8) & 255] << 8)
                | si[d & 255]) ^ key  # fmt: skip

    return (
        last(s0, s3, s2, s1, dk[k]),
        last(s1, s0, s3, s2, dk[k + 1]),
        last(s2, s1, s0, s3, dk[k + 2]),
        last(s3, s2, s1, s0, dk[k + 3]),
    )


_WORDS4 = struct.Struct(">4I")


def aes_cbc_encrypt(key: bytes, iv: bytes, data: bytes) -> bytes:
    """AES-CBC encryption of ``data`` (a multiple of 16 bytes; no padding is added)."""
    rk, _dk, rounds = _expand(key)
    c0, c1, c2, c3 = _WORDS4.unpack(iv)
    out = bytearray()
    for pos in range(0, len(data) - len(data) % 16, 16):
        p0, p1, p2, p3 = _WORDS4.unpack_from(data, pos)
        c0, c1, c2, c3 = _encrypt_block(rk, rounds, p0 ^ c0, p1 ^ c1, p2 ^ c2, p3 ^ c3)
        out += _WORDS4.pack(c0, c1, c2, c3)
    return bytes(out)


def aes_cbc_decrypt(key: bytes, data: bytes, iv: bytes | None = None, unpad: bool = True) -> bytes:
    """AES-CBC decryption. Without ``iv`` the first 16 bytes of ``data`` are the IV (the
    PDF layout). ``unpad`` removes valid PKCS#5 padding (invalid padding is kept)."""
    if iv is None:
        iv, data = data[:16], data[16:]
    if len(iv) < 16:
        return b""
    _rk, dk, rounds = _expand(key)
    v0, v1, v2, v3 = _WORDS4.unpack(iv)
    out = bytearray()
    for pos in range(0, len(data) - len(data) % 16, 16):
        c = _WORDS4.unpack_from(data, pos)
        d0, d1, d2, d3 = _decrypt_block(dk, rounds, *c)
        out += _WORDS4.pack(d0 ^ v0, d1 ^ v1, d2 ^ v2, d3 ^ v3)
        v0, v1, v2, v3 = c
    if unpad and out:
        n = out[-1]
        if 1 <= n <= 16 and out[-n:] == bytes([n]) * n:
            del out[-n:]
    return bytes(out)


# --------------------------------------------------------------------------------------
# Standard security handler
# --------------------------------------------------------------------------------------
def _hash_r6(password: bytes, salt: bytes, udata: bytes, revision: int) -> bytes:
    """ISO 32000-2 Algorithm 2.B (revision 6); revision 5 is the plain SHA-256."""
    k = hashlib.sha256(password + salt + udata).digest()
    if revision < 6:
        return k
    i = 0
    while True:
        k1 = (password + k + udata) * 64
        e = aes_cbc_encrypt(k[:16], k[16:32], k1)
        k = (hashlib.sha256, hashlib.sha384, hashlib.sha512)[sum(e[:16]) % 3](e).digest()
        i += 1
        if i >= 64 and e[-1] <= i - 32:
            return k[:32]


def _num(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


class SecurityHandler:
    """Decrypts one document's strings and streams (see the module docstring).

    ``key`` is None when no empty password opens the file (``needs_password``) or the
    handler is not the standard one (``supported`` is False).
    """

    def __init__(self, encrypt: dict[str, Any], file_id: bytes) -> None:
        self.encrypt = encrypt
        self.supported = str(encrypt.get("Filter") or "Standard") == "Standard"
        self.version = _num(encrypt.get("V"), 0)
        self.revision = _num(encrypt.get("R"), 2)
        self.encrypt_metadata = encrypt.get("EncryptMetadata", True) is not False
        self.stream_method, self.string_method = self._methods()
        bits = _num(encrypt.get("Length"), 40)
        self.length = max(5, min(16, bits // 8 if bits > 16 else bits)) if self.version >= 2 else 5
        self.key: bytes | None = None
        if self.supported and self.stream_method != "unsupported":
            try:
                self.key = self._file_key(file_id)
            except (ValueError, TypeError, IndexError):
                self.key = None

    @property
    def needs_password(self) -> bool:
        return self.key is None

    # ---- methods ------------------------------------------------------------------
    def _methods(self) -> tuple[str, str]:
        if self.version in (1, 2, 3):
            return "rc4", "rc4"
        if self.version not in (4, 5):
            return "unsupported", "unsupported"
        filters = self.encrypt.get("CF") if isinstance(self.encrypt.get("CF"), dict) else {}

        def method(name: Any) -> str:
            name = str(name or "Identity")
            if name == "Identity":
                return "identity"
            cf = filters.get(name) if isinstance(filters.get(name), dict) else {}
            cfm = str(cf.get("CFM") or "None")
            return {"V2": "rc4", "AESV2": "aes", "AESV3": "aes"}.get(cfm, "identity")

        return method(self.encrypt.get("StmF")), method(self.encrypt.get("StrF"))

    # ---- keys ---------------------------------------------------------------------
    def _file_key(self, file_id: bytes) -> bytes | None:
        if self.revision >= 5:
            return self._key_aesv3()
        key = self._key_r4(_PAD, file_id)
        if self._user_ok(key, file_id):
            return key
        user = self._user_from_owner(b"")  # the owner password is empty
        key = self._key_r4((user + _PAD)[:32], file_id)
        return key if self._user_ok(key, file_id) else None

    def _key_r4(self, padded: bytes, file_id: bytes) -> bytes:
        o = bytes(self.encrypt.get("O") or b"")[:32]
        p = _num(self.encrypt.get("P"), -1) & 0xFFFFFFFF
        h = hashlib.md5(padded[:32] + o + p.to_bytes(4, "little") + file_id)
        if self.revision >= 4 and not self.encrypt_metadata:
            h.update(b"\xff\xff\xff\xff")
        key = h.digest()
        n = 5 if self.revision == 2 else self.length
        if self.revision >= 3:
            for _ in range(50):
                key = hashlib.md5(key[:n]).digest()
        return key[:n]

    def _user_ok(self, key: bytes, file_id: bytes) -> bool:
        u = bytes(self.encrypt.get("U") or b"")
        if self.revision == 2:
            return rc4(key, _PAD) == u[:32]
        x = rc4(key, hashlib.md5(_PAD + file_id).digest())
        for i in range(1, 20):
            x = rc4(bytes(b ^ i for b in key), x)
        return x == u[:16]

    def _user_from_owner(self, owner: bytes) -> bytes:
        okey = hashlib.md5((owner + _PAD)[:32]).digest()
        n = 5 if self.revision == 2 else self.length
        if self.revision >= 3:
            for _ in range(50):
                okey = hashlib.md5(okey[:n]).digest()
        okey = okey[:n]
        x = bytes(self.encrypt.get("O") or b"")[:32]
        if self.revision == 2:
            return rc4(okey, x)
        for i in range(19, -1, -1):
            x = rc4(bytes(b ^ i for b in okey), x)
        return x

    def _key_aesv3(self) -> bytes | None:
        u = bytes(self.encrypt.get("U") or b"")[:48]
        o = bytes(self.encrypt.get("O") or b"")[:48]
        ue = bytes(self.encrypt.get("UE") or b"")[:32]
        oe = bytes(self.encrypt.get("OE") or b"")[:32]
        if len(u) < 48:
            return None
        zero = bytes(16)
        if _hash_r6(b"", u[32:40], b"", self.revision) == u[:32] and len(ue) == 32:
            inter = _hash_r6(b"", u[40:48], b"", self.revision)
            return aes_cbc_decrypt(inter, ue, zero, unpad=False)
        if len(o) == 48 and _hash_r6(b"", o[32:40], u, self.revision) == o[:32] and len(oe) == 32:
            inter = _hash_r6(b"", o[40:48], u, self.revision)
            return aes_cbc_decrypt(inter, oe, zero, unpad=False)
        return None

    # ---- decryption ---------------------------------------------------------------
    def _object_key(self, num: int, gen: int, aes: bool) -> bytes:
        assert self.key is not None
        if self.revision >= 5:
            return self.key
        seed = self.key + num.to_bytes(4, "little")[:3] + gen.to_bytes(4, "little")[:2]
        if aes:
            seed += b"sAlT"
        return hashlib.md5(seed).digest()[: min(len(self.key) + 5, 16)]

    def _apply(self, data: bytes, method: str, num: int, gen: int) -> bytes:
        if method == "rc4":
            return rc4(self._object_key(num, gen, False), data)
        if method == "aes":
            return aes_cbc_decrypt(self._object_key(num, gen, True), data)
        return data

    def decrypt_string(self, data: bytes, num: int, gen: int) -> bytes:
        return self._apply(data, self.string_method, num, gen) if self.key else data

    def decrypt_stream(self, data: bytes, stream_dict: dict[str, Any], num: int, gen: int) -> bytes:
        if not self.key or stream_dict.get("Type") == "XRef":
            return data
        if stream_dict.get("Type") == "Metadata" and not self.encrypt_metadata:
            return data
        return self._apply(data, self.stream_method, num, gen)
