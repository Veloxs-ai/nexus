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

"""Text tokenization and vector math shared by the retrieval engine.

Embedding models live in :mod:`nexus_retrieval.semantic`.
"""

from __future__ import annotations

import math
import re
import unicodedata

# Words in any script: letters, digits, "_", "-" and the combining marks of scripts whose
# vowel signs and viramas are marks (Indic, Thai, Arabic, Hebrew...; ``\w`` alone would cut
# "हिन्दी" apart). CJK runs are split into bigrams below.
TOKEN_PATTERN = re.compile(
    r"[\w\-\u0300-\u036f\u0483-\u0489\u0591-\u05c7\u0610-\u061a\u064b-\u065f\u0670"
    r"\u06d6-\u06ed\u0900-\u0dff\u0e00-\u0e7f\u0e80-\u0eff\u1000-\u109f\u1780-\u17ff"
    r"\u200c\u200d]+"
)
_CJK = re.compile(r"[\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff\uac00-\ud7af\uf900-\ufaff]+")


def _fold(token: str) -> str:
    """Casefold; Latin letters also lose their accents (``Café`` -> ``cafe``). Other scripts
    keep their combining marks: Devanagari vowel signs are letters of the word."""
    token = token.casefold().replace("\u200c", "").replace("\u200d", "")
    if token.isascii():
        return token
    decomposed = unicodedata.normalize("NFKD", token)
    out: list[str] = []
    for char in decomposed:
        if unicodedata.combining(char) and out and out[-1].isascii():
            continue  # an accent on a Latin base letter
        out.append(char)
    return unicodedata.normalize("NFC", "".join(out))


def tokenize(text: str) -> list[str]:
    """Lexical tokens of ``text`` in any script.

    ASCII words are lowercased exactly as before. Accented Latin words match their
    unaccented spelling, Devanagari/Arabic/Cyrillic/... words are tokens of their own, and
    Chinese/Japanese/Korean runs (no spaces between words) become overlapping character
    bigrams (a single character stays a token).
    """
    tokens: list[str] = []
    for raw in TOKEN_PATTERN.findall(text or ""):
        if raw.isascii():
            tokens.append(raw.lower())
            continue
        pos = 0
        for match in _CJK.finditer(raw):
            if match.start() > pos:
                tokens.append(_fold(raw[pos : match.start()]))
            run = match.group(0)
            tokens.extend(run if len(run) == 1 else [run[i : i + 2] for i in range(len(run) - 1)])
            pos = match.end()
        if pos < len(raw):
            tokens.append(_fold(raw[pos:]))
    return [t for t in tokens if t]


def normalize_vector(vector: list[float]) -> list[float]:
    magnitude = math.sqrt(sum(value * value for value in vector))
    if magnitude == 0:
        return vector
    return [value / magnitude for value in vector]


def cosine_similarity(left: list[float], right: list[float]) -> float:
    if not left or not right or len(left) != len(right):
        return 0.0
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    if left_norm == 0 or right_norm == 0:
        return 0.0
    return sum(a * b for a, b in zip(left, right, strict=True)) / (left_norm * right_norm)
