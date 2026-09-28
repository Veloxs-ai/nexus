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

"""Case planning: from facts to a decision, a next state and safe actions.

``plan_case`` is the heart of an evaluation run and is a pure function: given a
strategy definition, the subject's facts and its contact context, it returns a
``CasePlan`` — outputs, reason codes, scores, the next state, the actions to queue
(each with a permanent idempotency key and the earliest time contact rules allow) and
an approval request when a person must decide. Persisting the plan (and sending) is
the caller's job, so the same planner runs inside a platform with a database-backed
outbox or in a few lines of Python with ``OperationsEngine`` and an in-memory store.

Action kinds come from the strategy's ``actions`` map (or are inferred from the
channel): ``message`` (queued to a channel provider, with channel fallback when
consent or do-not-disturb blocks the first choice), ``task`` (work for a person, e.g.
a call), ``work_order`` (a ticket or notification in a maintenance / ITSM system, see
``nexus.operations.workorders``), ``handoff`` (leaves this strategy, e.g. to collections)
and ``none``. When a rule requires approval, its action is planned but marked
``needs_approval``: it is queued only after a person approves. Subjects
in the experiment's control arm are evaluated and recorded exactly like everyone else
but receive no actions — that is what makes the holdout comparison fair.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from typing import Any

from .cases import DEFAULT_MACHINE, CaseMachine, assign_arm, idempotency_key
from .contact_policy import ContactPolicy
from .messaging import ChannelProvider, Message, SendResult
from .strategy import evaluate_strategy

ACTION_KINDS = ("message", "task", "work_order", "handoff", "none")
DEFAULT_STATES = {
    "message": "contacted",
    "task": "escalated",
    "work_order": "escalated",
    "handoff": "escalated",
    "none": "monitoring",
}


@dataclass
class PlannedAction:
    action_type: str
    kind: str
    channel: str
    idempotency_key: str
    template: str | None = None
    not_before: datetime | None = None
    blocked: list[str] = field(default_factory=list)
    policy: dict[str, Any] = field(default_factory=dict)
    needs_approval: bool = False

    @property
    def sendable(self) -> bool:
        return not self.blocked

    @property
    def ready(self) -> bool:
        """Can be queued now: not blocked and not waiting for a person's approval."""
        return not self.blocked and not self.needs_approval

    def as_dict(self) -> dict[str, Any]:
        return {
            "action_type": self.action_type,
            "kind": self.kind,
            "channel": self.channel,
            "idempotency_key": self.idempotency_key,
            "template": self.template,
            "not_before": self.not_before.isoformat() if self.not_before else None,
            "blocked": self.blocked,
            "policy": self.policy,
            "needs_approval": self.needs_approval,
        }


@dataclass
class CasePlan:
    state: str
    priority: int
    outputs: dict[str, Any]
    reason_codes: list[str]
    scores: dict[str, Any]
    derived: dict[str, Any]
    actions: list[PlannedAction]
    approval: dict[str, Any] | None
    next_eval_at: datetime
    arm: str | None
    notes: list[str] = field(default_factory=list)
    trace: dict[str, Any] = field(default_factory=dict)

    @property
    def risk_band(self) -> str | None:
        band = self.outputs.get("risk_band")
        return None if band is None else str(band)

    def as_dict(self) -> dict[str, Any]:
        return {
            "state": self.state,
            "priority": self.priority,
            "outputs": self.outputs,
            "reason_codes": self.reason_codes,
            "scores": self.scores,
            "derived": self.derived,
            "actions": [a.as_dict() for a in self.actions],
            "approval": self.approval,
            "next_eval_at": self.next_eval_at.isoformat(),
            "arm": self.arm,
            "notes": self.notes,
        }


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def _int(value: Any, default: int = 0) -> int:
    try:
        return round(float(value))
    except (TypeError, ValueError):
        return default


def experiment_arm(definition: dict[str, Any], subject_ref: str) -> str | None:
    experiment = definition.get("experiment") or {}
    arms = experiment.get("arms") or {}
    if not arms:
        return None
    return assign_arm(subject_ref, str(experiment.get("name") or "default"), dict(arms))


def control_arm(definition: dict[str, Any]) -> str | None:
    experiment = definition.get("experiment") or {}
    return str(experiment.get("control") or "holdout") if experiment.get("arms") else None


def action_spec(definition: dict[str, Any], action: str, channel: str) -> dict[str, Any]:
    spec = dict((definition.get("actions") or {}).get(action) or {})
    if "kind" not in spec:
        spec["kind"] = (
            "none"
            if channel in ("", "none", None)
            else "task"
            if channel in ("voice", "visit")
            else "message"
        )
    if spec["kind"] not in ACTION_KINDS:
        raise ValueError(f"action '{action}' has unknown kind '{spec['kind']}'")
    return spec


def plan_case(
    definition: dict[str, Any],
    facts: dict[str, Any],
    *,
    subject_ref: str,
    now: datetime,
    today: date | None = None,
    state: str | None = None,
    arm: str | None = None,
    machine: CaseMachine | None = None,
    policy: ContactPolicy | None = None,
    contact_history: Iterable[tuple[str, datetime]] = (),
    consent: dict[str, bool] | None = None,
    dnd: dict[str, bool] | bool = False,
    recipient_timezone: str | None = None,
    opted_out: Iterable[str] = (),
    paused_until: datetime | None = None,
    last_conversation_at: datetime | None = None,
) -> CasePlan:
    """Evaluate one subject and plan what should happen next (no side effects)."""
    now = _aware(now)
    machine = machine or (
        CaseMachine.from_dict(definition["case_machine"])
        if definition.get("case_machine")
        else DEFAULT_MACHINE
    )
    current = state or machine.initial
    today = today or now.date()
    arm = arm if arm is not None else experiment_arm(definition, subject_ref)

    result = evaluate_strategy(definition, facts, today)
    outputs = result.outputs
    notes: list[str] = []
    action_name = str(outputs.get("action") or "monitor")
    channel = str(outputs.get("channel") or "none")
    spec = action_spec(definition, action_name, channel)
    kind = spec["kind"]
    priority = _int(outputs.get("priority"), 0)
    derived = {name: result.facts.get(name) for name in (definition.get("facts") or {})} | {
        k: v for k, v in outputs.items() if not isinstance(v, dict | list)
    }

    cycle = outputs.get("cycle") or result.facts.get("cycle") or today.isoformat()
    stage = str(outputs.get("stage") or action_name)
    actions: list[PlannedAction] = []
    approval: dict[str, Any] | None = None
    holdout = arm is not None and arm == control_arm(definition)

    if kind in ("message", "task", "work_order"):
        planned = PlannedAction(
            action_type=action_name,
            kind=kind,
            channel=channel,
            idempotency_key=idempotency_key(subject_ref, cycle, stage),
            template=spec.get("template") or action_name,
        )
        if holdout:
            planned.blocked.append(f"control arm '{arm}': evaluated but not contacted")
        elif paused_until is not None and now < _aware(paused_until):
            planned.blocked.append(f"contact paused until {_aware(paused_until).isoformat()}")
        elif kind == "task" and ("all" in set(opted_out) or channel in set(opted_out)):
            planned.blocked.append(f"{channel}: customer asked not to be contacted on this channel")
        elif kind == "message":
            _choose_channel(
                planned,
                [channel, *spec.get("fallback_channels", [])],
                policy,
                now,
                contact_history,
                consent,
                dnd,
                recipient_timezone,
                set(opted_out),
                last_conversation_at,
            )
        actions.append(planned)
    if outputs.get("requires_approval") and not holdout:
        approval = {
            "approval_type": str(outputs.get("approval_type") or action_name),
            "summary": str(outputs.get("approval_summary") or outputs.get("reason") or action_name),
            "requested_action": {"action": action_name, "channel": channel, "outputs": outputs},
        }
        for planned in actions:
            planned.needs_approval = True
        if actions:
            approval["requested_action"]["idempotency_key"] = actions[0].idempotency_key

    target = str(outputs.get("state") or "")
    if not target:
        if approval:
            target = "awaiting_approval"
        elif actions and actions[0].ready:
            target = DEFAULT_STATES[kind]
        elif kind == "handoff":
            target = DEFAULT_STATES["handoff"]
        elif current in ("open", "monitoring"):
            target = "monitoring"
        else:
            target = current
    if not machine.can(current, target) or machine.is_terminal(current):
        notes.append(f"state stays '{current}' (move to '{target}' not allowed)")
        target = current

    hours = outputs.get("next_eval_hours") or definition.get("reevaluate_hours") or 24
    next_eval = now + timedelta(hours=max(0.25, float(hours)))
    return CasePlan(
        state=target,
        priority=priority,
        outputs=outputs,
        reason_codes=result.reason_codes,
        scores={name: s.as_dict() for name, s in result.scores.items()},
        derived=derived,
        actions=actions,
        approval=approval,
        next_eval_at=next_eval,
        arm=arm,
        notes=notes,
        trace=result.as_dict(),
    )


def _choose_channel(
    planned: PlannedAction,
    candidates: list[str],
    policy: ContactPolicy | None,
    now: datetime,
    history: Iterable[tuple[str, datetime]],
    consent: dict[str, bool] | None,
    dnd: dict[str, bool] | bool,
    timezone: str | None,
    opted_out: set[str],
    last_conversation_at: datetime | None,
) -> None:
    history = list(history)
    reasons: list[str] = []
    for candidate in dict.fromkeys(c for c in candidates if c and c != "none"):
        if "all" in opted_out or candidate in opted_out:
            reasons.append(f"{candidate}: customer asked not to be contacted on this channel")
            continue
        if policy is None:
            planned.channel = candidate
            return
        blocked_dnd = dnd.get(candidate, False) if isinstance(dnd, dict) else bool(dnd)
        decision = policy.check(
            candidate,
            now,
            recipient_timezone=timezone,
            history=history,
            consent=consent,
            dnd=blocked_dnd,
            last_conversation_at=last_conversation_at,
        )
        if decision.allowed or decision.next_allowed_at is not None:
            planned.channel = candidate
            planned.not_before = decision.next_allowed_at
            planned.policy = decision.as_dict()
            return
        reasons.extend(f"{candidate}: {r}" for r in decision.reasons)
    planned.blocked.extend(reasons or ["no usable channel"])


# ---------------------------------------------------------------------------
# A complete engine for standalone use (in memory)
# ---------------------------------------------------------------------------


@dataclass
class _Case:
    subject_ref: str
    facts: dict[str, Any]
    state: str
    next_eval_at: datetime
    arm: str | None
    plan: CasePlan | None = None


class OperationsEngine:
    """Minimal in-memory runtime: upsert subjects, evaluate due cases, dispatch messages.

    Suitable for tests, notebooks and small deployments; platforms keep the same flow
    with a database store (cases, outbox with a unique idempotency key, contact ledger).
    """

    def __init__(
        self,
        definition: dict[str, Any],
        policy: ContactPolicy | None = None,
        providers: dict[str, ChannelProvider] | None = None,
        work_providers: dict[str, Any] | None = None,
    ) -> None:
        self.definition = definition
        self.policy = policy
        self.providers = providers or {}
        self.work_providers = work_providers or {}  # channel -> WorkProvider (workorders module)
        self.cases: dict[str, _Case] = {}
        self.outbox: dict[str, dict[str, Any]] = {}
        self.ledger: list[tuple[str, str, datetime]] = []

    def upsert(self, subject_ref: str, facts: dict[str, Any], now: datetime) -> None:
        now = _aware(now)
        case = self.cases.get(subject_ref)
        if case is None:
            self.cases[subject_ref] = _Case(
                subject_ref,
                dict(facts),
                DEFAULT_MACHINE.initial,
                now,
                experiment_arm(self.definition, subject_ref),
            )
        elif case.facts != facts:
            case.facts, case.next_eval_at = dict(facts), now  # changed data: evaluate now

    def evaluate_due(self, now: datetime) -> list[CasePlan]:
        now = _aware(now)
        plans = []
        for case in self.cases.values():
            if case.next_eval_at > now:
                continue
            history = [(ch, at) for ref, ch, at in self.ledger if ref == case.subject_ref]
            plan = plan_case(
                self.definition,
                case.facts,
                subject_ref=case.subject_ref,
                now=now,
                state=case.state,
                arm=case.arm,
                policy=self.policy,
                contact_history=history,
                consent=case.facts.get("consent"),
                dnd=case.facts.get("dnd", False),
            )
            case.state, case.next_eval_at, case.plan = plan.state, plan.next_eval_at, plan
            for action in plan.actions:
                if action.ready and action.kind in ("message", "work_order"):
                    self.outbox.setdefault(
                        action.idempotency_key,
                        {"subject_ref": case.subject_ref, "action": action, "status": "pending"},
                    )
            plans.append(plan)
        return plans

    def dispatch(
        self, now: datetime, render: Callable[[str, PlannedAction, dict[str, Any]], Message]
    ) -> list[SendResult]:
        now = _aware(now)
        results = []
        for item in self.outbox.values():
            action: PlannedAction = item["action"]
            if item["status"] != "pending" or (action.not_before and action.not_before > now):
                continue
            if action.kind == "work_order":
                results.append(self._submit_work(item, action))
                continue
            provider = self.providers.get(action.channel)
            if provider is None:
                continue
            message = render(item["subject_ref"], action, self.cases[item["subject_ref"]].facts)
            message.idempotency_key = message.idempotency_key or action.idempotency_key
            sent = provider.send(message)
            item["status"] = "sent" if sent.ok else ("pending" if sent.retryable else "failed")
            if sent.ok:
                self.ledger.append((item["subject_ref"], action.channel, now))
            results.append(sent)
        return results

    def _submit_work(self, item: dict[str, Any], action: PlannedAction) -> Any:
        from .workorders import DryRunWorkProvider, WorkItem

        provider = self.work_providers.get(action.channel) or self.work_providers.setdefault(
            action.channel, DryRunWorkProvider()
        )
        case = self.cases[item["subject_ref"]]
        outputs = case.plan.outputs if case.plan else {}
        work = WorkItem(
            title=str(outputs.get("title") or f"{action.action_type}: {item['subject_ref']}"),
            description=str(
                outputs.get("description") or outputs.get("reason") or action.action_type
            ),
            idempotency_key=action.idempotency_key,
            asset_ref=item["subject_ref"],
            priority=_int(outputs.get("work_priority"), 3),
        )
        result = provider.submit(work)
        item["status"] = "sent" if result.ok else ("pending" if result.retryable else "failed")
        item["result"] = result.as_dict()
        return result

    def approve(self, subject_ref: str) -> list[PlannedAction]:
        """A person approved the pending decision of this case: queue its held actions."""
        case = self.cases[subject_ref]
        released = []
        for action in case.plan.actions if case.plan else []:
            if action.needs_approval and action.sendable:
                action.needs_approval = False
                self.outbox.setdefault(
                    action.idempotency_key,
                    {"subject_ref": subject_ref, "action": action, "status": "pending"},
                )
                released.append(action)
        if released:
            case.state = DEFAULT_STATES[released[0].kind]
        return released
