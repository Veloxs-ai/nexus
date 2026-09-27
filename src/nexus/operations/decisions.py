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

"""Decision tables: versioned, data-defined business rules with an evaluation trace.

A table is a list of rules, each with a ``when`` condition and ``then`` outputs, in the
spirit of DMN decision tables. Output values may themselves be expressions (prefix
``=``), so a rule can compute ``{"priority": "=10 - days_to_due"}``.

Hit policies:
  * ``first``    — the first matching rule wins (ordered strategy tables)
  * ``priority`` — the matching rule with the highest ``priority`` wins
  * ``collect``  — every matching rule contributes an output (e.g. all reason codes)
  * ``unique``   — exactly one rule may match; more than one is a configuration error

Every evaluation returns a trace (which rules were checked and which matched) so each
automated decision can be explained and audited later.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from .expressions import ExpressionError, compile_expression, evaluate, referenced_fields

HIT_POLICIES = ("first", "priority", "collect", "unique")


class DecisionError(ValueError):
    """A decision table is invalid, or a unique table matched more than one rule."""


@dataclass(frozen=True)
class Rule:
    id: str
    when: str
    then: dict[str, Any]
    priority: int = 0
    description: str = ""


@dataclass
class DecisionResult:
    table: str
    version: str
    outputs: list[dict[str, Any]]
    matched: list[str]
    evaluated: int
    used_default: bool = False
    errors: list[str] = field(default_factory=list)

    @property
    def output(self) -> dict[str, Any] | None:
        """Single output for first/priority/unique tables (None when nothing matched)."""
        return self.outputs[0] if self.outputs else None

    def as_dict(self) -> dict[str, Any]:
        return {
            "table": self.table,
            "version": self.version,
            "outputs": self.outputs,
            "matched": self.matched,
            "evaluated": self.evaluated,
            "used_default": self.used_default,
            "errors": self.errors,
        }


def _resolve_outputs(
    then: dict[str, Any], facts: dict[str, Any], today: date | None
) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in then.items():
        if isinstance(value, str) and value.startswith("="):
            out[key] = evaluate(value[1:], facts, today)
        else:
            out[key] = value
    return out


@dataclass
class DecisionTable:
    name: str
    rules: list[Rule]
    hit_policy: str = "first"
    default: dict[str, Any] | None = None
    inputs: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.hit_policy not in HIT_POLICIES:
            raise DecisionError(f"hit_policy must be one of {HIT_POLICIES}")
        seen: set[str] = set()
        for rule in self.rules:
            if rule.id in seen:
                raise DecisionError(f"duplicate rule id '{rule.id}' in table '{self.name}'")
            seen.add(rule.id)
            try:
                compile_expression(rule.when)
                for value in rule.then.values():
                    if isinstance(value, str) and value.startswith("="):
                        compile_expression(value[1:])
            except ExpressionError as exc:
                raise DecisionError(f"rule '{rule.id}' in table '{self.name}': {exc}") from exc

    # -- serialization -------------------------------------------------------
    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> DecisionTable:
        rules = [
            Rule(
                id=str(r.get("id") or f"R{i + 1}"),
                when=str(r.get("when") or "True"),
                then=dict(r.get("then") or {}),
                priority=int(r.get("priority") or 0),
                description=str(r.get("description") or ""),
            )
            for i, r in enumerate(data.get("rules") or [])
        ]
        return cls(
            name=str(data.get("name") or "decision"),
            rules=rules,
            hit_policy=str(data.get("hit_policy") or "first"),
            default=data.get("default"),
            inputs=list(data.get("inputs") or []),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "hit_policy": self.hit_policy,
            "inputs": self.inputs,
            "default": self.default,
            "rules": [
                {
                    "id": r.id,
                    "when": r.when,
                    "then": r.then,
                    "priority": r.priority,
                    "description": r.description,
                }
                for r in self.rules
            ],
        }

    @property
    def version(self) -> str:
        """Content hash: identical rules always produce the same version id."""
        payload = json.dumps(self.to_dict(), sort_keys=True, default=str).encode("utf-8")
        return hashlib.sha256(payload).hexdigest()[:16]

    def fields(self) -> set[str]:
        """Every fact the table reads (declared inputs plus names used in conditions)."""
        names = set(self.inputs)
        for rule in self.rules:
            names |= referenced_fields(rule.when)
            for value in rule.then.values():
                if isinstance(value, str) and value.startswith("="):
                    names |= referenced_fields(value[1:])
        return names

    # -- evaluation ----------------------------------------------------------
    def evaluate(self, facts: dict[str, Any], today: date | None = None) -> DecisionResult:
        matches: list[Rule] = []
        errors: list[str] = []
        for rule in self.rules:
            try:
                if evaluate(rule.when, facts, today):
                    matches.append(rule)
                    if self.hit_policy == "first":
                        break
            except ExpressionError as exc:  # pragma: no cover - compiled in __post_init__
                errors.append(f"{rule.id}: {exc}")

        if self.hit_policy == "unique" and len(matches) > 1:
            raise DecisionError(
                f"table '{self.name}' is unique but rules {[m.id for m in matches]} all matched"
            )
        if self.hit_policy == "priority" and matches:
            matches = [max(matches, key=lambda r: r.priority)]

        outputs = [{**_resolve_outputs(m.then, facts, today), "_rule": m.id} for m in matches]
        used_default = False
        if not outputs and self.default is not None:
            outputs = [{**_resolve_outputs(self.default, facts, today), "_rule": "default"}]
            used_default = True
        return DecisionResult(
            table=self.name,
            version=self.version,
            outputs=outputs,
            matched=[m.id for m in matches],
            evaluated=len(self.rules),
            used_default=used_default,
            errors=errors,
        )
