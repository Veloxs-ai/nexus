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
  * ``scorecard``   — points scorecards with probability scaling and reason codes
  * ``strategy``    — derived facts plus an ordered chain of scorecards and tables
  * ``contact_policy`` — contact hours, frequency caps, consent and do-not-disturb,
    with jurisdiction presets (India RBI, US Regulation F)
  * ``cases``       — case state machines, permanent action keys and deterministic
    test/control assignment
  * ``engine``      — ``plan_case`` (facts → decision, next state, safe actions) and a
    small in-memory ``OperationsEngine``
  * ``intents``     — multilingual reply intent with confidence, entities and redaction
  * ``messaging``   — safe templates and channel providers (dry run, signed webhook,
    SMTP, WhatsApp Cloud, Twilio)
  * ``experiments`` — holdout comparisons with Wilson intervals and significance
  * ``signals``     — condition monitoring: explainable anomaly scores, data quality, time
    to limit and failure-mode diagnosis from streaming sensor readings
  * ``workorders``  — ServiceNow incidents, Maximo work orders, Teams notifications (idempotent)
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
from .engine import CasePlan, OperationsEngine, PlannedAction, experiment_arm, plan_case
from .experiments import Comparison, RateEstimate, compare, rate, summarize_arms
from .expressions import ExpressionError, compile_expression, evaluate, referenced_fields
from .intents import INTENTS, IntentClassifier, IntentModel, IntentResult, evaluate_model, redact
from .messaging import (
    ChannelProvider,
    DryRunProvider,
    Message,
    SendResult,
    TemplateError,
    WebhookProvider,
    mask_recipient,
    provider_from_config,
    render_template,
    template_fields,
)
from .scorecard import Scorecard, ScorecardError, ScoreResult
from .signals import (
    Assessment,
    AssetMonitor,
    Diagnosis,
    SignalSpec,
    diagnose,
    specs_from_dict,
    window_stats,
)
from .strategy import StrategyResult, evaluate_strategy
from .workorders import (
    TICKET_STATES,
    WORK_PROVIDERS,
    DryRunWorkProvider,
    MaximoProvider,
    ServiceNowProvider,
    TeamsProvider,
    TicketStatus,
    WorkItem,
    WorkProvider,
    WorkResult,
    work_provider_from_config,
)

__all__ = [
    "DEFAULT_MACHINE",
    "INTENTS",
    "TICKET_STATES",
    "WORK_PROVIDERS",
    "Assessment",
    "AssetMonitor",
    "CaseMachine",
    "CasePlan",
    "ChannelProvider",
    "Comparison",
    "ContactDecision",
    "ContactPolicy",
    "DecisionError",
    "DecisionResult",
    "DecisionTable",
    "Diagnosis",
    "DryRunProvider",
    "DryRunWorkProvider",
    "ExpressionError",
    "FrequencyCap",
    "IntentClassifier",
    "IntentModel",
    "IntentResult",
    "MaximoProvider",
    "Message",
    "OperationsEngine",
    "PlannedAction",
    "RateEstimate",
    "Rule",
    "ScoreResult",
    "Scorecard",
    "ScorecardError",
    "SendResult",
    "ServiceNowProvider",
    "SignalSpec",
    "StrategyResult",
    "TeamsProvider",
    "TemplateError",
    "TicketStatus",
    "TransitionError",
    "WebhookProvider",
    "WorkItem",
    "WorkProvider",
    "WorkResult",
    "assign_arm",
    "compare",
    "compile_expression",
    "diagnose",
    "evaluate",
    "evaluate_model",
    "evaluate_strategy",
    "experiment_arm",
    "idempotency_key",
    "mask_recipient",
    "plan_case",
    "provider_from_config",
    "rate",
    "redact",
    "referenced_fields",
    "render_template",
    "specs_from_dict",
    "stable_bucket",
    "summarize_arms",
    "template_fields",
    "window_stats",
    "work_provider_from_config",
]
