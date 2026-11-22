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

"""Legacy (non-UTF) encodings: which code page a byte string was written in.

``rank_encodings`` decodes a sample strictly with each candidate code page (Windows
Western, Central European, Cyrillic, Greek, Turkish, Arabic, Hebrew, Baltic, KOI8-R,
Japanese, Chinese simplified and traditional, Korean) and scores how plausible the text
is, the way a reader notices mojibake:

* C1 control characters, private-use or unassigned code points (never in real text);
* symbols wedged inside words (``Za¿ó³æ`` is cp1250 read as cp1252);
* case flips inside a word (``йНЛОЮМХЪ`` is cp1251 read as KOI8-R);
* words made mostly of accented Latin letters (``óõìâüëáéï`` is Greek read as cp1252);
* letters from several scripts in one text, half-width katakana runs;
* for East Asian text: kana and the most frequent Han characters count in favour, and
  Han text broken into short space-separated words is Korean, not Chinese.

The lowest penalty wins; Windows-1252 wins ties, so Western files decode as before.
Only the standard library's codecs are used.
"""

from __future__ import annotations

import codecs
import unicodedata

__all__ = ["CANDIDATES", "rank_encodings"]

CANDIDATES: tuple[str, ...] = (
    "cp1252",
    "cp1250",
    "cp1251",
    "cp1253",
    "cp1254",
    "cp1256",
    "cp1255",
    "cp1257",
    "koi8_r",
    "cp932",
    "euc_jp",
    "gb18030",
    "big5",
    "euc_kr",
)
SAMPLE_BYTES = 8192
MIN_EVIDENCE = 3  # non-ASCII characters needed before leaving Windows-1252
MARGIN = 0.3  # how much more plausible (per non-ASCII character) another page must be

# The most frequent Han characters (simplified and traditional forms): real Chinese and
# Japanese text is dense with them, mis-decoded bytes are not.
_COMMON_HAN = frozenset(
    "的一是不了人我在有他这這个個们們中来來上大为為和国國地到以说說时時要就出会會可也你对對"
    "生能而子那得于於着著下自之年过過发發后後作里裡用道行所然家种種事成方多经經么麼去法学學"
    "如都同现現当當没沒动動面起看定天分还還进進好小部其些主样樣理心她本前开開但因只从從想实"
    "實日军軍者意无無力它与與长長把机機十民第公此已工使情明性知全三又关關点點正业業外将將两"
    "兩高间間由问問很最重并並物手应應战戰向头頭文体體政美相见見被利什二等产產或新己制身果加"
    "西月话話合回特代内內信表化老给給世位次度门門任常先海通教儿兒原东東声聲提立及比员員解水"
    "名真论論处處走义義各入几幾口认認条條平系气氣题題活更别別打女变變四神总總何电電数數安少"
    "报報才结結反受目太量再感建务務做接必场場件计計管期市直资資命山金指许許统統区區保至形社"
    "便空决決治展科司五基书書非则則白界达達光放强強即像难難且权權思王象完设設式色路记記南品"
    "住告类類求据據程北边邊死张張该該交规規万萬取格望觉覺术術领領共确確传傳师師观觀清今切院"
    "让讓识識候带帶导導运運改收根造言联聯持组組每济濟车車亲親极極服快办辦议議往元英士证證近"
    "失转轉令准準布始存未远遠台单單影具字爱愛流备備连連调調深商算质質团團集百需价價城石级級"
    "整府离離况況请請技际際约約示复復病究线線似官火断斷精满滿支视視消越器容照须須增研写寫称"
    "稱企功包片史委查轻輕易早曾除农農找装裝广廣显顯标標谈談图圖念引历歷首医醫局专專费費号號"
    "社会會議株式取締役業績発表承認計画画投資季度董事批准年度司公布了請求書営課長様宛中在"
)
_KANA = (0x3040, 0x30FF)
_HALFWIDTH_KANA = (0xFF61, 0xFF9F)


def _script(ch: str) -> str:
    cp = ord(ch)
    if cp < 0x250:
        return "latin"
    if 0x370 <= cp < 0x400:
        return "greek"
    if 0x400 <= cp < 0x530:
        return "cyrillic"
    if 0x590 <= cp < 0x600:
        return "hebrew"
    if 0x600 <= cp < 0x780 or 0xFB50 <= cp < 0xFF00:
        return "arabic"
    if _KANA[0] <= cp <= _KANA[1] or _HALFWIDTH_KANA[0] <= cp <= _HALFWIDTH_KANA[1]:
        return "kana"
    if 0x3400 <= cp < 0xA000 or 0xF900 <= cp < 0xFB00:
        return "han"
    if 0xAC00 <= cp < 0xD7B0 or 0x1100 <= cp < 0x1200 or 0x3130 <= cp < 0x3190:
        return "hangul"
    return "other"


_CJK = frozenset({"han", "kana", "hangul"})  # one writing system: mixing them is normal
_VOWELS = frozenset("aeiouyæœøаеёиоуыэюяіїєαεηιουω")
_vowel_cache: dict[str, bool] = {}


def _is_vowel(ch: str) -> bool:
    hit = _vowel_cache.get(ch)
    if hit is None:
        base = unicodedata.normalize("NFD", ch.lower())[:1]
        hit = _vowel_cache[ch] = base in _VOWELS or ch.lower() in _VOWELS
    return hit


def _word_penalty(word: str, letters: dict[str, int]) -> tuple[float, int, int]:
    """``(penalty, non-ASCII characters, Han characters)`` of one word."""
    penalty = 0.0
    non_ascii = han = 0
    prev_lower = False
    ascii_letters = latin_extra = vowels = 0
    scripts: dict[str, int] = {}
    size = len(word)
    for i, ch in enumerate(word):
        if ch.isascii():
            if ch.isalpha():
                ascii_letters += 1
                vowels += ch in "aeiouyAEIOUY"
                if ch.isupper() and prev_lower:
                    penalty += 0.25  # camelCase identifiers are common in ASCII
                prev_lower = ch.islower()
            else:
                prev_lower = False
            continue
        non_ascii += 1
        cp = ord(ch)
        if 0x80 <= cp < 0xA0 or cp == 0xFFFD or 0xE000 <= cp < 0xF900:
            penalty += 3.0  # C1 controls and private use never occur in real text
            continue
        category = unicodedata.category(ch)
        if category == "Cn":
            penalty += 3.0
            continue
        if category[0] != "L":
            prev_lower = False
            if category == "Sc" and not (0 < i < size - 1):
                continue  # € £ ¥ next to an amount are ordinary
            if category[0] in "SN" or (category in ("Pc", "Pd", "Po") and cp < 0x2000):
                inside = 0 < i < size - 1 and word[i - 1].isalpha() and word[i + 1].isalpha()
                penalty += 2.0 if inside else 0.6  # ``Za¿ó³æ``: a symbol inside a word
            continue
        script = _script(ch)
        group = "cjk" if script in _CJK else script
        letters[group] = letters.get(group, 0) + 1
        scripts[group] = scripts.get(group, 0) + 1
        if ch.isupper() and prev_lower:
            penalty += 1.0  # ``йНЛОЮМХЪ``: a case flip inside a word
        prev_lower = ch.islower()
        if script in ("latin", "cyrillic", "greek"):
            vowels += _is_vowel(ch)
            if script == "latin":
                latin_extra += 1
            if ch == "ς" and i < size - 1 and word[i + 1].isalpha():
                penalty += 1.0  # final sigma inside a word
        elif script == "han":
            han += 1
            penalty += -0.6 if ch in _COMMON_HAN else 0.2
        elif script == "kana":
            penalty += 0.7 if _HALFWIDTH_KANA[0] <= cp <= _HALFWIDTH_KANA[1] else -0.4
    if ascii_letters:
        scripts["latin"] = scripts.get("latin", 0) + ascii_letters
    if len(scripts) > 1:  # Cyrillic or Greek letters inside a Latin word
        penalty += 2.0 * (sum(scripts.values()) - max(scripts.values()))
    if latin_extra >= 3 and not ascii_letters:
        penalty += latin_extra  # ``óõìâüëáéï``: a word of nothing but accented letters
    alphabetic = sum(scripts.get(k, 0) for k in ("latin", "cyrillic", "greek"))
    if alphabetic >= 4 and not vowels:
        penalty += 0.5 * alphabetic  # ``дзбшд``: no vowel at all
    return penalty, non_ascii, han


def _penalty(text: str) -> tuple[float, int]:
    """``(implausibility per non-ASCII character, non-ASCII characters)``; lower is more
    plausible."""
    non_ascii = 0
    penalty = 0.0
    letters: dict[str, int] = {}
    han_words = spaced_han = 0
    # A word scores the same wherever it occurs: score each distinct word once and replay
    # its letter counts (same additions in the same order, so the result is identical).
    seen: dict[str, tuple[float, int, int, tuple[tuple[str, int], ...]]] = {}
    for word in text.split():
        if word.isascii():
            continue
        hit = seen.get(word)
        if hit is None:
            counts: dict[str, int] = {}
            word_penalty, word_non_ascii, han = _word_penalty(word, counts)
            hit = seen[word] = (word_penalty, word_non_ascii, han, tuple(counts.items()))
        word_penalty, word_non_ascii, han, counts_items = hit
        for group, count in counts_items:
            letters[group] = letters.get(group, 0) + count
        penalty += word_penalty
        non_ascii += word_non_ascii
        if han:
            han_words += 1
            spaced_han += han <= 4
    if letters:
        penalty += 1.5 * (sum(letters.values()) - max(letters.values()))
    if han_words >= 4 and spaced_han >= 0.6 * han_words:
        penalty += 0.8 * non_ascii  # Han in short space-separated words: Korean read wrong
    return penalty / max(1, non_ascii), non_ascii


def _sample_text(sample: bytes, encoding: str) -> str | None:
    decoder = codecs.getincrementaldecoder(encoding)(errors="strict")
    try:
        return decoder.decode(sample, final=False)  # a cut multi-byte tail is not an error
    except UnicodeDecodeError:
        return None


def rank_encodings(data: bytes) -> list[str]:
    """Candidate code pages for ``data`` (not UTF-8), most plausible first.

    Only encodings that decode the sample strictly are listed; ties keep ``CANDIDATES``
    order, so Windows-1252 stays first for Western text."""
    sample = data[:SAMPLE_BYTES]
    scored: list[tuple[float, int, str]] = []
    evidence: dict[str, int] = {}
    for order, encoding in enumerate(CANDIDATES):
        text = _sample_text(sample, encoding)
        if text is None:
            continue
        score, evidence[encoding] = _penalty(text)
        scored.append((round(score, 6), order, encoding))
    scored.sort()
    ranked = [encoding for _, _, encoding in scored]
    if not ranked or evidence[ranked[0]] < MIN_EVIDENCE:
        # A couple of high bytes say nothing about the code page: Windows-1252 when it
        # can read them, else none (the caller's Latin-1 maps every byte).
        return ["cp1252"] if "cp1252" in evidence else []
    if ranked[0] != "cp1252" and "cp1252" in evidence:
        western = next(score for score, _, encoding in scored if encoding == "cp1252")
        # Windows-1252 is by far the most common legacy encoding: another code page must
        # be clearly more plausible to replace it.
        if scored[0][0] > western - MARGIN:
            ranked.remove("cp1252")
            ranked.insert(0, "cp1252")
    return ranked
