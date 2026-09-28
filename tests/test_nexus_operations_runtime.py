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

"""Scorecards, reply intents, messaging, experiments and the case planner."""

import hashlib
import hmac
import math
from datetime import UTC, date, datetime, timedelta

import pytest

from nexus.operations import (
    ContactPolicy,
    DryRunProvider,
    IntentClassifier,
    Message,
    OperationsEngine,
    Scorecard,
    ScorecardError,
    TemplateError,
    WebhookProvider,
    compare,
    evaluate,
    evaluate_strategy,
    mask_recipient,
    plan_case,
    provider_from_config,
    rate,
    redact,
    render_template,
    template_fields,
)

TODAY = date(2026, 10, 8)
NOW = datetime(2026, 10, 8, 6, 30, tzinfo=UTC)  # 12:00 in India

CARD = {
    "name": "early_risk",
    "base_points": 600,
    "base_odds": 50,
    "pdo": 20,
    "bands": [
        {"band": "low", "min_score": 620},
        {"band": "medium", "min_score": 580},
        {"band": "high", "min_score": 0},
    ],
    "outputs": {"score": "risk_score", "probability": "risk_probability", "band": "risk_band"},
    "characteristics": [
        {
            "id": "BOUNCES_6M",
            "field": "bounces_6m",
            "description": "Auto-debit bounces in the last 6 months",
            "bins": [
                {"when": "value == 0", "points": 330},
                {"when": "value == 1", "points": 300},
                {"when": "value >= 2", "points": 270},
            ],
            "missing_points": 300,
        },
        {
            "id": "MANDATE",
            "field": "mandate_status",
            "description": "Auto-debit mandate status",
            "bins": [
                {"when": "value == 'ACTIVE'", "points": 300},
                {"when": "value != 'ACTIVE'", "points": 260},
            ],
            "missing_points": 290,
        },
    ],
}

DEFINITION = {
    "facts": {
        "days_to_due": "days_until(next_due_date)",
        "cycle": "str(next_due_date) if coalesce(dpd, 0) == 0 else str(add_days(today(), 1 - dpd))",
    },
    "scorecards": {"early_risk": CARD},
    "tables": {
        "treatment": {
            "hit_policy": "first",
            "rules": [
                {
                    "id": "RELIEF",
                    "when": "intent == 'hardship'",
                    "then": {
                        "action": "relief_review",
                        "channel": "none",
                        "requires_approval": True,
                    },
                },
                {
                    "id": "OVERDUE",
                    "when": "dpd >= 1",
                    "then": {
                        "action": "overdue_reminder",
                        "channel": "whatsapp",
                        "priority": "=40 + dpd",
                    },
                },
                {
                    "id": "DUE_SOON",
                    "when": "0 <= days_to_due <= 3",
                    "then": {"action": "pre_due_reminder", "channel": "whatsapp", "stage": "T-3"},
                },
            ],
            "default": {"action": "monitor", "channel": "none"},
        }
    },
    "steps": ["early_risk", "treatment"],
    "actions": {
        "pre_due_reminder": {
            "kind": "message",
            "template": "pre_due",
            "fallback_channels": ["sms"],
        },
        "overdue_reminder": {
            "kind": "message",
            "template": "overdue",
            "fallback_channels": ["sms"],
        },
        "relief_review": {"kind": "none"},
    },
    "experiment": {"name": "pd-2026", "arms": {"treatment": 90, "holdout": 10}},
    "reevaluate_hours": 24,
}


# -- expressions additions ---------------------------------------------------------


def test_date_helpers():
    assert evaluate("add_days(today(), -2)", {}, TODAY) == date(2026, 10, 6)
    assert evaluate("str(add_days('2026-10-05', 30))", {}, TODAY) == "2026-11-04"
    assert evaluate("add_days(x, 'a')", {"x": "2026-10-05"}, TODAY) is None


# -- scorecard ---------------------------------------------------------------------


def test_scorecard_scaling_bands_and_reasons():
    card = Scorecard.from_dict(CARD)
    good = card.score({"bounces_6m": 0, "mandate_status": "ACTIVE"})
    bad = card.score({"bounces_6m": 3, "mandate_status": "CANCELLED"})
    assert good.score == 630 and good.band == "low" and good.reasons == []
    assert bad.score == 530 and bad.band == "high"
    assert [r["code"] for r in bad.reasons] == ["BOUNCES_6M", "MANDATE"]  # 60 then 40 points lost
    # 600 points = odds 50:1; every 20 points doubles the odds.
    assert math.isclose(card.probability(600), 1 / 51, rel_tol=1e-9)
    assert math.isclose(card.probability(620), 1 / 101, rel_tol=1e-9)
    missing = card.score({})
    assert missing.contributions["BOUNCES_6M"]["bin"] == "missing"


def test_scorecard_validation():
    with pytest.raises(ScorecardError):
        Scorecard.from_dict({"name": "x", "characteristics": []})
    with pytest.raises(ScorecardError):
        Scorecard.from_dict(
            {**CARD, "bands": [{"band": "a", "min_score": 1}, {"band": "b", "min_score": 5}]}
        )
    bad_bin = {
        **CARD,
        "characteristics": [
            {"id": "X", "field": "x", "bins": [{"when": "__import__('os')", "points": 1}]}
        ],
    }
    with pytest.raises(ScorecardError):
        Scorecard.from_dict(bad_bin)


def test_strategy_runs_scorecard_then_table():
    facts = {"bounces_6m": 1, "mandate_status": "ACTIVE", "dpd": 0, "next_due_date": "2026-10-10"}
    result = evaluate_strategy(DEFINITION, facts, TODAY)
    assert result.outputs["risk_band"] == "medium"
    assert result.outputs["action"] == "pre_due_reminder"
    assert "early_risk:BOUNCES_6M" in result.reason_codes
    assert "treatment:DUE_SOON" in result.reason_codes
    assert result.scores["early_risk"].score == 600


# -- intents -------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "intent"),
    [
        ("Salary late hai is baar, 12 tareekh tak pay kar dunga.", "promise_to_pay"),
        ("Will pay by the 15th, salary got delayed this month.", "promise_to_pay"),
        ("Job chali gayi hai, 4 mahine ka time chahiye EMI ke liye.", "hardship"),
        ("Father is hospitalised, I need an EMI holiday for a few months please.", "hardship"),
        ("नौकरी चली गई, समय चाहिए", "hardship"),
        ("Payment ho gaya hai, UTR 412345678901. Please check.", "already_paid"),
        ("The bounce charge is wrong, I had balance on the due date.", "dispute"),
        ("Mera account band ho gaya, naya mandate kaise banaun?", "mandate_issue"),
        ("Wrong number, I don't have any loan.", "wrong_number"),
        ("STOP", "stop_contact"),
    ],
)
def test_intents(text, intent):
    result = IntentClassifier().classify(text, TODAY)
    assert result.intent == intent
    assert not result.needs_review


def test_intent_entities_and_modifiers():
    c = IntentClassifier()
    promise = c.classify("Kal tak UPI se bhej dunga, please call mat karo.", TODAY)
    assert promise.intent == "promise_to_pay" and not promise.needs_review
    assert promise.entities["promise_date"] == date(2026, 10, 9)
    assert promise.signals.get("stop_contact") and promise.entities["stop_channels"] == ["voice"]
    assert c.classify("Will pay by the 5th", TODAY).entities["promise_date"] == date(2026, 11, 5)
    paid = c.classify("already paid, UTR 412345678901", TODAY)
    assert paid.entities["payment_reference"] == "412345678901"
    mixed = c.classify("Will pay tomorrow but I lost my job", TODAY)
    assert mixed.needs_review


def test_intent_llm_fallback_is_redacted_capped_and_validated():
    seen = []

    def llm(text):
        seen.append(text)
        return {"intent": "callback_request", "confidence": 0.99}

    result = IntentClassifier(llm=llm).classify("hmm 9876543210", TODAY)
    assert seen == ["hmm [phone]"]
    assert result.method == "llm" and result.confidence == 0.85
    broken = IntentClassifier(llm=lambda _t: {"intent": "rm -rf"}).classify("hmm", TODAY)
    assert broken.method == "rules" and broken.needs_review
    failing = IntentClassifier(llm=lambda _t: 1 / 0).classify("hmm", TODAY)
    assert failing.intent == "other"


def test_redact():
    text = redact("PAN ABCDE1234F, mail a.b@x.in, phone +91 9876543210, a/c 50100123456789")
    assert "ABCDE1234F" not in text and "a.b@x.in" not in text
    assert "9876543210" not in text and "50100123456789" not in text


# -- messaging ----------------------------------------------------------------------------


def test_templates_are_placeholder_only():
    assert render_template("Hi {name}, EMI {emi} due {{soon}}", {"name": "Asha", "emi": 1}) == (
        "Hi Asha, EMI 1 due {soon}"
    )
    assert template_fields("{a} and {b}") == {"a", "b"}
    for bad in ("{a.__class__}", "{a[0]}", "{a!r}", "{a:>10}", "{"):
        with pytest.raises(TemplateError):
            template_fields(bad)
    assert render_template("{missing}!", {}) == "!"


def test_mask_recipient():
    assert mask_recipient("+91 9876543210") == "+91********10"
    assert mask_recipient("asha@example.in") == "a***@example.in"


def test_webhook_provider_signature_and_https():
    with pytest.raises(ValueError):
        WebhookProvider("http://gateway.bank.example/sms", "x" * 32)
    with pytest.raises(ValueError):
        WebhookProvider("https://gateway.bank.example/sms", "short")
    provider = WebhookProvider("https://gateway.bank.example/sms", "s" * 32)
    body, ts = b'{"a":1}', 1_700_000_000
    expected = hmac.new(b"s" * 32, b"1700000000." + body, hashlib.sha256).hexdigest()
    assert provider.sign(body, ts) == f"t={ts},v1={expected}"
    assert isinstance(provider_from_config({"provider": "dry_run"}), DryRunProvider)
    with pytest.raises(ValueError):
        provider_from_config({"provider": "carrier-pigeon"})


# -- experiments ---------------------------------------------------------------------------


def test_rate_and_compare():
    r = rate(0, 10)
    assert r.rate == 0 and r.low == 0 and 0.2 < r.high < 0.35  # Wilson, not a degenerate interval
    strong = compare((900, 1000), (800, 1000))
    assert strong.conclusive and strong.lift == pytest.approx(0.1) and strong.p_value < 0.001
    small = compare((9, 10), (8, 10))
    assert not small.conclusive and "needs at least" in small.note
    assert compare((0, 0), (1, 5)).lift is None


# -- planner & engine -----------------------------------------------------------------------


def _facts(**overrides):
    base = {"bounces_6m": 0, "mandate_status": "ACTIVE", "dpd": 0, "next_due_date": "2026-10-10"}
    return {**base, **overrides}


def _treated_subject():
    return next(
        f"LA{i}"
        for i in range(100)
        if plan_case(DEFINITION, _facts(), subject_ref=f"LA{i}", now=NOW).arm == "treatment"
    )


def test_plan_pre_due_with_channel_fallback_and_stable_key():
    policy = ContactPolicy.preset("IN_RBI")
    ref = _treated_subject()
    plan = plan_case(
        DEFINITION, _facts(), subject_ref=ref, now=NOW, policy=policy, consent={"whatsapp": False}
    )
    action = plan.actions[0]
    assert action.channel == "sms" and action.sendable  # no WhatsApp consent -> SMS
    assert action.idempotency_key == f"{ref}|2026-10-10|T-3"
    assert plan.state == "contacted"
    again = plan_case(
        DEFINITION,
        _facts(),
        subject_ref=ref,
        now=NOW + timedelta(hours=5),
        policy=policy,
        consent={"whatsapp": True},
    )
    assert again.actions[0].idempotency_key == action.idempotency_key  # same cycle, same key


def test_plan_respects_hours_opt_out_pause_and_holdout():
    policy = ContactPolicy.preset("IN_RBI")
    ref = _treated_subject()
    night = datetime(2026, 10, 8, 16, 0, tzinfo=UTC)  # 21:30 in India
    deferred = plan_case(
        DEFINITION, _facts(), subject_ref=ref, now=night, policy=policy, consent={"whatsapp": True}
    ).actions[0]
    assert deferred.sendable and deferred.not_before == datetime(2026, 10, 9, 2, 30, tzinfo=UTC)
    opted = plan_case(
        DEFINITION,
        _facts(),
        subject_ref=ref,
        now=NOW,
        policy=policy,
        consent={"whatsapp": True},
        opted_out=["all"],
    )
    assert not opted.actions[0].sendable and opted.state == "monitoring"
    paused = plan_case(
        DEFINITION, _facts(), subject_ref=ref, now=NOW, paused_until=NOW + timedelta(days=2)
    )
    assert "paused" in paused.actions[0].blocked[0]
    holdout = plan_case(DEFINITION, _facts(), subject_ref=ref, now=NOW, arm="holdout")
    assert "control arm" in holdout.actions[0].blocked[0]
    assert holdout.reason_codes  # still decided and recorded


def test_plan_overdue_cycle_and_approval():
    ref = _treated_subject()
    overdue = plan_case(
        DEFINITION, _facts(dpd=4, next_due_date="2026-11-05"), subject_ref=ref, now=NOW
    )
    assert overdue.actions[0].idempotency_key == f"{ref}|2026-10-05|overdue_reminder"
    assert overdue.priority == 44
    relief = plan_case(
        DEFINITION, _facts(intent="hardship"), subject_ref=ref, now=NOW, state="contacted"
    )
    assert relief.approval and relief.state == "awaiting_approval" and not relief.actions


def test_engine_end_to_end_is_idempotent():
    provider = DryRunProvider()
    engine = OperationsEngine(
        DEFINITION, ContactPolicy.preset("IN_RBI"), {"whatsapp": provider, "sms": provider}
    )
    refs = [f"LA{i}" for i in range(40)]
    for ref in refs:
        engine.upsert(ref, _facts(consent={"whatsapp": True}), NOW)
    plans = engine.evaluate_due(NOW)
    assert len(plans) == 40

    def render(ref, action, facts):
        return Message(channel=action.channel, to="+91 9000000000", body=f"{ref} {action.template}")

    first = engine.dispatch(NOW, render)
    assert first and all(r.ok for r in first)
    treated = sum(1 for p in plans if p.arm == "treatment")
    assert len(provider.sent) == treated
    engine.evaluate_due(NOW + timedelta(days=1))  # re-evaluated, same cycle -> same keys
    assert engine.dispatch(NOW + timedelta(days=1), render) == []


def test_tasks_respect_opt_outs():
    definition = {
        "tables": {
            "t": {
                "rules": [
                    {"id": "CALL", "when": "1 == 1", "then": {"action": "call", "channel": "voice"}}
                ]
            }
        },
        "steps": ["t"],
    }
    blocked = plan_case(definition, {}, subject_ref="L1", now=NOW, opted_out=["voice"])
    assert blocked.actions[0].blocked and blocked.state == "monitoring"
    allowed = plan_case(definition, {}, subject_ref="L1", now=NOW)
    assert allowed.actions[0].sendable and allowed.state == "escalated"


WORK_DEFINITION = {
    "tables": {
        "t": {
            "rules": [
                {
                    "id": "CRITICAL",
                    "when": "risk >= 0.8",
                    "then": {
                        "action": "work_order",
                        "channel": "work_order",
                        "requires_approval": True,
                        "approval_type": "work_order",
                        "title": "Pump P-101: bearing wear",
                        "work_priority": 2,
                        "cycle": "=incident",
                    },
                },
                {
                    "id": "WATCH",
                    "when": "risk >= 0.5",
                    "then": {"action": "notify", "channel": "teams", "cycle": "=incident"},
                },
            ],
            "default": {"action": "observe", "channel": "none"},
        }
    },
    "steps": ["t"],
    "actions": {"work_order": {"kind": "work_order"}, "notify": {"kind": "work_order"}},
}


def test_work_orders_wait_for_approval_and_are_raised_once():
    from nexus.operations import DryRunWorkProvider

    critical = plan_case(
        WORK_DEFINITION, {"risk": 0.9, "incident": "E1"}, subject_ref="P-101", now=NOW
    )
    held = critical.actions[0]
    assert critical.state == "awaiting_approval" and held.needs_approval and not held.ready
    assert held.kind == "work_order" and held.idempotency_key == "P-101|E1|work_order"
    assert critical.approval["requested_action"]["idempotency_key"] == held.idempotency_key
    watch = plan_case(
        WORK_DEFINITION, {"risk": 0.6, "incident": "E1"}, subject_ref="P-102", now=NOW
    )
    assert watch.actions[0].ready and watch.state == "escalated" and not watch.approval

    tickets = DryRunWorkProvider()
    engine = OperationsEngine(WORK_DEFINITION, work_providers={"work_order": tickets})
    engine.upsert("P-101", {"risk": 0.9, "incident": "E1"}, NOW)
    engine.evaluate_due(NOW)
    assert engine.dispatch(NOW, lambda *a: None) == [] and not tickets.items  # held for approval
    assert [a.action_type for a in engine.approve("P-101")] == ["work_order"]
    results = engine.dispatch(NOW, lambda *a: None)
    assert results[0].ok and tickets.items[0].title == "Pump P-101: bearing wear"
    assert tickets.items[0].priority == 2 and tickets.items[0].asset_ref == "P-101"
    engine.approve("P-101")
    # same incident: raised once
    assert engine.dispatch(NOW, lambda *a: None) == [] and len(tickets.items) == 1


LABELLED = [
    ("abhi paisa nahi hai, agle mahine dekhta hoon", "hardship"),
    ("paisa nahi hai abhi, thoda ruk jao", "hardship"),
    ("haath tang hai is mahine, ruk jaiye", "hardship"),
    ("ghar mein shaadi thi, paisa khatam ho gaya", "hardship"),
    ("dukaan mein nuksan hua, abhi mushkil hai", "hardship"),
    ("mushkil chal raha hai, kuch waqt dijiye", "hardship"),
    ("salary aate hi bhar dunga", "promise_to_pay"),
    ("somvar ko pakka jama karunga", "promise_to_pay"),
    ("shaam tak transfer ho jayega", "promise_to_pay"),
    ("hafte ke end tak clear kar dunga", "promise_to_pay"),
    ("pakka bhar dunga is hafte", "promise_to_pay"),
    ("jama karunga shaam tak pakka", "promise_to_pay"),
    ("bhar diya kal hi, check karo", "already_paid"),
    ("paise kat gaye account se, check karo", "already_paid"),
    ("kal jama kar diya tha branch mein", "already_paid"),
    ("gpay se bhej diya tha kal", "already_paid"),
    ("mera number nahi hai ye", "wrong_number"),
    ("ye kiska loan hai, main nahi jaanta", "wrong_number"),
    ("aap galat insaan ko message kar rahe ho", "wrong_number"),
    ("main is naam ke kisi ko nahi jaanta", "wrong_number"),
]


def test_intent_model_learns_phrasing_the_rules_miss():
    from nexus.operations import IntentModel, evaluate_model

    model = IntentModel.fit(LABELLED)
    assert model.trained
    assert model.predict("abhi paisa nahi hai bhai")[0] == "hardship"
    assert model.predict("somvar tak pakka bhar dunga")[0] == "promise_to_pay"
    assert IntentModel.from_dict(model.to_dict()).probabilities(
        "gpay se bhej diya"
    ) == model.probabilities("gpay se bhej diya")
    report = evaluate_model(LABELLED)
    assert report["examples"] == 20 and report["accuracy"] is not None
    assert evaluate_model(LABELLED[:3])["accuracy"] is None  # too few labels to judge


def test_classifier_uses_the_model_only_when_rules_are_unsure():
    from nexus.operations import IntentModel

    model = IntentModel.fit(LABELLED)
    plain = IntentClassifier().classify("abhi paisa nahi hai, agle mahine dekhta hoon", TODAY)
    assert plain.needs_review
    learned = IntentClassifier(model=model, model_min_confidence=0.5).classify(
        "abhi paisa nahi hai, agle mahine dekhta hoon", TODAY
    )
    assert learned.method == "model" and learned.intent == "hardship" and learned.confidence <= 0.85
    confident = IntentClassifier(model=model).classify(
        "Wrong number, I don't have any loan.", TODAY
    )
    assert confident.method == "rules" and confident.intent == "wrong_number"
    untrained = IntentClassifier(model=IntentModel.fit(LABELLED[:3]))
    assert untrained.model is None
