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

"""Per-document parse quality: is the extracted text usable?

``assess_text`` measures what a processor produced (characters, letter/digit share,
replacement characters, empty chunks, language) and raises flags a pipeline can show
or act on: ``garbled_text`` (mostly symbols or mojibake), ``no_text`` (nothing
extracted), ``mostly_empty`` (most chunks have almost no text) and ``replacement_chars``
(bytes that could not be decoded).
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from .language import detect_language

__all__ = ["assess_text"]

GARBLED_ALNUM_RATIO = 0.5
EMPTY_CHUNK_CHARS = 20
SAMPLE_CHARS = 500_000  # ratios are measured on (a sample of) this many characters


def assess_text(texts: Iterable[str], *, source_chars: int | None = None) -> dict[str, Any]:
    """Quality measures and flags for the chunk ``texts`` of one document.

    ``source_chars``: characters the parser extracted before chunking, when known
    (``coverage`` = characters indexed / characters extracted).
    """
    texts = [t or "" for t in texts]
    joined = "\n".join(texts)
    sample = joined[:SAMPLE_CHARS]
    visible = [c for c in sample if not c.isspace()]
    alnum = sum(1 for c in visible if c.isalnum())
    replacement = sample.count("�")
    empty = sum(1 for t in texts if len(t.strip()) < EMPTY_CHUNK_CHARS)
    language, confidence = detect_language(sample)
    report: dict[str, Any] = {
        "chunks": len(texts),
        "chars_indexed": len(joined),
        "alnum_ratio": round(alnum / len(visible), 3) if visible else 0.0,
        "replacement_char_ratio": round(replacement / len(sample), 4) if sample else 0.0,
        "empty_chunks": empty,
        "language": language,
        "language_confidence": confidence,
    }
    if source_chars:
        report["chars_extracted"] = source_chars
        report["coverage"] = round(min(1.0, len(joined) / source_chars), 3)
    flags: list[str] = []
    if not visible:
        flags.append("no_text")
    elif report["alnum_ratio"] < GARBLED_ALNUM_RATIO:
        flags.append("garbled_text")
    if replacement and report["replacement_char_ratio"] > 0.001:
        flags.append("replacement_chars")
    if texts and empty > len(texts) / 2:
        flags.append("mostly_empty")
    report["flags"] = flags
    return report
