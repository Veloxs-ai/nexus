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

"""Cases: long-lived subjects (a loan, a machine) moving through explicit states.

"Long cases, short runs": a case's journey lives as data — its state and the next
time it must be re-evaluated — while each evaluation is a short, idempotent run.
This module provides the pieces that make those runs safe:

  * ``CaseMachine`` — allowed states and transitions; illegal transitions raise
  * ``idempotency_key`` — a permanent, human-readable key for an action, so the same
    reminder for the same instalment on the same channel can never be sent twice
  * ``stable_bucket`` / ``assign_arm`` — deterministic test/control assignment for
    champion–challenger experiments (same subject → same arm, every run)
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from typing import Any


class TransitionError(ValueError):
    """A case was asked to move to a state its machine does not allow."""


@dataclass
class CaseMachine:
    states: list[str]
    transitions: dict[str, list[str]]
    initial: str
    terminal: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        known = set(self.states)
        if self.initial not in known:
            raise TransitionError(f"initial state '{self.initial}' is not a declared state")
        for src, targets in self.transitions.items():
            unknown = ({src} | set(targets)) - known
            if unknown:
                raise TransitionError(f"transitions reference undeclared states: {sorted(unknown)}")
        for state in self.terminal:
            if state not in known:
                raise TransitionError(f"terminal state '{state}' is not declared")

    def can(self, current: str, target: str) -> bool:
        return current == target or target in self.transitions.get(current, [])

    def assert_transition(self, current: str, target: str) -> None:
        if current in self.terminal and current != target:
            raise TransitionError(f"case is closed in state '{current}'")
        if not self.can(current, target):
            allowed = self.transitions.get(current, [])
            raise TransitionError(
                f"cannot move from '{current}' to '{target}' (allowed: {allowed})"
            )

    def is_terminal(self, state: str) -> bool:
        return state in self.terminal

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CaseMachine:
        return cls(
            states=list(data["states"]),
            transitions={k: list(v) for k, v in (data.get("transitions") or {}).items()},
            initial=str(data["initial"]),
            terminal=list(data.get("terminal") or []),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "states": self.states,
            "transitions": self.transitions,
            "initial": self.initial,
            "terminal": self.terminal,
        }


# A general-purpose lifecycle that fits collections and operational incidents alike.
DEFAULT_MACHINE = CaseMachine(
    states=[
        "open",
        "monitoring",
        "contacted",
        "promised",
        "awaiting_approval",
        "escalated",
        "resolved",
        "closed",
    ],
    transitions={
        "open": ["monitoring", "contacted", "awaiting_approval", "escalated", "resolved", "closed"],
        "monitoring": ["contacted", "awaiting_approval", "escalated", "resolved", "closed"],
        "contacted": [
            "monitoring",
            "promised",
            "awaiting_approval",
            "escalated",
            "resolved",
            "closed",
        ],
        "promised": [
            "monitoring",
            "contacted",
            "awaiting_approval",
            "escalated",
            "resolved",
            "closed",
        ],
        "awaiting_approval": [
            "monitoring",
            "contacted",
            "promised",
            "escalated",
            "resolved",
            "closed",
        ],
        "escalated": ["monitoring", "contacted", "awaiting_approval", "resolved", "closed"],
        "resolved": ["monitoring", "closed"],
    },
    initial="open",
    terminal=["closed"],
)

_KEY_PART = re.compile(r"[^A-Za-z0-9._:-]+")


def idempotency_key(*parts: Any, max_length: int = 200) -> str:
    """Permanent key for an action, e.g. ``loan-123|emi:2026-10|T-3|sms``.

    Parts are normalized (unsafe characters replaced) and joined with ``|``. Keys longer
    than ``max_length`` keep a readable prefix plus a hash of the full value, so they
    stay unique and indexable.
    """
    if not parts:
        raise ValueError("idempotency_key needs at least one part")
    cleaned = [_KEY_PART.sub("-", str(p).strip()).strip("-") or "_" for p in parts]
    key = "|".join(cleaned)
    if len(key) <= max_length:
        return key
    digest = hashlib.sha256(key.encode("utf-8")).hexdigest()[:24]
    return f"{key[: max_length - 25]}#{digest}"


def stable_bucket(subject_id: str, experiment: str, buckets: int = 100) -> int:
    """Deterministic bucket in [0, buckets) for a subject within an experiment."""
    digest = hashlib.sha256(f"{experiment}\x1f{subject_id}".encode()).digest()
    return int.from_bytes(digest[:8], "big") % buckets


def assign_arm(subject_id: str, experiment: str, arms: dict[str, int]) -> str:
    """Pick an arm by percentage weights.

    Example: ``{"champion": 80, "challenger": 10, "control": 10}``.
    """
    total = sum(arms.values())
    if total <= 0:
        raise ValueError("arm weights must add up to more than zero")
    point = stable_bucket(subject_id, experiment, 10_000) * total / 10_000
    running = 0.0
    for arm, weight in arms.items():
        running += weight
        if point < running:
            return arm
    return next(reversed(arms))
