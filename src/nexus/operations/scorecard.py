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

"""Points scorecards: the transparent risk model lenders already use and validate.

A scorecard is a list of characteristics (``bounces_6m``, ``months_on_book``), each split
into bins that award points. The total is a score on a fixed scale, defined by the
usual three numbers: ``base_points`` at ``base_odds`` (good:bad), and ``pdo`` — the
points that double the odds. From that scale every score maps to a probability of the
bad outcome, so bands and thresholds can be set in either unit.

Reason codes follow the adverse-action convention: the characteristics where the
subject lost the most points against the best possible bin, largest first. They are
stable, explainable and auditable — exactly what model risk management asks for —
and a fitted logistic model can be converted into this form without loss.

Everything is data (``Scorecard.from_dict``), bins use the safe expression language
with the characteristic's value bound to ``value``::

    {"id": "BOUNCES_6M", "field": "bounces_6m",
     "description": "Auto-debit bounces in the last 6 months",
     "bins": [{"when": "value == 0", "points": 60},
              {"when": "value == 1", "points": 25},
              {"when": "value >= 2", "points": 0}],
     "missing_points": 20}
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from .expressions import ExpressionError, compile_expression, evaluate


class ScorecardError(ValueError):
    """A scorecard definition is invalid."""


@dataclass(frozen=True)
class Bin:
    when: str
    points: float
    label: str = ""


@dataclass(frozen=True)
class Characteristic:
    id: str
    field: str
    bins: tuple[Bin, ...]
    missing_points: float = 0.0
    description: str = ""

    @property
    def max_points(self) -> float:
        return max([b.points for b in self.bins] + [self.missing_points])


@dataclass
class ScoreResult:
    score: float
    probability: float  # probability of the bad outcome
    band: str | None
    reasons: list[dict[str, Any]]
    contributions: dict[str, dict[str, Any]] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "score": self.score,
            "probability": self.probability,
            "band": self.band,
            "reasons": self.reasons,
            "contributions": self.contributions,
        }


@dataclass
class Scorecard:
    name: str
    characteristics: list[Characteristic]
    base_points: float = 600.0
    base_odds: float = 50.0
    pdo: float = 20.0
    bands: list[tuple[str, float]] = field(default_factory=list)  # (band, min_score), high first
    max_reasons: int = 4
    outputs: dict[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.characteristics:
            raise ScorecardError(f"scorecard '{self.name}' needs at least one characteristic")
        if self.pdo <= 0 or self.base_odds <= 0:
            raise ScorecardError("pdo and base_odds must be positive")
        seen: set[str] = set()
        for ch in self.characteristics:
            if ch.id in seen:
                raise ScorecardError(f"duplicate characteristic id '{ch.id}'")
            seen.add(ch.id)
            if not ch.bins:
                raise ScorecardError(f"characteristic '{ch.id}' has no bins")
            for b in ch.bins:
                try:
                    compile_expression(b.when)
                except ExpressionError as exc:
                    raise ScorecardError(f"characteristic '{ch.id}': {exc}") from exc
        scores = [s for _, s in self.bands]
        if scores != sorted(scores, reverse=True):
            raise ScorecardError("bands must be ordered from the highest min_score down")
        unknown = set(self.outputs) - {"score", "probability", "band"}
        if unknown:
            raise ScorecardError(f"unknown scorecard outputs {sorted(unknown)}")

    # -- scale -----------------------------------------------------------------------
    @property
    def factor(self) -> float:
        return self.pdo / math.log(2)

    @property
    def offset(self) -> float:
        return self.base_points - self.factor * math.log(self.base_odds)

    def probability(self, score: float) -> float:
        """Probability of the bad outcome at ``score`` on this scorecard's scale."""
        log_odds = (score - self.offset) / self.factor
        return 1.0 / (1.0 + math.exp(min(700.0, log_odds)))

    def band_for(self, score: float) -> str | None:
        for band, minimum in self.bands:
            if score >= minimum:
                return band
        return self.bands[-1][0] if self.bands else None

    # -- scoring ---------------------------------------------------------------------
    def score(self, facts: dict[str, Any], today: date | None = None) -> ScoreResult:
        total = 0.0
        contributions: dict[str, dict[str, Any]] = {}
        for ch in self.characteristics:
            value = facts.get(ch.field)
            points, matched = ch.missing_points, "missing"
            if value is not None:
                points, matched = 0.0, "no bin matched"
                scope = {**facts, "value": value}
                for n, b in enumerate(ch.bins):
                    if evaluate(b.when, scope, today) is True:
                        points, matched = b.points, b.label or b.when or f"bin {n + 1}"
                        break
            total += points
            contributions[ch.id] = {
                "field": ch.field,
                "value": value,
                "bin": matched,
                "points": points,
                "shortfall": round(ch.max_points - points, 4),
            }
        ranked = sorted(
            (c for c in self.characteristics if contributions[c.id]["shortfall"] > 0),
            key=lambda c: (-contributions[c.id]["shortfall"], c.id),
        )
        reasons = [
            {
                "code": c.id,
                "description": c.description or c.field,
                "value": contributions[c.id]["value"],
                "points_lost": contributions[c.id]["shortfall"],
            }
            for c in ranked[: self.max_reasons]
        ]
        score = round(total, 2)
        return ScoreResult(
            score=score,
            probability=round(self.probability(score), 6),
            band=self.band_for(score),
            reasons=reasons,
            contributions=contributions,
        )

    def outputs_for(self, result: ScoreResult) -> dict[str, Any]:
        """Facts this scorecard contributes to later strategy steps."""
        names = self.outputs or {"score": f"{self.name}_score"}
        values = {"score": result.score, "probability": result.probability, "band": result.band}
        return {fact: values[key] for key, fact in names.items()}

    def fields(self) -> set[str]:
        from .expressions import referenced_fields

        used = {c.field for c in self.characteristics}
        for c in self.characteristics:
            for b in c.bins:
                used |= referenced_fields(b.when) - {"value"}
        return used

    @property
    def version(self) -> str:
        blob = json.dumps(self.to_dict(), sort_keys=True, default=str)
        return hashlib.sha256(blob.encode()).hexdigest()[:12]

    # -- (de)serialization ---------------------------------------------------------------
    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Scorecard:
        try:
            characteristics = [
                Characteristic(
                    id=str(c["id"]),
                    field=str(c["field"]),
                    bins=tuple(
                        Bin(str(b["when"]), float(b["points"]), str(b.get("label") or ""))
                        for b in c.get("bins") or []
                    ),
                    missing_points=float(c.get("missing_points", 0)),
                    description=str(c.get("description") or ""),
                )
                for c in data.get("characteristics") or []
            ]
            bands = [(str(b["band"]), float(b["min_score"])) for b in data.get("bands") or []]
            return cls(
                name=str(data.get("name") or "scorecard"),
                characteristics=characteristics,
                base_points=float(data.get("base_points", 600)),
                base_odds=float(data.get("base_odds", 50)),
                pdo=float(data.get("pdo", 20)),
                bands=bands,
                max_reasons=int(data.get("max_reasons", 4)),
                outputs={str(k): str(v) for k, v in (data.get("outputs") or {}).items()},
            )
        except (KeyError, TypeError, ValueError) as exc:
            if isinstance(exc, ScorecardError):
                raise
            raise ScorecardError(f"invalid scorecard: {exc}") from exc

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "base_points": self.base_points,
            "base_odds": self.base_odds,
            "pdo": self.pdo,
            "bands": [{"band": b, "min_score": s} for b, s in self.bands],
            "max_reasons": self.max_reasons,
            "outputs": self.outputs,
            "characteristics": [
                {
                    "id": c.id,
                    "field": c.field,
                    "description": c.description,
                    "missing_points": c.missing_points,
                    "bins": [
                        {
                            "when": b.when,
                            "points": b.points,
                            **({"label": b.label} if b.label else {}),
                        }
                        for b in c.bins
                    ],
                }
                for c in self.characteristics
            ],
        }
