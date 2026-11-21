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
import unicodedata
from collections.abc import Callable, Iterable
from dataclasses import dataclass

from .config import PiiConfig
from .models import Finding
from .normalization import is_invisible, luhn_valid, normalize_text, strip_invisible

PATTERNS = {
    # Secrets first: they may contain digit runs the generic patterns would split.
    "jwt": re.compile(r"\beyJ[A-Za-z0-9_-]{5,}\.[A-Za-z0-9_-]{5,}\.[A-Za-z0-9_-]{5,}"),
    "api_key": re.compile(
        r"\b(?:sk-(?:proj-|ant-)?[A-Za-z0-9_-]{16,}|AKIA[0-9A-Z]{16}|AIza[0-9A-Za-z_-]{35}"
        r"|gh[pousr]_[A-Za-z0-9]{36}|xox[abprs]-[A-Za-z0-9-]{10,}|sk_(?:live|test)_[A-Za-z0-9]{16,})"
    ),
    "email": re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"),
    "ssn": re.compile(r"(?<![\w-])\d{3}-\d{2}-\d{4}(?![\w-])"),
    "credit_card": re.compile(r"\b(?:\d[ -]?){13,19}\b"),
    "phone": re.compile(
        r"(?:(?<![\w+])\+\d{1,3}[-.\s]?\d{2,5}[-.\s]?\d{3,5}[-.\s]?\d{3,5}\b)"
        r"|\b(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b"
    ),
    "ip_address": re.compile(r"\b(?:(?:25[0-5]|2[0-4]\d|1?\d?\d)\.){3}(?:25[0-5]|2[0-4]\d|1?\d?\d)\b"),
}

MASKS = {
    "jwt": "[JWT_TOKEN]",
    "api_key": "[API_KEY]",
    "email": "[EMAIL]",
    "ssn": "[SSN]",
    "credit_card": "[CREDIT_CARD]",
    "phone": "[PHONE]",
    "ip_address": "[IP_ADDRESS]",
}

# Detectors are always applied in PATTERNS order (specific formats before generic numbers).
_ORDER = list(PATTERNS)

# --- context rules for the number detectors ---------------------------------------
# A formatted number (separators, parentheses, a leading "+") is a phone number unless it
# is part of a longer token ("ORD-555-123-4567", "1234567890.50") or the value of an
# identifier/timestamp key. A bare digit run is one when a cue precedes it ("call",
# "my number is", "text me at") or when it has the shape of a dialable number (NANP
# ``[2-9]XX[2-9]XXXXXX``, an Indian mobile ``[6-9]XXXXXXXXX``) and nothing marks it as an
# identifier, amount or date. Table columns are masked by column (``pii_columns``), so
# id and amount columns never reach this free-text rule.
_CONTEXT_CHARS = 32
_PHONE_CUE = re.compile(
    r"(?i)(?:(?:\b|_)(?:phone|ph|tel|telephone|mobile|mob|cell|cellphone|call|calls|called|calling"
    r"|contact|whatsapp|fax|sms|dial|reach|text|texts|texting|ping|ring|message|msg)(?:\b|_)"
    r"|\b(?:my|our|his|her|their|your|personal|home|work|office|landline)\s+(?:number|no\.?|#)"
    r"(?:\s+is)?\b)[^\n|;]{0,24}$"
)
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
        tail = re.match(r"\d+", text[end + 1 :])
        return bool(tail) and len(tail.group(0)) <= 3
    after2 = text[end + 1] if end + 1 < len(text) else ""
    return after in "-./" and after2.isdigit()


def _phone_ok(text: str, match: re.Match[str]) -> bool:
    value = match.group(0)
    start, end = match.span()
    context = text[max(0, start - _CONTEXT_CHARS) : start]
    cued = bool(_PHONE_CUE.search(context))
    if _attached(text, start, end, cued):
        return False
    if cued:
        return True
    if _ID_CUE.search(context) or _AMOUNT_CUE.search(context):
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
    cued = bool(_CARD_CUE.search(context))
    if not luhn_valid(value) or _attached(text, start, end, cued):
        return False
    if cued:
        return True
    if _ID_CUE.search(context):
        return False
    digits = "".join(ch for ch in value if ch.isdigit())
    return bool(_CARD_PREFIX.match(digits))


_VALIDATORS = {"phone": _phone_ok, "credit_card": _card_ok}


def _accept(detector: str, text: str, match: re.Match[str], strict: bool = False) -> bool:
    if strict:  # every pattern match counts; cards still need a valid Luhn checksum
        return detector != "credit_card" or luhn_valid(text[slice(*_span(match))])
    validator = _VALIDATORS.get(detector)
    return validator(text, match) if validator else True


def _detector_findings(detector: str, text: str) -> bool:
    pattern = PATTERNS.get(detector)
    if not pattern:
        return False
    return any(_accept(detector, text, match) for match in pattern.finditer(text))


def detect_pii(text: str, config: PiiConfig) -> list[Finding]:
    if not config.enabled:
        return []
    normalized = normalize_text(text)
    findings: list[Finding] = []
    for detector in config.detectors:
        if _detector_findings(detector, normalized):
            findings.append(
                Finding(category="pii", message=f"Detected {detector}", severity="warn")
            )
    return findings


def mask_detector(text: str, detector: str) -> str:
    """Mask the values one detector accepts in ``text`` (already normalized)."""
    pattern = PATTERNS.get(detector)
    if not pattern:
        return text
    mask_value = MASKS[detector]
    if detector not in _VALIDATORS:
        return pattern.sub(mask_value, text)
    pieces: list[str] = []
    last = 0
    for match in pattern.finditer(text):
        if _accept(detector, text, match):
            start, end = _span(match)
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


def _shadow(text: str) -> tuple[str, list[int] | None]:
    """The detection view of ``text`` (NFKC, invisible characters removed) and, unless it
    is identical to ``text``, the original index of each of its characters."""
    if text.isascii():
        return text, None
    chars: list[str] = []
    offsets: list[int] = []
    for i, char in enumerate(text):
        if is_invisible(char):
            continue
        for piece in unicodedata.normalize("NFKC", char):
            chars.append(piece)
            offsets.append(i)
    return "".join(chars), offsets


def _ordered(detectors: Iterable[str]) -> list[str]:
    return sorted(detectors, key=lambda d: _ORDER.index(d) if d in _ORDER else len(_ORDER))


def detect_pii_spans(
    text: str,
    config: PiiConfig | None = None,
    entities: Iterable[str] | None = None,
    strict: bool = False,
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
    """
    config = config or PiiConfig()
    wanted = list(entities) if entities is not None else list(config.detectors)
    if not text or not wanted:
        return []
    shadow, offsets = _shadow(text)
    found: list[tuple[int, int, str]] = []
    for detector in _ordered(wanted):
        pattern = PATTERNS.get(detector)
        if not pattern:
            continue
        hits: list[tuple[int, int]] = []
        for match in pattern.finditer(shadow):
            if _accept(detector, shadow, match, strict):
                hits.append(_span(match) if detector in _VALIDATORS else match.span())
        if hits:
            for start, end in hits:
                found.append((start, end, detector))
            # Later detectors see the earlier values as neutral filler of the same length.
            pieces, last = [], 0
            for start, end in hits:
                pieces.append(shadow[last:start])
                pieces.append(_BLANK * (end - start))
                last = end
            pieces.append(shadow[last:])
            shadow = "".join(pieces)
    spans = []
    for start, end, detector in sorted(found):
        if end <= start:
            continue
        if offsets is None:
            spans.append(PiiSpan(start, end, detector))
        else:
            spans.append(PiiSpan(offsets[start], offsets[end - 1] + 1, detector))
    return spans


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
