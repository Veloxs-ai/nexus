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

from collections import Counter
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from nexus.operations import (
    DEFAULT_MACHINE,
    ContactPolicy,
    DecisionError,
    DecisionTable,
    ExpressionError,
    TransitionError,
    assign_arm,
    evaluate,
    idempotency_key,
    referenced_fields,
    stable_bucket,
)

TODAY = date(2026, 9, 27)


# -- expressions ------------------------------------------------------------------


def test_expressions_cover_business_rules():
    facts = {
        "days_to_due": 3,
        "risk_band": "high",
        "loan": {"product": "PL", "emi": 12500},
        "bounces": [1, 0, 1],
        "due_date": "2026-09-30",
    }
    assert evaluate("days_to_due <= 3 and risk_band == 'high'", facts, TODAY) is True
    assert evaluate("loan.product in ['PL', 'VL'] and loan['emi'] > 10000", facts, TODAY) is True
    assert evaluate("days_until(due_date)", facts, TODAY) == 3
    assert evaluate("days_since('2026-09-20')", facts, TODAY) == 7
    assert evaluate("'call' if risk_band == 'high' else 'sms'", facts, TODAY) == "call"
    assert evaluate("coalesce(missing, 5) * 2", facts, TODAY) == 10
    assert evaluate("0 < days_to_due < 7", facts, TODAY) is True


def test_missing_fields_do_not_match_instead_of_raising():
    assert evaluate("dpd > 30", {}, TODAY) is False
    assert evaluate("dpd == None", {}, TODAY) is True
    assert evaluate("amount + 5", {}, TODAY) is None
    assert evaluate("name > 5", {"name": "x"}, TODAY) is False  # incompatible types


@pytest.mark.parametrize(
    "unsafe",
    [
        "__import__('os').system('id')",
        "().__class__.__bases__",
        "open('/etc/passwd')",
        "[x for x in range(3)]",
        "lambda: 1",
        "loan._secret",
        "eval('1')",
        "min(1, key=abs)",
    ],
)
def test_unsafe_expressions_are_rejected(unsafe):
    with pytest.raises(ExpressionError):
        evaluate(unsafe, {}, TODAY)


def test_referenced_fields_ignores_functions_and_literals():
    assert referenced_fields("days_until(due_date) <= 3 and risk_band == 'high'") == {
        "due_date",
        "risk_band",
    }


# -- decision tables ----------------------------------------------------------------

TREATMENT = {
    "name": "pre_due_treatment",
    "hit_policy": "first",
    "inputs": ["days_to_due", "risk_band"],
    "rules": [
        {
            "id": "HIGH_T3",
            "when": "days_to_due <= 3 and risk_band == 'high'",
            "then": {"action": "call_task", "channel": "voice", "priority": "=10 - days_to_due"},
        },
        {
            "id": "ANY_T7",
            "when": "days_to_due <= 7",
            "then": {"action": "reminder", "channel": "sms"},
        },
    ],
    "default": {"action": "none"},
}


def test_first_hit_policy_and_computed_outputs():
    table = DecisionTable.from_dict(TREATMENT)
    high = table.evaluate({"days_to_due": 2, "risk_band": "high"})
    assert high.output == {
        "action": "call_task",
        "channel": "voice",
        "priority": 8,
        "_rule": "HIGH_T3",
    }
    assert high.matched == ["HIGH_T3"]
    low = table.evaluate({"days_to_due": 6, "risk_band": "low"})
    assert low.output["action"] == "reminder"
    none = table.evaluate({"days_to_due": 20, "risk_band": "low"})
    assert none.used_default and none.output["action"] == "none"


def test_collect_priority_and_unique_policies():
    reasons = DecisionTable.from_dict(
        {
            "name": "reasons",
            "hit_policy": "collect",
            "rules": [
                {"id": "B", "when": "bounces_6m >= 2", "then": {"code": "REPEAT_BOUNCE"}},
                {"id": "N", "when": "loan_age_months < 3", "then": {"code": "NEW_LOAN"}},
            ],
        }
    )
    assert [
        o["code"] for o in reasons.evaluate({"bounces_6m": 3, "loan_age_months": 1}).outputs
    ] == ["REPEAT_BOUNCE", "NEW_LOAN"]

    prio = DecisionTable.from_dict(
        {
            "name": "p",
            "hit_policy": "priority",
            "rules": [
                {"id": "lo", "when": "True", "then": {"x": 1}, "priority": 1},
                {"id": "hi", "when": "True", "then": {"x": 2}, "priority": 9},
            ],
        }
    )
    assert prio.evaluate({}).output["x"] == 2

    unique = DecisionTable.from_dict(
        {
            "name": "u",
            "hit_policy": "unique",
            "rules": [
                {"id": "a", "when": "True", "then": {}},
                {"id": "b", "when": "True", "then": {}},
            ],
        }
    )
    with pytest.raises(DecisionError):
        unique.evaluate({})


def test_tables_validate_on_load_and_version_by_content():
    with pytest.raises(DecisionError):
        DecisionTable.from_dict(
            {"name": "bad", "rules": [{"id": "x", "when": "__import__('os')", "then": {}}]}
        )
    with pytest.raises(DecisionError):
        DecisionTable.from_dict(
            {
                "name": "dup",
                "rules": [
                    {"id": "a", "when": "True", "then": {}},
                    {"id": "a", "when": "True", "then": {}},
                ],
            }
        )
    assert DecisionTable.from_dict(TREATMENT).version == DecisionTable.from_dict(TREATMENT).version
    changed = {**TREATMENT, "default": {"action": "watch"}}
    assert DecisionTable.from_dict(changed).version != DecisionTable.from_dict(TREATMENT).version
    assert DecisionTable.from_dict(TREATMENT).fields() == {"days_to_due", "risk_band"}


# -- contact policy -------------------------------------------------------------------

IST = ZoneInfo("Asia/Kolkata")


def test_india_contact_hours_and_next_allowed_time():
    policy = ContactPolicy.preset("IN_RBI")
    evening = datetime(2026, 9, 27, 20, 30, tzinfo=IST)
    decision = policy.check("voice", evening, recipient_timezone="Asia/Kolkata")
    assert not decision.allowed and "outside contact hours" in decision.reasons[0]
    assert decision.next_allowed_at == datetime(2026, 9, 28, 8, 0, tzinfo=IST).astimezone(UTC)
    assert policy.check(
        "voice", datetime(2026, 9, 27, 10, 0, tzinfo=IST), recipient_timezone="Asia/Kolkata"
    ).allowed


def test_frequency_caps_consent_and_dnd():
    policy = ContactPolicy.preset("IN_RBI")
    now = datetime(2026, 9, 27, 11, 0, tzinfo=IST)
    calls = [("voice", now - timedelta(days=d)) for d in (1, 2, 3)]
    capped = policy.check("voice", now, recipient_timezone="Asia/Kolkata", history=calls)
    assert not capped.allowed and any("frequency cap" in r for r in capped.reasons)
    assert capped.next_allowed_at == (now - timedelta(days=3) + timedelta(days=7))

    wa = policy.check("whatsapp", now, recipient_timezone="Asia/Kolkata", consent={})
    assert not wa.allowed and wa.next_allowed_at is None  # no consent: never allowed by waiting
    assert policy.check(
        "whatsapp", now, recipient_timezone="Asia/Kolkata", consent={"whatsapp": True}
    ).allowed
    assert not policy.check("sms", now, recipient_timezone="Asia/Kolkata", dnd=True).allowed
    assert policy.check("email", now, recipient_timezone="Asia/Kolkata", dnd=True).allowed


def test_us_reg_f_seven_in_seven_and_conversation_cooloff():
    policy = ContactPolicy.preset("US_REG_F")
    now = datetime(2026, 9, 27, 10, 0, tzinfo=ZoneInfo("America/Chicago"))
    seven = [("voice", now - timedelta(hours=h)) for h in range(1, 8)]
    assert not policy.check(
        "voice", now, recipient_timezone="America/Chicago", history=seven, consent={"voice": True}
    ).allowed
    talked = policy.check(
        "voice",
        now,
        recipient_timezone="America/Chicago",
        consent={"voice": True},
        last_conversation_at=now - timedelta(days=2),
    )
    assert not talked.allowed and "cooling period" in talked.reasons[0]


def test_policy_round_trips_through_dict_with_overrides():
    policy = ContactPolicy.from_dict({"preset": "IN_RBI", "hours": {"*": ["09:00", "18:00"]}})
    assert policy.to_dict()["hours"]["*"] == ["09:00", "18:00"]
    assert ContactPolicy.from_dict(policy.to_dict()).to_dict() == policy.to_dict()


# -- cases ------------------------------------------------------------------------------


def test_case_machine_enforces_transitions():
    DEFAULT_MACHINE.assert_transition("open", "contacted")
    with pytest.raises(TransitionError):
        DEFAULT_MACHINE.assert_transition("resolved", "promised")
    with pytest.raises(TransitionError):
        DEFAULT_MACHINE.assert_transition("closed", "open")


def test_idempotency_keys_are_stable_readable_and_bounded():
    assert (
        idempotency_key("loan 123", "emi:2026-10", "T-3", "sms") == "loan-123|emi:2026-10|T-3|sms"
    )
    long_key = idempotency_key("x" * 500)
    assert len(long_key) <= 200 and long_key == idempotency_key("x" * 500)
    assert idempotency_key("x" * 500) != idempotency_key("x" * 499 + "y")


def test_assignment_is_deterministic_and_proportional():
    assert stable_bucket("loan-1", "exp") == stable_bucket("loan-1", "exp")
    arms = Counter(
        assign_arm(f"loan-{i}", "reminders-v1", {"champion": 80, "control": 20})
        for i in range(5000)
    )
    assert 0.76 < arms["champion"] / 5000 < 0.84


# -- strategies -------------------------------------------------------------------------


def test_strategy_derives_facts_and_chains_tables():
    from nexus.operations import evaluate_strategy

    definition = {
        "facts": {"days_to_due": "days_until(next_due_date)", "dpd": "coalesce(dpd, 0)"},
        "tables": {
            "risk": {
                "rules": [
                    {"id": "BOUNCES", "when": "bounces_6m >= 2", "then": {"risk_band": "high"}}
                ],
                "default": {"risk_band": "low"},
            },
            "treatment": TREATMENT,
        },
        "steps": ["risk", "treatment"],
    }
    loan = {"next_due_date": "2026-09-29", "bounces_6m": 3}
    result = evaluate_strategy(definition, loan, TODAY)
    assert result.facts["days_to_due"] == 2 and result.facts["dpd"] == 0
    assert result.outputs["risk_band"] == "high" and result.outputs["action"] == "call_task"
    assert result.reason_codes == ["risk:BOUNCES", "treatment:HIGH_T3"]
    calm = evaluate_strategy(definition, {"next_due_date": "2026-10-20", "bounces_6m": 0}, TODAY)
    assert calm.outputs["action"] == "none" and calm.reason_codes == [
        "risk:default",
        "treatment:default",
    ]
