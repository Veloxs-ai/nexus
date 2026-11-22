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
    "pl": "i w na z do się nie że to jest o jak ale po co od za przez dla oraz a jego",
    "cs": "a v se na je že to s z do o k jak ale by jsou pro jsem od po tak jeho který",
    "ro": "și în de la a cu că nu o pe un din se este mai care pentru ca al sau dar fost",
    "da": "og i at det en den til er som på de med han af for ikke der var mig sig men et",
    "no": "og i det som en på er av for med til den har de ikke om et men var jeg seg fra",
    "fi": "ja on ei se että oli hän mutta kun niin myös tai ovat joka sen vain mitä olla",
    "hu": "a az és hogy nem egy is van meg de ez csak már volt mint ki el azt még sem",
    "vi": "và của là có không được cho các những một người trong với này đã để khi từ",
}
_WORD = re.compile(r"[^\W\d_]+")
_LATIN_MARKERS = {
    lang: frozenset(marks)
    for lang, marks in {
        "pl": "łąęśźżćń",
        "cs": "ěřůťď",
        "ro": "ășțş",
        "hu": "őű",
        "tr": "ğı",
        "vi": "ơưđạảấầẩẫậắằẳẵặẹẻẽếềểễệỉịọỏốồổỗộớờởỡợụủứừửữựỳỵỷỹ",
        "pt": "ãõ",
        "es": "ñ¿¡",
        "de": "ß",
        "da": "ø",
        "no": "ø",
    }.items()
}
MIN_STOPWORD_SHARE = 0.05  # below this share of stopword hits the language is unknown

# Letters that single out one language of a shared script.
_CYRILLIC_MARKERS = (
    ("kk", "әғқңөұүһ"),
    ("sr", "ђјљњћџ"),
    ("mk", "ѓќѕ"),
    ("be", "ў"),
    ("uk", "іїєґ"),
)
_ARABIC_MARKERS = (("ur", "ٹڈڑںے"), ("fa", "پچژگکی"))
_MARATHI_WORDS = frozenset(["आणि", "आहे", "आहेत", "होते", "च्या", "केले", "झाले", "नाही"])
_HINDI_WORDS = frozenset(["और", "है", "हैं", "के", "की", "में", "को", "से", "का", "था", "थे", "नहीं"])
# Kanji forms used in Japanese but not in Chinese (shinjitai and kokuji).
_JAPANESE_KANJI = frozenset(
    "営様駅円図広売読変楽発検険験剤済渋浅歩転伝価徳辺隠帰戦拡払単弁応恵悪戻斎黒県権絵続総縦労"
    "励圧囲壊塩桜歳枠稲蔵込峠畑働匂栃雫芸賛巻覚箇関姫"
)


def _cyrillic_language(sample: str) -> str:
    letters = set(sample.lower())
    for lang, marks in _CYRILLIC_MARKERS:
        if letters & set(marks):
            return lang
    if "ъ" in letters and not letters & set("ыэё"):
        return "bg"  # Bulgarian writes ъ as a vowel and has no ы/э/ё
    return "ru"


def _arabic_language(sample: str) -> str:
    for lang, marks in _ARABIC_MARKERS:
        found = sum(sample.count(m) for m in marks)
        if found >= 2:
            return lang
    return "ar"


def _devanagari_language(sample: str) -> str:
    words = sample.split()
    marathi = sum(w in _MARATHI_WORDS for w in words) + 2 * sample.count("ळ")
    hindi = sum(w in _HINDI_WORDS for w in words)
    return "mr" if marathi > hindi else "hi"


@lru_cache(maxsize=4096)
@lru_cache(maxsize=8192)
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


@lru_cache(maxsize=1)
def _stopword_index() -> dict[str, tuple[str, ...]]:
    """Stopword -> the languages whose profile lists it (one lookup per word)."""
    index: dict[str, list[str]] = {}
    for lang, stop in _profiles().items():
        for word in stop:
            index.setdefault(word, []).append(lang)
    return {word: tuple(langs) for word, langs in index.items()}


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
        if not lang:
            return "und", 0.0
        sample = text[:_SAMPLE_CHARS]
        if top == "CYRILLIC":
            lang = _cyrillic_language(sample)
        elif top == "ARABIC":
            lang = _arabic_language(sample)
        elif top == "DEVANAGARI":
            lang = _devanagari_language(sample)
        elif top == "CJK" and any(ch in _JAPANESE_KANJI for ch in sample):
            return "ja", round(share * 0.8, 3)  # kanji only, but in Japanese forms
        return lang, round(share, 3)
    words = [w.casefold() for w in _WORD.findall(text[:_SAMPLE_CHARS])]
    if len(words) < 3:
        return "und", 0.0
    scores = dict.fromkeys(_profiles(), 0)  # profile order: ties resolve as before
    index = _stopword_index()
    for word in words:
        for lang in index.get(word, ()):
            scores[lang] += 1
    if not any(scores.values()) or max(scores.values()) < MIN_STOPWORD_SHARE * len(words):
        return "und", 0.0
    letters = set(text[:_SAMPLE_CHARS].lower())
    for lang, marks in _LATIN_MARKERS.items():  # letters only one language writes
        scores[lang] += len(letters & marks)
    best = max(scores, key=lambda lang: scores[lang])
    hits = scores[best]
    runner_up = max((v for k, v in scores.items() if k != best), default=0)
    confidence = min(1.0, (hits / len(words)) * 3) * (1 - runner_up / (hits + runner_up))
    return best, round(max(0.05, confidence) * share, 3)
