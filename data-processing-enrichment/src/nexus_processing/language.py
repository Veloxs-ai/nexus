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

"""Language and script identification without a model.

``detect_script`` counts letters per Unicode script (from ``unicodedata.name``).
``detect_language`` maps a dominant non-Latin script to its main language (Devanagari ->
``hi``, Arabic -> ``ar``, Han -> ``zh``, kana -> ``ja``, Hangul -> ``ko``, ...) and scores
Latin-script text against stopword profiles of common European languages. The result
is an ISO 639-1 code (``"und"`` when undetermined) and a confidence in 0..1.
"""

from __future__ import annotations

import re
import unicodedata
from functools import lru_cache

__all__ = ["detect_language", "detect_script"]

_SAMPLE_CHARS = 4000

# Script (first word of the Unicode character name) -> language when the script decides it.
_SCRIPT_LANGUAGE = {
    "DEVANAGARI": "hi",
    "ARABIC": "ar",
    "CJK": "zh",
    "HIRAGANA": "ja",
    "KATAKANA": "ja",
    "HANGUL": "ko",
    "CYRILLIC": "ru",
    "GREEK": "el",
    "HEBREW": "he",
    "THAI": "th",
    "BENGALI": "bn",
    "TAMIL": "ta",
    "TELUGU": "te",
    "GUJARATI": "gu",
    "GURMUKHI": "pa",
    "KANNADA": "kn",
    "MALAYALAM": "ml",
    "ORIYA": "or",
    "SINHALA": "si",
    "GEORGIAN": "ka",
    "ARMENIAN": "hy",
    "ETHIOPIC": "am",
    "KHMER": "km",
    "LAO": "lo",
    "MYANMAR": "my",
}

_STOPWORDS = {
    "en": "the of and to in is that for it with as was "
    "on are be this by at from or have not an which",
    "es": "de la que el en y los del se las por un "
    "para con no una su al es lo como más pero sus le",
    "fr": "de la le et les des en un du une que est pour qui dans par sur pas au plus ne se avec",
    "de": "der die und in den von zu das mit sich des "
    "auf für ist im dem nicht ein eine als auch es",
    "pt": "de a o que e do da em um para é com não uma os no se na por mais as dos como mas ao",
    "it": "di e il la che in a per un è del non sono le si con una da al gli lo dei nel più",
    "nl": "de en van het een in is dat op te zijn voor met die niet aan er ook als bij door om",
    "sv": "och i att det som en på är av för med till den har de inte om ett men var jag",
    "id": "yang dan di ini itu dengan untuk dari dalam tidak akan pada juga ke adalah ada oleh",
    "tr": "ve bir bu da de için ile ne olarak daha çok gibi ama en mi sonra kadar her",
}
_WORD = re.compile(r"[^\W\d_]+")


@lru_cache(maxsize=4096)
def _script_of(char: str) -> str:
    try:
        name = unicodedata.name(char)
    except ValueError:
        return ""
    first = name.split(" ", 1)[0]
    return "CJK" if first in ("CJK", "IDEOGRAPHIC") else first


def detect_script(text: str) -> dict[str, float]:
    """Share of letters per script in (a sample of) ``text``, largest first."""
    counts: dict[str, int] = {}
    for char in (text or "")[:_SAMPLE_CHARS]:
        if char.isalpha():
            script = _script_of(char)
            if script:
                counts[script] = counts.get(script, 0) + 1
    total = sum(counts.values())
    if not total:
        return {}
    return dict(
        sorted(((k, v / total) for k, v in counts.items()), key=lambda kv: kv[1], reverse=True)
    )


@lru_cache(maxsize=1)
def _profiles() -> dict[str, frozenset[str]]:
    return {lang: frozenset(words.split()) for lang, words in _STOPWORDS.items()}


def detect_language(text: str) -> tuple[str, float]:
    """``(ISO 639-1 code, confidence)`` of ``text``; ``("und", 0.0)`` when undetermined."""
    scripts = detect_script(text)
    if not scripts:
        return "und", 0.0
    top, share = next(iter(scripts.items()))
    if "HIRAGANA" in scripts or "KATAKANA" in scripts:
        kana = scripts.get("HIRAGANA", 0.0) + scripts.get("KATAKANA", 0.0)
        if kana >= 0.1:
            return "ja", round(min(1.0, share + kana), 3)
    if top != "LATIN":
        lang = _SCRIPT_LANGUAGE.get(top)
        return (lang, round(share, 3)) if lang else ("und", 0.0)
    words = [w.casefold() for w in _WORD.findall(text[:_SAMPLE_CHARS])]
    if len(words) < 3:
        return "und", 0.0
    scores = {lang: sum(1 for w in words if w in stop) for lang, stop in _profiles().items()}
    best = max(scores, key=lambda lang: scores[lang])
    hits = scores[best]
    if hits == 0:
        return "und", 0.0
    runner_up = max((v for k, v in scores.items() if k != best), default=0)
    confidence = min(1.0, (hits / len(words)) * 3) * (1 - runner_up / (hits + runner_up))
    return best, round(max(0.05, confidence) * share, 3)
