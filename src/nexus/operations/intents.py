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

"""Reply intent: what a customer's message asks for, with a confidence.

Replies to payment reminders are short and repetitive ("will pay by the 10th",
"salary late hai", "already paid, UTR …", "job chali gayi, time chahiye"), so a
transparent weighted lexicon handles most of them offline, in English, Hinglish,
Hindi (Devanagari) and Marathi, with no data leaving the process. Each intent's
score combines its matched patterns (noisy-OR); the confidence is the winner's score
discounted by the runner-up, so mixed messages get low confidence and go to a person.

  * ``intent``       — the primary intent (``INTENTS``)
  * ``signals``      — other intents present (e.g. a promise that also says
    "please don't call": ``stop_contact`` with channel ``voice``)
  * ``entities``     — promise date, payment reference (UTR/RRN), amount, months of
    relief requested, the channel a stop request refers to
  * ``needs_review`` — below the review threshold: a person decides

When the rules are unsure, an ``IntentModel`` trained on reviewers' labels (word and
character n-gram naive Bayes, self-hosted) is consulted next, and only accepted above
its own confidence threshold. An optional ``llm`` callable is the last resort. It receives
the message after ``redact`` (phone numbers, e-mail addresses, account-like numbers,
PAN and Aadhaar masked) and must return ``{"intent": ..., "confidence": ...}``;
anything else is ignored. Its confidence is capped so model output never skips
review on its own say-so.
"""

from __future__ import annotations

import contextlib
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any

INTENTS = (
    "promise_to_pay",
    "hardship",
    "already_paid",
    "dispute",
    "mandate_issue",
    "stop_contact",
    "wrong_number",
    "callback_request",
    "other",
)
LLM_CONFIDENCE_CAP = 0.85
# Requests about *how* to be contacted accompany a substantive reply ("will pay tomorrow,
# don't call"); they are reported as signals and do not lower the main intent's confidence.
MODIFIERS = ("stop_contact", "callback_request")
# Pairs that naturally occur together and do not make a reply ambiguous.
COMPATIBLE = {frozenset({"mandate_issue", "promise_to_pay"})}

# (pattern, weight). Patterns are matched case-insensitively on the whole message.
Lexicon = dict[str, list[tuple[str, float]]]
DEFAULT_LEXICON: Lexicon = {
    "promise_to_pay": [
        (r"\b(will|shall|i'?ll|going to|gonna)\s+(pay|clear|deposit|transfer|send)", 0.75),
        (r"\bpay(ing)?\s+(it\s+)?(by|on|before|till|until|next|tomorrow|today)\b", 0.7),
        (r"\b(by|before|on)\s+the\s+\d{1,2}(st|nd|rd|th)?\b", 0.45),
        (
            r"\b(salary|payment)\s+(is\s+|got\s+|has\s+been\s+)?"
            r"(late|delayed|pending|not credited)",
            0.4,
        ),
        (
            r"\b(kar|bhej|de|bhar|jama\s+kar)\s*(dunga|dungi|denge|doonga|dungaa|dege|deta|deti)\b",
            0.8,
        ),
        (r"\b(pay|payment)\s+kar\s*(dunga|dungi|denge|doonga)\b", 0.85),
        (r"\btak\s+(pay|payment|bhej|jama|kar|de)", 0.55),
        (r"\b\d{1,2}\s*(tareekh|tarikh|tarik|taarikh)\b", 0.5),
        (r"\bsalary\s+(aane|aate)\s+(par|pe|hi)\b", 0.6),
        (r"\b(next week|agle\s+hafte|agle\s+hafta|pudhchya\s+aathvad\w*)\b", 0.4),
        (r"\b(bharto|bharen|bharin|bharun\s+deto|bharun\s+denar)\b", 0.8),
        (r"(भर दूंगा|भर दूँगा|भेज दूंगा|भेज दूँगा|कर दूंगा|कर दूँगा|जमा कर दूंगा|दे दूंगा)", 0.8),
        (r"(भरतो|भरेन|भरून देतो)", 0.8),
    ],
    "hardship": [
        (r"\b(lost|losing)\s+(my\s+)?(job|employment|income)\b", 0.9),
        (r"\b(job|naukri|naukari|kaam)\s+(chali|chala|chhut|chhoot|gayi|gaya|geli|gela|nahi)", 0.9),
        (r"\b(hospital|hospitali[sz]ed|surgery|accident|medical|illness|bimar|beemar|ill)\b", 0.6),
        (r"\b(emi\s+holiday|moratorium|restructur\w*|reschedul\w*|extension|relief)\b", 0.75),
        (r"\b(\d+|few|some|couple of)\s+(months?|mahine|mahina|mahinon|mahinyan?)\b", 0.45),
        (r"\b(time|samay|mohlat|waqt|vel)\s+(chahiye|chaiye|do|de\s*do|dya|dijiye|milega)", 0.5),
        (r"\b(business|dhandha|dukaan|shop)\s+(band|closed|loss|ghata|nuksan)", 0.85),
        (r"\b(cannot|can'?t|unable to|not able to)\s+(pay|afford)", 0.7),
        (r"\b(death|passed away|expired|guzar|nidhan)\b", 0.7),
        (r"(नौकरी चली|नौकरी छूट|समय चाहिए|मोहलत|बीमार|अस्पताल|नोकरी गेली|वेळ द्या)", 0.85),
    ],
    "already_paid": [
        (r"\b(already|just)\s+(paid|pay|transferred|deposited|cleared)", 0.9),
        (r"\b(i\s+)?(have\s+|had\s+)?(paid|transferred|deposited)\b", 0.55),
        (
            r"\b(payment|paisa|paise|emi)\s+(ho\s*gaya|ho\s*gayi|kar\s*diya|kar\s*diye|bhej\s*diya|"
            r"jama\s*kar\s*diya|bhar\s*diya|zala|jhala)",
            0.9,
        ),
        (
            r"\b(utr|rrn|txn|transaction|ref(erence)?)\s*(no\.?|number|id)?\s*[:#-]?\s*[a-z0-9]{8,}",
            0.6,
        ),
        (r"\b(bharle|bharla|bharli)\b", 0.85),
        (r"(भुगतान कर दिया|पेमेंट हो गया|पैसे भेज दिए|जमा कर दिया|भरले|भरला)", 0.9),
    ],
    "dispute": [
        (
            r"\b(wrong|incorrect|excess|extra|double)\s+(charge|amount|deduction|debit|emi|penalty)",
            0.8,
        ),
        (r"\b(charge|penalty|fine|amount|emi)\s+(is\s+)?(wrong|incorrect|not correct|unfair)", 0.8),
        (r"\bwhy\s+(is|was|has)\s+(my\s+)?(emi|amount|charge|penalty|interest)", 0.6),
        (r"\b(had|have|there was)\s+(sufficient\s+|enough\s+)?balance\b", 0.6),
        (r"\b(complaint|dispute|ombudsman|grievance)\b", 0.7),
        (r"\b(galat|jyada|zyada)\s+(charge|paisa|amount|kata|kaat)", 0.75),
    ],
    "mandate_issue": [
        (
            r"\b(cancel+ed|stopped|revoked|closed)\s+(the\s+|my\s+)?(auto[- ]?debit|mandate|nach|"
            r"e-?mandate|si|standing instruction|autopay)",
            0.9,
        ),
        (r"\b(auto[- ]?debit|mandate|nach|e-?mandate|autopay)\b", 0.45),
        (r"\b(account|khata|a/c)\s+(band|closed|close|changed|badal)", 0.75),
        (r"\b(new|naya|nayi|change)\s+(bank\s+)?(account|mandate|khata)", 0.6),
    ],
    "stop_contact": [
        (r"^\s*stop\s*$", 0.95),
        (r"\b(unsubscribe|opt[- ]?out)\b", 0.9),
        (
            r"\b(stop|don'?t|do not|never)\s+(calling|call|messaging|message|texting|contacting|"
            r"contact)\s*(me)?\b",
            0.85,
        ),
        (r"\b(call|phone|message|msg|sms)\s+(mat|na|nako)\s*(karo|kare|kijiye|kara)?\b", 0.8),
        (r"\b(harass\w*|pareshan)\b", 0.6),
        (r"(कॉल मत करो|फोन मत करो|मैसेज मत करो|परेशान)", 0.8),
    ],
    "wrong_number": [
        (r"\bwrong\s+(number|person|no\.?)\b", 0.95),
        (r"\b(don'?t|do not)\s+have\s+(any|a)\s+loan\b", 0.85),
        (r"\bnot\s+(my|mine)\s+(loan|number)\b", 0.8),
        (r"\b(galat|ghalat)\s+(number|no)\b", 0.95),
        (r"\b(mera|meri)\s+(koi\s+)?loan\s+nahi\b", 0.85),
        (r"(गलत नंबर|चुकीचा नंबर)", 0.95),
    ],
    "callback_request": [
        (r"\b(call|phone)\s+(me\s+)?(back|later|tomorrow|after|in the evening)\b", 0.7),
        (r"\b(please|pls|plz)\s+call\b(?!\s+(mat|na|nako|mut)\b)", 0.55),
        (r"\b(baat|talk|speak)\s+(karni|karna|karo|to)\b", 0.5),
    ],
}

STOP_CHANNEL_HINTS = {
    "voice": re.compile(r"\b(call|calling|phone|kol)\b|कॉल|फोन", re.I),
    "sms": re.compile(r"\b(sms|text|texting|message|messaging|msg)\b|मैसेज", re.I),
    "whatsapp": re.compile(r"\bwhats\s*app\b", re.I),
}
_MONTHS = {
    m: i + 1
    for i, m in enumerate(
        ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"]
    )
}
_WEEKDAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]


@dataclass
class IntentResult:
    intent: str
    confidence: float
    signals: dict[str, float] = field(default_factory=dict)
    entities: dict[str, Any] = field(default_factory=dict)
    matched: list[str] = field(default_factory=list)
    method: str = "rules"
    needs_review: bool = False

    def as_dict(self) -> dict[str, Any]:
        entities = {
            k: v.isoformat() if isinstance(v, date) else v for k, v in self.entities.items()
        }
        return {
            "intent": self.intent,
            "confidence": self.confidence,
            "signals": self.signals,
            "entities": entities,
            "matched": self.matched,
            "method": self.method,
            "needs_review": self.needs_review,
        }


# ---------------------------------------------------------------------------
# Redaction
# ---------------------------------------------------------------------------

_REDACTIONS = [
    (re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+"), "[email]"),
    (re.compile(r"\b[A-Z]{5}\d{4}[A-Z]\b", re.I), "[pan]"),
    (re.compile(r"\b\d{4}\s?\d{4}\s?\d{4}\b"), "[id-number]"),  # Aadhaar-like
    (re.compile(r"(?:\+?\d{1,3}[\s-]?)?\b[6-9]\d{9}\b"), "[phone]"),
    (re.compile(r"\+?\d[\d\s().-]{8,}\d"), "[number]"),
    (re.compile(r"\b[A-Z0-9]*\d[A-Z0-9]{7,}\b", re.I), "[reference]"),
]


def redact(text: str) -> str:
    """Mask personal identifiers before text leaves the process (e.g. to an LLM)."""
    out = text
    for pattern, replacement in _REDACTIONS:
        out = pattern.sub(replacement, out)
    return out


# ---------------------------------------------------------------------------
# Entities
# ---------------------------------------------------------------------------


def _day_of_month(day: int, today: date) -> date | None:
    for months_ahead in (0, 1):
        y, m = today.year, today.month + months_ahead
        if m > 12:
            y, m = y + 1, 1
        try:
            candidate = date(y, m, day)
        except ValueError:
            continue
        if candidate >= today:
            return candidate
    return None


def promise_date(text: str, today: date) -> date | None:
    """The date a promise refers to, if the message names one."""
    t = text.lower()
    m = re.search(r"\b(\d{1,2})[/.-](\d{1,2})(?:[/.-](\d{2,4}))?\b", t)
    if m:
        d, mo = int(m.group(1)), int(m.group(2))
        y = int(m.group(3)) if m.group(3) else today.year
        y = y + 2000 if y < 100 else y
        try:
            found = date(y, mo, d)
            if not m.group(3) and found < today:
                found = date(y + 1, mo, d)
            return found
        except ValueError:
            pass
    m = re.search(r"\b(\d{1,2})(?:st|nd|rd|th)?\s+(" + "|".join(_MONTHS) + r")[a-z]*\b", t)
    if m:
        try:
            found = date(today.year, _MONTHS[m.group(2)], int(m.group(1)))
            return found if found >= today else date(today.year + 1, found.month, found.day)
        except ValueError:
            pass
    m = re.search(r"\b(\d{1,2})(?:st|nd|rd|th)\b", t) or re.search(
        r"\b(\d{1,2})\s*(?:tareekh|tarikh|tarik|taarikh|tarkhela|tarkhe)\b", t
    )
    if m and 1 <= int(m.group(1)) <= 31:
        return _day_of_month(int(m.group(1)), today)
    if re.search(r"\b(day after tomorrow|parso|parson)\b|परसों", t):
        return today + timedelta(days=2)
    if re.search(r"\b(tomorrow|kal|udya|udyaa)\b|कल|उद्या", t):
        return today + timedelta(days=1)
    if re.search(r"\b(today|aaj|aj)\b|आज", t):
        return today
    if re.search(r"\b(next week|agle hafte|agle hafta|pudhchya aathvad\w*)\b|अगले हफ्ते", t):
        return today + timedelta(days=7)
    for i, name in enumerate(_WEEKDAYS):
        if re.search(rf"\b{name}\b", t):
            ahead = (i - today.weekday()) % 7 or 7
            return today + timedelta(days=ahead)
    return None


def extract_entities(text: str, today: date) -> dict[str, Any]:
    entities: dict[str, Any] = {}
    found = promise_date(text, today)
    if found:
        entities["promise_date"] = found
    ref = re.search(
        r"\b(?:utr|rrn|txn|transaction|ref(?:erence)?)\s*(?:no\.?|number|id)?\s*[:#-]?\s*"
        r"([A-Z0-9]{8,22})\b",
        text,
        re.I,
    )
    if ref:
        entities["payment_reference"] = ref.group(1).upper()
    amount = re.search(r"(?:₹|rs\.?|inr)\s*([\d,]+(?:\.\d{1,2})?)", text, re.I)
    if amount:
        with contextlib.suppress(ValueError):
            entities["amount"] = float(amount.group(1).replace(",", ""))
    months = re.search(r"\b(\d{1,2})\s+(?:months?|mahine|mahina|mahinon|mahinyan?)\b", text, re.I)
    if months:
        entities["months_requested"] = int(months.group(1))
    return entities


# ---------------------------------------------------------------------------
# Classifier
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# A small model that learns from reviewers' labels
# ---------------------------------------------------------------------------

_WORD = re.compile(r"[^\W_]+", re.UNICODE)


def _features(text: str) -> list[str]:
    """Words plus character 3–4-grams inside words: robust to Hinglish spelling variants."""
    feats: list[str] = []
    for word in _WORD.findall((text or "").lower()):
        if word.isdigit():
            word = "#" * min(len(word), 6)  # dates and amounts by shape, never by value
        feats.append(f"w:{word}")
        padded = f"<{word}>"
        for n in (3, 4):
            feats.extend(f"c:{padded[i : i + n]}" for i in range(max(0, len(padded) - n + 1)))
    return feats


@dataclass
class IntentModel:
    """Multinomial naive Bayes over word and character n-gram features.

    Trained on reviewers' labels (the text never leaves the process), serialized as plain
    counts, deterministic, and cheap to retrain. Used only where the rules are unsure.
    """

    class_counts: dict[str, int] = field(default_factory=dict)
    feature_counts: dict[str, dict[str, int]] = field(default_factory=dict)
    vocabulary: list[str] = field(default_factory=list)
    max_features: int = 20_000

    @classmethod
    def fit(cls, examples: list[tuple[str, str]], max_features: int = 20_000) -> IntentModel:
        from collections import Counter

        totals: Counter[str] = Counter()
        per_class: dict[str, Counter[str]] = {}
        classes: Counter[str] = Counter()
        for text, intent in examples:
            if intent not in INTENTS:
                continue
            feats = _features(text)
            classes[intent] += 1
            per_class.setdefault(intent, Counter()).update(feats)
            totals.update(set(feats))
        vocab = [f for f, _ in totals.most_common(max_features)]
        keep = set(vocab)
        return cls(
            class_counts=dict(classes),
            feature_counts={
                c: {f: n for f, n in cnt.items() if f in keep} for c, cnt in per_class.items()
            },
            vocabulary=vocab,
            max_features=max_features,
        )

    @property
    def trained(self) -> bool:
        return len(self.class_counts) >= 2 and sum(self.class_counts.values()) >= 10

    def probabilities(self, text: str) -> dict[str, float]:
        import math

        if not self.trained:
            return {}
        vocab = set(self.vocabulary)
        feats = [f for f in _features(text) if f in vocab]
        total_docs = sum(self.class_counts.values())
        size = len(vocab) or 1
        logs: dict[str, float] = {}
        for intent, n_docs in self.class_counts.items():
            counts = self.feature_counts.get(intent, {})
            denom = sum(counts.values()) + size
            logp = math.log(n_docs / total_docs)
            for f in feats:
                logp += math.log((counts.get(f, 0) + 1) / denom)
            logs[intent] = logp
        top = max(logs.values())
        exp = {k: math.exp(v - top) for k, v in logs.items()}
        z = sum(exp.values())
        return {k: round(v / z, 6) for k, v in sorted(exp.items(), key=lambda kv: -kv[1])}

    def predict(self, text: str) -> tuple[str, float] | None:
        probs = self.probabilities(text)
        if not probs:
            return None
        intent, p = next(iter(probs.items()))
        return intent, p

    def to_dict(self) -> dict[str, Any]:
        return {
            "class_counts": self.class_counts,
            "feature_counts": self.feature_counts,
            "vocabulary": self.vocabulary,
            "max_features": self.max_features,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> IntentModel:
        return cls(
            class_counts={str(k): int(v) for k, v in (data.get("class_counts") or {}).items()},
            feature_counts={
                str(c): {str(f): int(n) for f, n in fs.items()}
                for c, fs in (data.get("feature_counts") or {}).items()
            },
            vocabulary=[str(f) for f in data.get("vocabulary") or []],
            max_features=int(data.get("max_features", 20_000)),
        )


def evaluate_model(examples: list[tuple[str, str]], folds: int = 5) -> dict[str, Any]:
    """k-fold accuracy of IntentModel on labelled examples (deterministic folds)."""
    import hashlib

    labelled = [(t, i) for t, i in examples if i in INTENTS and (t or "").strip()]
    if len(labelled) < 10:
        return {
            "examples": len(labelled),
            "accuracy": None,
            "note": "needs at least 10 labelled replies",
        }
    fold = [int(hashlib.sha256(t.encode()).hexdigest(), 16) % folds for t, _ in labelled]
    correct = 0
    confusion: dict[str, dict[str, int]] = {}
    for k in range(folds):
        train = [e for e, f in zip(labelled, fold, strict=True) if f != k]
        model = IntentModel.fit(train)
        for (text, truth), f in zip(labelled, fold, strict=True):
            if f != k:
                continue
            guess = (model.predict(text) or ("other", 0.0))[0]
            correct += guess == truth
            confusion.setdefault(truth, {}).setdefault(guess, 0)
            confusion[truth][guess] += 1
    return {
        "examples": len(labelled),
        "accuracy": round(correct / len(labelled), 4),
        "confusion": confusion,
        "note": f"{folds}-fold cross-validation",
    }


class IntentClassifier:
    def __init__(
        self,
        lexicon: Lexicon | None = None,
        review_below: float = 0.6,
        llm: Callable[[str], dict[str, Any]] | None = None,
        model: IntentModel | None = None,
        model_min_confidence: float = 0.8,
    ) -> None:
        self.lexicon = lexicon or DEFAULT_LEXICON
        self.review_below = review_below
        self.llm = llm
        self.model = model if model is not None and model.trained else None
        self.model_min_confidence = model_min_confidence
        self._compiled = {
            intent: [(re.compile(p, re.I), w, p) for p, w in patterns]
            for intent, patterns in self.lexicon.items()
        }

    def scores(self, text: str) -> tuple[dict[str, float], list[str]]:
        scores: dict[str, float] = {}
        matched: list[str] = []
        for intent, patterns in self._compiled.items():
            miss = 1.0
            for rx, weight, source in patterns:
                if rx.search(text):
                    miss *= 1.0 - weight
                    matched.append(f"{intent}:{source[:40]}")
            if miss < 1.0:
                scores[intent] = round(1.0 - miss, 4)
        return scores, matched

    def classify(self, text: str, today: date | None = None) -> IntentResult:
        today = today or date.today()
        text = (text or "").strip()[:2000]
        entities = extract_entities(text, today) if text else {}
        scores, matched = self.scores(text) if text else ({}, [])
        ranked = sorted(scores.items(), key=lambda kv: (-kv[1], INTENTS.index(kv[0])))
        substantive = [kv for kv in ranked if kv[0] not in MODIFIERS and kv[1] >= 0.5]
        primary = substantive or ranked
        if primary:
            intent, top = primary[0]
            rivals = [s for name, s in primary[1:] if frozenset({intent, name}) not in COMPATIBLE]
            confidence = round(max(0.0, top - 0.5 * (rivals[0] if rivals else 0.0)), 4)
        else:
            intent, confidence = "other", 0.0
        signals = {name: s for name, s in ranked if name != intent and s >= 0.5}
        if "stop_contact" in scores:
            entities["stop_channels"] = [
                ch for ch, rx in STOP_CHANNEL_HINTS.items() if rx.search(text)
            ] or ["all"]
        result = IntentResult(
            intent=intent,
            confidence=confidence,
            signals=signals,
            entities=entities,
            matched=matched,
            needs_review=confidence < self.review_below,
        )
        if result.needs_review and self.model is not None and text:
            guess = self.model.predict(text)
            if guess and guess[1] >= self.model_min_confidence:
                confidence = round(min(guess[1], LLM_CONFIDENCE_CAP), 4)
                result = IntentResult(
                    intent=guess[0],
                    confidence=confidence,
                    signals=result.signals,
                    entities=result.entities,
                    matched=result.matched,
                    method="model",
                    needs_review=confidence < self.review_below,
                )
        if result.needs_review and self.llm is not None and text:
            result = self._ask_llm(text, result)
        return result

    def _ask_llm(self, text: str, fallback: IntentResult) -> IntentResult:
        try:
            answer = self.llm(redact(text)) if self.llm else None
        except Exception:  # an unavailable model must never break reply handling
            return fallback
        if not isinstance(answer, dict) or answer.get("intent") not in INTENTS:
            return fallback
        try:
            confidence = min(LLM_CONFIDENCE_CAP, max(0.0, float(answer.get("confidence", 0))))
        except (TypeError, ValueError):
            return fallback
        return IntentResult(
            intent=str(answer["intent"]),
            confidence=round(confidence, 4),
            signals=fallback.signals,
            entities=fallback.entities,
            matched=fallback.matched,
            method="llm",
            needs_review=confidence < self.review_below,
        )


LLM_INSTRUCTIONS = (
    "Classify a customer's reply to a loan repayment reminder. Answer with JSON only: "
    '{"intent": one of ' + ", ".join(INTENTS) + ', "confidence": number between 0 and 1}. '
    "promise_to_pay = will pay later; hardship = cannot pay because of job loss, illness or "
    "similar and asks for time or relief; already_paid = says payment was made; dispute = "
    "disagrees with an amount or charge; mandate_issue = auto-debit or bank account problem; "
    "stop_contact = asks not to be contacted; wrong_number = not the borrower; "
    "callback_request = asks for a call; other = anything else. The reply may be in English, "
    "Hindi, Hinglish or Marathi. Personal details are masked in brackets."
)
