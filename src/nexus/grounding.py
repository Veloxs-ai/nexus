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

"""Grounding: check every cited sentence of an answer against the passages it cites.

``check_answer(answer, passages, score=...)`` splits the answer into claims (sentences, list
items, table rows) with their inline citations (``[2]``, ``[2][3]``, ``[2, 3]``) and checks each
cited claim against the text of the passages it cites:

  numbers     every number, identifier and date in the claim must appear in the cited
              passages (``45,000`` = ``45000`` = ``45k`` within its precision); a missing one
              makes the claim unsupported whatever else matches. Small whole numbers with no
              unit (counts, "3 customers") and figures the question itself states are exempt.
  words       the share of the claim's content words found in the cited passages; a high
              share supports the claim without a model call
  re-ranker   otherwise the cross-encoder (``score(claim, windows)``, e.g. ``NexusClient.rerank``)
              scores the claim against the window of each cited passage that shares most of its
              words; paraphrases score high, unrelated text low. Without ``score`` the word share
              decides alone.

A claim is ``supported``, ``unsupported`` (a missing figure or id, a citation to no passage, or
almost no shared words and a re-ranker score near 0) or ``unverified`` (in between: a loose
paraphrase or a weak match, reported but never removed). Uncited
sentences are counted, not judged. ``cited_refs`` are the passages actually cited.
``strip_unsupported`` removes the unsupported claims from the answer text.

Standard library only. The cross-encoder is relevance, not entailment: a changed figure in an
otherwise matching sentence still scores high, which is why figures are checked exactly.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from .figure_text import spell_figures
from .text_terms import Number, key_tokens, numbers, terms

__all__ = [
    "Claim",
    "ClaimCheck",
    "GroundingConfig",
    "GroundingReport",
    "best_window",
    "check_answer",
    "cited_refs",
    "split_claims",
    "strip_unsupported",
]

Scorer = Callable[[str, list[str]], Sequence[float]]

_CITE = re.compile(r"\[(\d{1,3}(?:\s*[,;]\s*\d{1,3})*)\]")
_LEAD_CITES = re.compile(r"^\s*(?:\[\d{1,3}(?:\s*[,;]\s*\d{1,3})*\]\s*)+")
_BULLET = re.compile(r"^\s*(?:[-*+•]|\d{1,3}[.)])\s+")
_TABLE_RULE = re.compile(r"^\s*\|?\s*:?-{2,}")
_ABBREV = re.compile(
    r"(?:\b(?:e\.g|i\.e|etc|vs|approx|incl|no|nos|mr|mrs|ms|dr|st|inc|ltd|co)|\b[A-Z])\.$", re.I
)
_SENT_END = re.compile(r"[.!?]+[\"')\]]*\s+")
# Words an answer uses about its sources, never facts to be found in them.
_META = frozenset(
    terms(
        "according based passage passages source sources document documents cited mentioned states "
        "stated says said shown shows listed lists note noted also following below above answer "
        "provided information material context records record result results total"
    )
)


@dataclass
class Claim:
    """One sentence, list item or table row of an answer and the passages it cites."""

    text: str  # without citation markers
    start: int  # offsets in the answer (the claim's own text and its markers)
    end: int
    refs: tuple[int, ...]
    kind: str = "sentence"  # "sentence" | "item" | "row"


@dataclass
class ClaimCheck:
    claim: Claim
    status: str  # "supported" | "unsupported" | "unverified"
    reason: str = ""
    word_share: float = 0.0
    rerank: float | None = None
    missing: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class GroundingConfig:
    """Thresholds, tuned on Nexora's evaluation fixture (paraphrases must not be flagged)."""

    words_pass: float = 0.75  # word share that supports a claim without the re-ranker
    rerank_pass: float = 0.5  # re-ranker score that supports a claim
    # Unsupported by meaning only when almost nothing matches: re-ranker under ``rerank_fail`` and
    # word share under ``words_fail`` (a paraphrase shares more: "nine working days").
    rerank_fail: float = 0.02
    words_fail: float = 0.2
    words_floor: float = 0.4  # no re-ranker: below this the claim is unsupported
    words_only_pass: float = 0.6  # no re-ranker: word share that supports a claim
    window_chars: int = 700  # passage window shown to the re-ranker (its useful input length)
    max_rerank_claims: int = 24  # re-ranker calls per answer at most (the rest: words decide)


@dataclass
class GroundingReport:
    checks: list[ClaimCheck]
    uncited: int
    cited_refs: list[int]
    rerank_calls: int = 0

    def count(self, status: str) -> int:
        return sum(1 for c in self.checks if c.status == status)

    @property
    def faithfulness(self) -> float | None:
        """Share of the cited claims that are supported (None when nothing is cited)."""
        return self.count("supported") / len(self.checks) if self.checks else None

    def to_dict(self, max_flagged: int = 10) -> dict[str, Any]:
        flagged = [c for c in self.checks if c.status != "supported"][:max_flagged]
        faith = self.faithfulness
        return {
            "claims": len(self.checks),
            "supported": self.count("supported"),
            "unsupported": self.count("unsupported"),
            "unverified": self.count("unverified"),
            "uncited": self.uncited,
            "faithfulness": None if faith is None else round(faith, 4),
            "cited_refs": self.cited_refs,
            "flagged": [
                {
                    "text": c.claim.text[:240],
                    "refs": list(c.claim.refs),
                    "status": c.status,
                    "reason": c.reason,
                }
                for c in flagged
            ],
        }


def _refs(text: str) -> tuple[int, ...]:
    out: list[int] = []
    for m in _CITE.finditer(text):
        for part in re.split(r"[,;]", m.group(1)):
            n = int(part.strip())
            if n not in out:
                out.append(n)
    return tuple(out)


def cited_refs(answer: str) -> list[int]:
    """The passage numbers an answer cites, in first-cited order."""
    return list(_refs(answer or ""))


def _sentences(line: str, offset: int) -> list[tuple[str, int, int]]:
    """Split one line into sentences; markers after a full stop stay with that sentence."""
    out: list[tuple[str, int, int]] = []
    start = 0
    for m in _SENT_END.finditer(line):
        head = line[start : m.start() + 1].rstrip()
        if _ABBREV.search(head) or not head.strip():
            continue
        end = m.end()
        lead = _LEAD_CITES.match(line[end:])
        if lead:  # "... USD. [1] Next" -> the marker cites the sentence before it
            end += lead.end()
        out.append((line[start:end], offset + start, offset + end))
        start = end
    if start < len(line):
        out.append((line[start:], offset + start, offset + len(line)))
    return [(t, s, e) for t, s, e in out if t.strip()]


def _clean(text: str) -> str:
    """Claim text: citation markers and Markdown emphasis removed, spacing normalised."""
    text = _CITE.sub(" ", text).replace("**", "").replace("__", "")
    return re.sub(r"\s+([.,;:!?])", r"\1", " ".join(text.split()))


def split_claims(answer: str) -> list[Claim]:
    """Claims of an answer: sentences of paragraphs, list items and table rows (headings, code
    and table rules skipped). A list item or table row without a citation of its own takes
    the citations of the line that introduces it ("... are: [2]")."""
    claims: list[Claim] = []
    pos, in_code, intro_refs = 0, False, ()
    table_header = True
    for raw in (answer or "").splitlines(keepends=True):
        line, offset = raw.rstrip("\n"), pos
        pos += len(raw)
        stripped = line.strip()
        if stripped.startswith("```"):
            in_code = not in_code
            continue
        if in_code or not stripped or stripped.startswith("#") or _TABLE_RULE.match(stripped):
            if not stripped:
                intro_refs, table_header = (), True
            continue
        if stripped.startswith("|"):
            if table_header:  # the header row names columns: nothing to check
                table_header = False
                continue
            refs = _refs(line) or intro_refs
            text = _clean(stripped.strip("|").replace("|", " ; "))
            claims.append(Claim(text, offset, offset + len(line), refs, "row"))
            continue
        bullet = _BULLET.match(line)
        if bullet:
            refs = _refs(line) or intro_refs
            claims.append(
                Claim(_clean(line[bullet.end() :]), offset, offset + len(line), refs, "item")
            )
            continue
        for sentence, start, end in _sentences(line, offset):
            text = _clean(sentence)
            if not text.endswith(":"):  # "The matching records are:" introduces, it claims nothing
                claims.append(Claim(text, start, end, _refs(sentence)))
        # "The matching records are: [2]" introduces a list: its items take these citations.
        bare = _CITE.sub("", stripped).rstrip()
        intro_refs = _refs(line) if bare.endswith(":") else ()
    return [c for c in claims if c.text and any(ch.isalnum() for ch in c.text)]


def best_window(claim: str, passage: str, max_chars: int = 700) -> str:
    """The part of ``passage`` (at most ``max_chars``, whole sentences where possible) that
    shares most content words with ``claim``: what the re-ranker is shown."""
    if len(passage) <= max_chars:
        return passage
    want = terms(claim)
    parts = [p for p in re.split(r"(?<=[.!?\n])\s+", passage) if p.strip()]
    if not parts:
        return passage[:max_chars]
    scores = [len(want & terms(p)) for p in parts]
    best, best_score, start, used, score = (0, 0), -1, 0, 0, 0
    for end, part in enumerate(parts):
        used += len(part) + 1
        score += scores[end]
        while used > max_chars and start < end:
            used -= len(parts[start]) + 1
            score -= scores[start]
            start += 1
        if score > best_score:
            best, best_score = (start, end), score
    return " ".join(parts[best[0] : best[1] + 1])[:max_chars]


def _figures(text: str) -> tuple[list[Number], set[str]]:
    """Numbers and ids/dates of ``text`` with figures in words spelled as digits; the year of
    each ISO date also counts as a number ("in 2026" is found in "2026-03-05")."""
    spelled = spell_figures(text)
    keys = key_tokens(spelled)
    years = [Number(k[:4], float(k[:4]), 0.5, year=True) for k in keys if _ISO_DAY.match(k)]
    return numbers(spelled) + years, keys


def _figures_missing(
    claim: str, passage_numbers: list[Number], passage_keys: set[str], asked: str
) -> list[str]:
    missing = []
    asked_numbers, asked_keys = _figures(asked)
    claim_numbers, claim_keys = _figures(claim)
    for key in claim_keys:
        if key in passage_keys or key in asked_keys:
            continue
        fiscal = _FISCAL.match(key)  # "FY2025" is said "fiscal year 2025" too
        year = float(fiscal.group(1)) if fiscal else None
        if year is not None and any(p.year and p.value == year for p in passage_numbers):
            continue
        missing.append(key)
    for num in claim_numbers:
        if num.soft or any(num.matches(a) for a in asked_numbers):
            continue
        if not any(num.matches(p) for p in passage_numbers):
            missing.append(num.text)
    return missing


_ISO_DAY = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_FISCAL = re.compile(r"^(?:fy|cy)-?((?:19|20)\d{2})$")


def _terms(text: str) -> set[str]:
    """Content terms, with figures in words as digits ("nine days" matches "9 days")."""
    return terms(spell_figures(text))


def _word_share(claim_terms: set[str], passage_terms: set[str]) -> float:
    # Ids are checked exactly (``_figures_missing``); one-letter parts carry nothing.
    want = {
        t
        for t in claim_terms
        if t not in _META and len(t) > 1 and (t.isdigit() or not any(c.isdigit() for c in t))
    }
    if not want:
        return 1.0
    return len(want & passage_terms) / len(want)


def check_answer(
    answer: str,
    passages: Mapping[int, str],
    score: Scorer | None = None,
    question: str = "",
    config: GroundingConfig | None = None,
) -> GroundingReport:
    """Check every cited claim of ``answer`` against ``passages`` ({citation number: text})."""
    cfg = config or GroundingConfig()
    claims = split_claims(answer)
    cache: dict[int, tuple[set[str], list[Number], set[str]]] = {}

    def facts(ref: int) -> tuple[set[str], list[Number], set[str]]:
        if ref not in cache:
            text = passages.get(ref) or ""
            nums, keys = _figures(text)
            cache[ref] = (_terms(text), nums, keys)
        return cache[ref]

    checks: list[ClaimCheck] = []
    pending: list[ClaimCheck] = []
    uncited = 0
    for claim in claims:
        if not claim.refs:
            uncited += 1
            continue
        unknown = [r for r in claim.refs if r not in passages]
        if len(unknown) == len(claim.refs):
            checks.append(
                ClaimCheck(claim, "unsupported", f"cites [{unknown[0]}], which is not a source")
            )
            continue
        known = [r for r in claim.refs if r in passages]
        words: set[str] = set()
        nums: list[Number] = []
        keys: set[str] = set()
        for ref in known:
            w, n, k = facts(ref)
            words |= w
            nums += n
            keys |= k
        missing = _figures_missing(claim.text, nums, keys, question)
        share = _word_share(_terms(claim.text), words)
        check = ClaimCheck(claim, "supported", word_share=round(share, 4), missing=missing)
        if missing:
            check.status = "unsupported"
            check.reason = "not in the cited passage: " + ", ".join(missing[:4])
        elif share >= cfg.words_pass:
            pass
        elif score is None:
            if share < cfg.words_floor:
                check.status, check.reason = "unsupported", "the cited passage does not say this"
            elif share < cfg.words_only_pass:
                check.status, check.reason = "unverified", "partly found in the cited passage"
        else:
            pending.append(check)
        checks.append(check)
    calls = 0
    for check in pending:
        if calls >= cfg.max_rerank_claims:  # past the budget the word share decides
            if check.word_share < cfg.words_floor:
                check.status, check.reason = "unverified", "not checked by the re-ranker"
            continue
        windows = [
            best_window(check.claim.text, passages[r], cfg.window_chars)
            for r in check.claim.refs
            if r in passages
        ]
        calls += 1
        best = max((float(s) for s in score(check.claim.text, windows)), default=0.0)
        check.rerank = round(best, 4)
        if best >= cfg.rerank_pass:
            continue
        if best < cfg.rerank_fail and check.word_share < cfg.words_fail:
            check.status, check.reason = "unsupported", "the cited passage does not say this"
        else:
            check.status, check.reason = "unverified", "weak match with the cited passage"
    return GroundingReport(checks, uncited, cited_refs(answer), calls)


def strip_unsupported(answer: str, report: GroundingReport) -> str:
    """``answer`` without its unsupported claims (their text and citation markers)."""
    cuts = sorted(
        ((c.claim.start, c.claim.end) for c in report.checks if c.status == "unsupported"),
        reverse=True,
    )
    out = answer
    for start, end in cuts:
        out = out[:start] + out[end:]
    out = re.sub(r"[ \t]+\n", "\n", out)
    out = re.sub(r"\n{3,}", "\n\n", out)
    return out.strip()
