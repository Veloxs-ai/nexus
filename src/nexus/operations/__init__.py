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

"""Nexus Operations — building blocks for governed, continuous decisions.

Turning live data into accountable actions (loan reminders before a due date, work
orders for a degrading machine) needs the same few primitives every time. They are
pure Python with no extra dependencies, so they run the same inside a SaaS platform
and inside a customer's own infrastructure:

  * ``expressions`` — a safe expression language for business rules
  * ``decisions``   — versioned decision tables with hit policies and traces
  * ``contact_policy`` — contact hours, frequency caps, consent and do-not-disturb,
    with jurisdiction presets (India RBI, US Regulation F)
  * ``strategy``    — derived facts plus an ordered chain of decision tables
  * ``cases``       — case state machines, permanent action keys and deterministic
    test/control assignment
"""

from .cases import (
    DEFAULT_MACHINE,
    CaseMachine,
    TransitionError,
    assign_arm,
    idempotency_key,
    stable_bucket,
)
from .contact_policy import ContactDecision, ContactPolicy, FrequencyCap
from .decisions import DecisionError, DecisionResult, DecisionTable, Rule
from .expressions import ExpressionError, compile_expression, evaluate, referenced_fields
from .strategy import StrategyResult, evaluate_strategy

__all__ = [
    "DEFAULT_MACHINE",
    "CaseMachine",
    "ContactDecision",
    "ContactPolicy",
    "DecisionError",
    "DecisionResult",
    "DecisionTable",
    "ExpressionError",
    "FrequencyCap",
    "Rule",
    "StrategyResult",
    "TransitionError",
    "assign_arm",
    "compile_expression",
    "evaluate",
    "evaluate_strategy",
    "idempotency_key",
    "referenced_fields",
    "stable_bucket",
]
