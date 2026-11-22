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

from __future__ import annotations

import re
from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass
from functools import lru_cache

from .config import PiiConfig
from .models import Finding
from .normalization import luhn_valid, strip_invisible
from .pii_ids import ID_PATTERNS, ID_VALIDATORS
from .pii_scan import MAYBE_PII, email_matches, shadow

PATTERNS = {
    # Secrets first: they may contain digit runs the generic patterns would split.
    "jwt": re.compile(r"\beyJ[A-Za-z0-9_-]{5,}\.[A-Za-z0-9_-]{5,}\.[A-Za-z0-9_-]{5,}"),
    "api_key": re.compile(
        r"\b(?:sk-(?:proj-|ant-)?[A-Za-z0-9_-]{16,}|AKIA[0-9A-Z]{16}|AIza[0-9A-Za-z_-]{35}"
        r"|gh[pousr]_[A-Za-z0-9]{36}|xox[abprs]-[A-Za-z0-9-]{10,}|sk_(?:live|test)_[A-Za-z0-9]{16,})"
    ),
    "email": re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"),
    # Opt-in national ids (aadhaar, pan, iban), each confirmed by its checksum or format
    # rules (``pii_ids``); before the generic number detectors so they keep the whole value.
    **ID_PATTERNS,
    "ssn": re.compile(r"(?<![\w-])\d{3}-\d{2}-\d{4}(?![\w-])"),
    "credit_card": re.compile(r"\b(?:\d[ -]?){13,19}\b"),
    "phone": re.compile(
        r"(?:(?<![\w+])\+\d{1,3}[-.\s]?\d{2,5}[-.\s]?\d{3,5}[-.\s]?\d{3,5}\b)"
        r"|\b(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b"
    ),
    "ip_address": re.compile(r"\b(?:(?:25[0-5]|2[0-4]\d|1?\d?\d)\.){3}(?:25[0-5]|2[0-4]\d|1?\d?\d)\b"),
    # Opt-in (not a default detector): a street address, house number + 1-4 capitalised
    # words + a street type, with an optional unit ("221B Baker Street", "12 Gandhi Marg, Flat 4").
    "address": re.compile(
        r"\b\d{1,5}[A-Za-z]?\s+(?:[A-Z][a-z]+\s){1,4}"
        r"(?:Street|St|Road|Rd|Avenue|Ave|Lane|Ln|Boulevard|Blvd|Drive|Dr|Court|Ct|Way|Place|Pl"
        r"|Marg|Nagar|Colony)\b\.?"
        r"(?:,?\s*(?:Apt|Suite|Unit|Flat)\s*#?\s*\w+)?"
    ),
}

MASKS = {
    "jwt": "[JWT_TOKEN]",
    "api_key": "[API_KEY]",
    "email": "[EMAIL]",
    "ssn": "[SSN]",
    "credit_card": "[CREDIT_CARD]",
    "phone": "[PHONE]",
    "ip_address": "[IP_ADDRESS]",
    "address": "[ADDRESS]",
    "aadhaar": "[AADHAAR]",
    "pan": "[PAN]",
    "iban": "[IBAN]",
    "person": "[PERSON]",
    "location": "[LOCATION]",
}
# Named entities found by ``ner`` (a lexicon detector, or spaCy when installed), not by a regex.
NER_ENTITIES = ("person", "location")

# Detectors are always applied in PATTERNS order (specific formats before generic numbers).
_ORDER = list(PATTERNS)
# The detectors as shipped: the fast paths below apply only while a detector still uses
# its built-in pattern (PATTERNS is a public dict and may be customised).
_BUILTIN = dict(PATTERNS)
_EMAIL = PATTERNS["email"]
# Literal text every match of a built-in detector contains: without one, the regex is
# not run at all (a substring search is ~50x cheaper than scanning the text with it).
_REQUIRED = {
    "jwt": ("eyJ",),
    "api_key": ("sk-", "sk_", "AKIA", "AIza", "ghp_", "gho_", "ghu_", "ghs_", "ghr_", "xox"),
    "email": ("@",),
    "ssn": ("-",),
}
_DIGITS = re.compile(r"\d+")
# Every context cue needs a letter or a currency sign: without one the cue regexes are skipped.
_CUE_CHAR = re.compile(r"[^\W\d_]|[$€£₹¥]")

# --- context rules for the number detectors ---------------------------------------
# A formatted number (separators, parentheses, a leading "+") is a phone number unless it
# is part of a longer token ("ORD-555-123-4567", "1234567890.50") or the value of an
# identifier/timestamp key. A bare digit run is one when a cue precedes it ("call",
# "my number is", "text me at") or when it has the shape of a dialable number (NANP
# ``[2-9]XX[2-9]XXXXXX``, an Indian mobile ``[6-9]XXXXXXXXX``) and nothing marks it as an
# identifier, amount or date. Table columns are masked by column (``pii_columns``), so
# id and amount columns never reach this free-text rule.
_CONTEXT_CHARS = 32
_CUE_WORDS = (
    r"(?i)(?:(?:\b|_)(?:phone|ph|tel|telephone|mobile|mob|cell|cellphone|call|calls|called|calling"
    r"|contact|whatsapp|fax|sms|dial|reach|text|texts|texting|ping|ring|message|msg"
    r"|kontakt|telefon|handy|movil|móvil|celular|portable|téléphone)(?:\b|_)"
    r"|\b(?:my|our|his|her|their|your|personal|home|work|office|landline)\s+(?:number|no\.?|#)"
    r"(?:\s+is)?\b)"
)
_PHONE_CUE = re.compile(_CUE_WORDS + r"[^\n|;]{0,24}$")
_AMOUNT_CUE = re.compile(
    r"(?i)(?:(?:\b|_)(?:amount|amt|total|subtotal|price|cost|balance|sum|qty|quantity|count|value"
    r"|revenue|salary|fee|fees|paid|usd|inr|eur|gbp|rs|\w+_amount|\w+_total|\w+_count)(?:\b|_)"
    r"\s*[:=#]?\s*|[$€£₹¥]\s?)$"
)
_DIALABLE = re.compile(r"(?:1?[2-9]\d{2}[2-9]\d{6}|[6-9]\d{9})")
_DATE_DIGITS = re.compile(r"(?:19|20)\d{2}(?:0[1-9]|1[0-2])(?:0[1-9]|[12]\d|3[01])\d{0,2}")
_CARD_CUE = re.compile(
    r"(?i)(?:\b|_)(?:card|cards|cc|ccn|pan|visa|mastercard|amex|discover|credit|debit|paid with"
    r"|payment)(?:\b|_)[^\n|;]{0,24}$"
)
_ID_CUE = re.compile(
    r"(?i)(?:\b|_)(?:id|ids|no|nr|num|number|order|orders|invoice|ref|reference|ts|timestamp|epoch"
    r"|txn|transaction|ticket|sku|account|acct|serial|tracking|isbn|uuid|build|version|code"
    r"|\w+_at|\w+_id|\w+_no|\w+_ts)(?:\b|_)\s*[:=#]?\s*$"
)
_CARD_PREFIX = re.compile(r"^(?:4|5[1-5]|2[2-7]|3[47]|3[0689]|6)")


def _attached(text: str, start: int, end: int, cued: bool = False) -> bool:
    """True when the match is glued to a longer token: ABC-555..., 1234567890.50, ...-12.

    ``cued``: a phone/card cue precedes the match, so a ``#`` right before it is the cue's
    number sign ("cc#4111...", "tel#555...") rather than part of an id. A comma only glues
    a decimal or thousands group (1-3 digits), not the next value of a list
    ("5553334444,4155551234")."""
    before = text[start - 1] if start > 0 else ""
    after = text[end] if end < len(text) else ""
    if before and (before.isalnum() or before in "-_/.@" or (before == "#" and not cued)):
        return True
    if after and (after.isalnum() or after in "_@"):
        return True
    if after == ",":
        tail = _DIGITS.match(text, end + 1)
        return bool(tail) and len(tail.group(0)) <= 3
    after2 = text[end + 1] if end + 1 < len(text) else ""
    return after in "-./" and after2.isdigit()


def _phone_ok(text: str, match: re.Match[str]) -> bool:
    value = match.group(0)
    start, end = match.span()
    context = text[max(0, start - _CONTEXT_CHARS) : start]
    words = bool(_CUE_CHAR.search(context))
    cued = words and bool(_PHONE_CUE.search(context))
    if _attached(text, start, end, cued):
        return False
    if cued:
        return True
    if words and (_ID_CUE.search(context) or _AMOUNT_CUE.search(context)):
        return False
    if value.startswith("+") or not value.isdigit():
        return True
    return bool(_DIALABLE.fullmatch(value)) and not _DATE_DIGITS.fullmatch(value)


def _span(match: re.Match[str]) -> tuple[int, int]:
    """Match span without trailing separators (the card pattern may end on a space)."""
    start, end = match.span()
    value = match.group(0)
    return start, end - (len(value) - len(value.rstrip(" -")))


def _card_ok(text: str, match: re.Match[str]) -> bool:
    start, end = _span(match)
    value = text[start:end]
    context = text[max(0, start - _CONTEXT_CHARS) : start]
    words = bool(_CUE_CHAR.search(context))
    cued = words and bool(_CARD_CUE.search(context))
    if not luhn_valid(value) or _attached(text, start, end, cued):
        return False
    if cued:
        return True
    if words and _ID_CUE.search(context):
        return False
    digits = "".join(ch for ch in value if ch.isdigit())
    return bool(_CARD_PREFIX.match(digits))


_VALIDATORS = {"phone": _phone_ok, "credit_card": _card_ok, **ID_VALIDATORS}

# National phone formats the main pattern misses ("98765 43210", "044-2345 6789",
# "030 12345678", "020 7946 0958", "+33 1 23 45 67 89"). A national number needs a phone
# cue ("call", "mobile", "my number is"): digit groups alone are too often amounts; one
# with a "+" country code is accepted like the main pattern's, unless an id/amount cue
# precedes it.
_NATIONAL_PHONE = re.compile(
    # The lookahead (10+ digits ahead, at most two separators apart) skips dates, amounts
    # and short ids inside the regex engine; the validator counts the digits exactly.
    r"(?<![\w+\-/.@#])(?=(?:[-.\s()+]{0,2}\d){10})\+?\(?\d{1,5}\)?(?:[-.\s]\d{1,8}){1,5}(?!\w)"
)
# Exact prefilter: ``_NATIONAL_PHONE``'s lookahead needs ten digits, each at most two
# separators after the previous one; text without such a run cannot match, and this scan
# (it starts on a digit) skips digit-free stretches in C.
_TEN_DIGIT_RUN = re.compile(r"\d(?:[-.\s()+]{0,2}\d){9}")
_DATE_LIKE = re.compile(
    r"(?:19|20)\d{2}[-./](?:0?[1-9]|1[0-2])[-./]\d{1,2}|\d{1,2}[-./]\d{1,2}[-./]\d{4}"
)


def _national_phone_ok(text: str, match: re.Match[str]) -> bool:
    start, end = _span(match)
    value = text[start:end]
    if not 10 <= sum(ch.isdigit() for ch in value) <= 12 or _DATE_LIKE.search(value):
        return False
    if text.startswith(":", end) and text[end + 1 : end + 2].isdigit():
        return False  # a time ("... 10:30")
    context = text[max(0, start - _CONTEXT_CHARS) : start]
    words = bool(_CUE_CHAR.search(context))
    cued = words and bool(_PHONE_CUE.search(context))
    if _attached(text, start, end, cued):
        return False
    if cued:
        return True
    if not text.startswith("+", start):
        return False
    return not (words and (_ID_CUE.search(context) or _AMOUNT_CUE.search(context)))


def _phone_span(text: str, start: int, end: int) -> tuple[int, int]:
    """A phone span with the "+" of a country code or the "(" of an area code that the
    pattern's word boundary leaves outside ("+1 (415) ...", "(212) 555-0199")."""
    if start > 0:
        before = text[start - 1]
        value = text[start:end]
        if before == "+" and value[:1].isdigit():
            return start - 1, end
        closes = value.find(")")
        if before == "(" and closes != -1 and not 0 <= value.find("(") < closes:
            return start - 1, end
    return start, end


def _accept(detector: str, text: str, match: re.Match[str], strict: bool = False) -> bool:
    if strict:  # every pattern match counts; cards and ids still need a valid checksum
        if detector in ID_VALIDATORS:
            return ID_VALIDATORS[detector](text, match)
        return detector != "credit_card" or luhn_valid(text[slice(*_span(match))])
    validator = _VALIDATORS.get(detector)
    return validator(text, match) if validator else True


def _finditer(detector: str, pattern: re.Pattern[str], text: str) -> Iterator[re.Match[str]]:
    """``pattern.finditer(text)``; the built-in e-mail pattern runs as a linear scan on
    texts long enough for the regex's worst case (quadratic) to matter."""
    if pattern is _EMAIL and len(text) > _SHORT_TEXT:
        return email_matches(text)  # type: ignore[return-value]
    return pattern.finditer(text)


_SHORT_TEXT = 512


def _contains_any(text: str, literals: tuple[str, ...]) -> bool:
    return any(literal in text for literal in literals)


def _cannot_match(text: str, detectors: Iterable[str]) -> bool:
    """True when ``text`` is ASCII with no digit, ``@`` or secret prefix and every detector
    is a built-in one: no detector can then find anything."""
    if not text.isascii() or MAYBE_PII.search(text):
        return False
    return all(PATTERNS.get(d) is _BUILTIN.get(d) for d in detectors)


def detect_pii(text: str, config: PiiConfig) -> list[Finding]:
    """One finding per enabled detector that found a value in ``text``.

    Uses the same detection as masking (:func:`detect_pii_spans`), so a finding always
    corresponds to a value ``mask_pii`` replaces.
    """
    if not config.enabled:
        return []
    return findings_for(detect_pii_spans(text, config), config)


def findings_for(spans: Iterable[PiiSpan], config: PiiConfig) -> list[Finding]:
    """``detect_pii`` findings for spans already detected (in ``config.detectors`` order)."""
    found = {span.entity for span in spans}
    return [
        Finding(category="pii", message=f"Detected {detector}", severity="warn")
        for detector in dict.fromkeys(config.detectors)
        if detector in found
    ]


def mask_detector(text: str, detector: str) -> str:
    """Mask the values one detector accepts in ``text`` (already normalized)."""
    pattern = PATTERNS.get(detector)
    if not pattern or not text or _cannot_match(text, (detector,)):
        return text
    mask_value = MASKS.get(detector, f"[{detector.upper()}]")
    if detector not in _VALIDATORS and pattern is not _EMAIL:
        return pattern.sub(mask_value, text)
    pieces: list[str] = []
    last = 0
    for match in _finditer(detector, pattern, text):
        if _accept(detector, text, match):
            start, end = _span(match) if detector in _VALIDATORS else match.span()
            pieces.append(text[last:start])
            pieces.append(mask_value)
            last = end
    if not pieces:
        return text
    pieces.append(text[last:])
    return "".join(pieces)


@dataclass(frozen=True)
class PiiSpan:
    """One detected value: ``text[start:end]`` of the ORIGINAL text is a ``entity``."""

    start: int
    end: int
    entity: str


_BLANK = "\ue000"  # private-use filler: not alphanumeric, never matched by a detector
# The detection view of a text and its map back to the original (see ``pii_scan.shadow``).
_shadow = shadow
_DEFAULT_CONFIG = PiiConfig()


@lru_cache(maxsize=256)
def _ordered_tuple(detectors: tuple[str, ...]) -> tuple[str, ...]:
    rank = {d: i for i, d in enumerate(_ORDER)}
    return tuple(sorted(detectors, key=lambda d: rank.get(d, len(_ORDER))))


def _ordered(detectors: Iterable[str]) -> list[str]:
    return list(_ordered_tuple(tuple(detectors)))


def detect_pii_spans(
    text: str,
    config: PiiConfig | None = None,
    entities: Iterable[str] | None = None,
    strict: bool = False,
    *,
    ner_backend: str = "auto",
    ner_model: str | None = None,
) -> list[PiiSpan]:
    """Non-overlapping PII spans on the original ``text``, in text order.

    ``strict=True`` turns the context rules off: every phone-shaped number and every
    Luhn-valid card-shaped number is a span, even after an id or amount cue. Use it where
    over-redaction is acceptable and a miss is not (output policies, compliance redaction).

    Detection runs on a shadow string (NFKC, zero-width and bidi characters removed) so
    full-width digits or invisible separators cannot hide a value, and every span is
    mapped back to the original characters. Detectors run in ``PATTERNS`` order (secrets
    and specific formats before generic numbers); a later detector never re-detects
    inside an earlier one's span. ``entities`` defaults to ``config.detectors``.

    ``"person"`` and ``"location"`` are named entities (``nexus.guardrails.ner``, backend
    ``ner_backend``, spaCy model ``ner_model``); they never overlap a pattern detector's span.
    """
    config = config or _DEFAULT_CONFIG
    wanted = tuple(entities) if entities is not None else tuple(config.detectors)
    named = [w for w in wanted if w in NER_ENTITIES]
    if named:
        from .ner import add_entities

        rest = tuple(w for w in wanted if w not in NER_ENTITIES)
        found = detect_pii_spans(text, config, rest, strict) if rest else []
        return add_entities(text, found, named, backend=ner_backend, model=ner_model)
    if not text or not wanted or _cannot_match(text, wanted):
        return []
    view, offsets = _shadow(text)
    found: list[tuple[int, int, str]] = []
    for detector in _ordered_tuple(wanted):
        pattern = PATTERNS.get(detector)
        if not pattern:
            continue
        required = _REQUIRED.get(detector)
        if required and pattern is _BUILTIN[detector] and not _contains_any(view, required):
            continue
        hits: list[tuple[int, int]] = []
        for match in _finditer(detector, pattern, view):
            if _accept(detector, view, match, strict):
                hits.append(_span(match) if detector in _VALIDATORS else match.span())
        if detector == "phone" and pattern is _BUILTIN["phone"]:
            hits = _phone_hits(view, hits, strict)
        if hits:
            for start, end in hits:
                found.append((start, end, detector))
            # Later detectors see the earlier values as neutral filler of the same length.
            pieces, last = [], 0
            for start, end in hits:
                pieces.append(view[last:start])
                pieces.append(_BLANK * (end - start))
                last = end
            pieces.append(view[last:])
            view = "".join(pieces)
    spans = []
    for start, end, detector in sorted(found):
        if end <= start:
            continue
        if offsets is None:
            spans.append(PiiSpan(start, end, detector))
        else:
            spans.append(PiiSpan(offsets[start], offsets[end - 1] + 1, detector))
    return spans


def _phone_hits(
    view: str, hits: list[tuple[int, int]], strict: bool
) -> list[tuple[int, int]]:
    """Phone hits with their "+" / "(" prefix, plus cued national formats between them."""
    if hits:
        hits = [_phone_span(view, start, end) for start, end in hits]
        pieces, last = [], 0
        for start, end in hits:
            pieces.append(view[last:start])
            pieces.append(_BLANK * (end - start))
            last = end
        pieces.append(view[last:])
        rest = "".join(pieces)
    else:
        rest = view
    if not _TEN_DIGIT_RUN.search(rest):
        return hits
    extra = [
        _phone_span(rest, *_span(match))
        for match in _NATIONAL_PHONE.finditer(rest)
        if _national_phone_ok(rest, match)  # cue-gated in strict mode too
    ]
    return sorted(hits + extra) if extra else hits


def mask_spans(
    text: str,
    spans: Iterable[PiiSpan | tuple[int, int, str]],
    placeholder: str | Callable[[str], str] | None = None,
) -> str:
    """``text`` with every span replaced: by ``placeholder`` (a string, or a function of the
    entity name), or by the entity's standard mask (``[EMAIL]``, ...) when not given.
    Overlapping spans are merged (the earlier one wins)."""
    ordered = sorted(
        (s if isinstance(s, PiiSpan) else PiiSpan(int(s[0]), int(s[1]), str(s[2])) for s in spans),
        key=lambda s: (s.start, -s.end),
    )
    pieces: list[str] = []
    last = 0
    for span in ordered:
        if span.start < last:
            continue
        if callable(placeholder):
            token = placeholder(span.entity)
        elif placeholder is not None:
            token = placeholder
        else:
            token = MASKS.get(span.entity, f"[{span.entity.upper()}]")
        pieces.append(text[last : span.start])
        pieces.append(token)
        last = span.end
    pieces.append(text[last:])
    return "".join(pieces)


def mask_pii(text: str, config: PiiConfig) -> str:
    """``text`` with its PII masked; everything else is kept as written.

    Detection is Unicode-hardened (see ``detect_pii_spans``), but the stored text is not
    rewritten: exponents, ligatures and joiners (``x²``, ``ﬁ``, ZWJ in Indic scripts and
    emoji) survive. Only invisible bidi controls and zero-width spaces are removed, since
    they can hide text from readers.
    """
    if not config.enabled or not config.mask or not text:
        return text
    masked = mask_spans(text, detect_pii_spans(text, config))
    return strip_invisible(masked)
