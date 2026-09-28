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

"""Strategies: derived facts plus an ordered chain of decision tables.

A strategy definition is plain data::

    {
      "facts":  {"days_to_due": "days_until(next_due_date)"},   # computed in order
      "scorecards": {"early_risk": {...}},                       # Scorecard specs (optional)
      "tables": {"treatment": {...}},                            # DecisionTable specs
      "steps":  ["early_risk", "treatment"]                      # evaluation order
    }

A step names a scorecard or a decision table. Each step's outputs become facts for
the next step (the scorecard sets ``risk_band``; ``treatment`` reads it). The result
keeps every step's trace, the scores, and a flat list of reason codes
(``"treatment:OVERDUE"``, ``"early_risk:BOUNCES_6M"``) for the decision record.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date
from functools import lru_cache
from typing import Any

from .decisions import DecisionResult, DecisionTable
from .expressions import evaluate
from .scorecard import Scorecard, ScoreResult


@dataclass
class StrategyResult:
    facts: dict[str, Any]
    outputs: dict[str, Any]
    steps: list[DecisionResult] = field(default_factory=list)
    reason_codes: list[str] = field(default_factory=list)
    scores: dict[str, ScoreResult] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "outputs": self.outputs,
            "reason_codes": self.reason_codes,
            "steps": [s.as_dict() for s in self.steps],
            "scores": {name: r.as_dict() for name, r in self.scores.items()},
        }


@lru_cache(maxsize=512)
def _table(serialized: str) -> DecisionTable:
    return DecisionTable.from_dict(json.loads(serialized))


@lru_cache(maxsize=128)
def _scorecard(serialized: str) -> Scorecard:
    return Scorecard.from_dict(json.loads(serialized))


def evaluate_strategy(
    definition: dict[str, Any], inputs: dict[str, Any], today: date | None = None
) -> StrategyResult:
    """Compute derived facts, then run each step's table in order."""
    facts = dict(inputs)
    for name, expression in (definition.get("facts") or {}).items():
        facts[name] = evaluate(str(expression), facts, today)

    tables = definition.get("tables") or {}
    scorecards = definition.get("scorecards") or {}
    outputs: dict[str, Any] = {}
    steps: list[DecisionResult] = []
    reasons: list[str] = []
    scores: dict[str, ScoreResult] = {}
    for step in definition.get("steps") or [*scorecards, *tables]:
        if step in scorecards:
            card = _scorecard(json.dumps({"name": step, **scorecards[step]}, sort_keys=True))
            scored = card.score(facts, today)
            scores[step] = scored
            for key, value in card.outputs_for(scored).items():
                facts[key] = value
                outputs[key] = value
            reasons.extend(f"{step}:{r['code']}" for r in scored.reasons)
            continue
        spec = {"name": step, **tables[step]}
        result = _table(json.dumps(spec, sort_keys=True, default=str)).evaluate(facts, today)
        steps.append(result)
        for out in result.outputs:
            for key, value in out.items():
                if key.startswith("_"):
                    continue
                facts[key] = value
                outputs[key] = value
        matched = result.matched or (["default"] if result.used_default else [])
        reasons.extend(f"{step}:{rule}" for rule in matched)
    return StrategyResult(
        facts=facts, outputs=outputs, steps=steps, reason_codes=reasons, scores=scores
    )
