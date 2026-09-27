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

"""Contact policy: may we contact this person, on this channel, right now?

Checked before every outbound message or call, in the recipient's local time:

  * allowed hours per channel (e.g. 08:00–19:00)
  * frequency caps per channel over a rolling window (e.g. 7 calls in 7 days)
  * consent per channel and do-not-disturb
  * a cooling period after a completed conversation, if configured

Rules are data so they can differ per jurisdiction and per client. Presets encode
common regimes; they are starting points and must be confirmed by the client's
compliance team:

  * ``IN_RBI`` — India: recovery contact 08:00–19:00 (RBI conduct directions)
  * ``US_REG_F`` — United States: 08:00–21:00 recipient-local (FDCPA), at most 7 call
    attempts in 7 days and no call within 7 days after a conversation (Regulation F
    presumption), consent required for automated calls and texts (TCPA)

``check`` returns whether contact is allowed now, every reason it is not, and the
earliest time it would be allowed, so the caller can schedule instead of dropping.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import UTC, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

CHANNELS = ("sms", "whatsapp", "email", "voice", "visit")


@dataclass(frozen=True)
class FrequencyCap:
    channel: str  # a channel name, or "*" for all channels combined
    max_contacts: int
    period_days: int


@dataclass
class ContactPolicy:
    name: str = "custom"
    hours: dict[str, tuple[time, time]] = field(default_factory=dict)  # channel or "*" -> window
    caps: list[FrequencyCap] = field(default_factory=list)
    require_consent: tuple[str, ...] = ()
    respect_dnd: tuple[str, ...] = ("sms", "voice", "whatsapp")
    conversation_cooloff_days: dict[str, int] = field(default_factory=dict)
    default_timezone: str = "UTC"

    # -- presets --------------------------------------------------------------
    @classmethod
    def preset(cls, name: str) -> ContactPolicy:
        key = name.upper()
        if key == "IN_RBI":
            window = (time(8, 0), time(19, 0))
            return cls(
                name="IN_RBI",
                hours={"*": window},
                caps=[
                    FrequencyCap("voice", 3, 7),
                    FrequencyCap("sms", 2, 1),
                    FrequencyCap("whatsapp", 2, 1),
                    FrequencyCap("*", 6, 7),
                ],
                require_consent=("whatsapp",),
                respect_dnd=("sms", "voice"),
                default_timezone="Asia/Kolkata",
            )
        if key == "US_REG_F":
            return cls(
                name="US_REG_F",
                hours={"*": (time(8, 0), time(21, 0))},
                caps=[FrequencyCap("voice", 7, 7)],
                require_consent=("sms", "voice"),
                respect_dnd=("sms", "voice"),
                conversation_cooloff_days={"voice": 7},
                default_timezone="America/New_York",
            )
        raise ValueError(f"unknown contact policy preset '{name}' (use IN_RBI or US_REG_F)")

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ContactPolicy:
        if data.get("preset"):
            base = cls.preset(str(data["preset"]))
        else:
            base = cls(name=str(data.get("name") or "custom"))
        if "hours" in data:
            base.hours = {
                ch: (time.fromisoformat(w[0]), time.fromisoformat(w[1]))
                for ch, w in data["hours"].items()
            }
        if "caps" in data:
            base.caps = [
                FrequencyCap(str(c["channel"]), int(c["max_contacts"]), int(c["period_days"]))
                for c in data["caps"]
            ]
        for key in ("require_consent", "respect_dnd"):
            if key in data:
                setattr(base, key, tuple(data[key]))
        if "conversation_cooloff_days" in data:
            base.conversation_cooloff_days = {
                k: int(v) for k, v in data["conversation_cooloff_days"].items()
            }
        if data.get("default_timezone"):
            base.default_timezone = str(data["default_timezone"])
        return base

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "hours": {
                ch: [w[0].isoformat("minutes"), w[1].isoformat("minutes")]
                for ch, w in self.hours.items()
            },
            "caps": [
                {"channel": c.channel, "max_contacts": c.max_contacts, "period_days": c.period_days}
                for c in self.caps
            ],
            "require_consent": list(self.require_consent),
            "respect_dnd": list(self.respect_dnd),
            "conversation_cooloff_days": self.conversation_cooloff_days,
            "default_timezone": self.default_timezone,
        }

    # -- evaluation -------------------------------------------------------------
    def _zone(self, tz: str | None) -> ZoneInfo:
        try:
            return ZoneInfo(tz or self.default_timezone)
        except ZoneInfoNotFoundError:
            return ZoneInfo(self.default_timezone)

    def check(
        self,
        channel: str,
        now: datetime,
        *,
        recipient_timezone: str | None = None,
        history: Iterable[tuple[str, datetime]] = (),
        consent: dict[str, bool] | None = None,
        dnd: bool = False,
        last_conversation_at: datetime | None = None,
    ) -> ContactDecision:
        """Decide whether ``channel`` may be used at ``now`` (timezone-aware).

        ``history`` is (channel, contacted_at) for prior contacts with this person.
        """
        if now.tzinfo is None:
            now = now.replace(tzinfo=UTC)
        reasons: list[str] = []
        not_before: list[datetime] = []
        zone = self._zone(recipient_timezone)
        local = now.astimezone(zone)

        window = self.hours.get(channel) or self.hours.get("*")
        if window:
            start, end = window
            if not (start <= local.time() < end):
                reasons.append(f"outside contact hours {start:%H:%M}-{end:%H:%M} ({zone.key})")
                next_day = local.date() + timedelta(days=0 if local.time() < start else 1)
                not_before.append(datetime.combine(next_day, start, tzinfo=zone).astimezone(UTC))

        if channel in self.require_consent and not (consent or {}).get(channel, False):
            reasons.append(f"no recorded consent for {channel}")
        if dnd and channel in self.respect_dnd:
            reasons.append(f"recipient is on do-not-disturb for {channel}")

        past = sorted((c, t if t.tzinfo else t.replace(tzinfo=UTC)) for c, t in history)
        for cap in self.caps:
            since = now - timedelta(days=cap.period_days)
            relevant = sorted(
                t for c, t in past if (cap.channel == "*" or c == cap.channel) and t > since
            )
            applies = cap.channel == "*" or cap.channel == channel
            if applies and len(relevant) >= cap.max_contacts:
                scope = "all channels" if cap.channel == "*" else cap.channel
                reasons.append(
                    f"frequency cap reached: {cap.max_contacts} {scope} contact(s) "
                    f"per {cap.period_days} day(s)"
                )
                oldest_counted = relevant[len(relevant) - cap.max_contacts]
                not_before.append(oldest_counted + timedelta(days=cap.period_days))

        cooloff = self.conversation_cooloff_days.get(channel)
        if cooloff and last_conversation_at is not None:
            last = (
                last_conversation_at
                if last_conversation_at.tzinfo
                else last_conversation_at.replace(tzinfo=UTC)
            )
            if now < last + timedelta(days=cooloff):
                reasons.append(f"within {cooloff}-day cooling period after a conversation")
                not_before.append(last + timedelta(days=cooloff))

        blocking_forever = any(
            r.startswith(("no recorded consent", "recipient is on do-not-disturb")) for r in reasons
        )
        return ContactDecision(
            allowed=not reasons,
            reasons=reasons,
            next_allowed_at=None
            if (not reasons or blocking_forever)
            else max(not_before)
            if not_before
            else None,
            policy=self.name,
        )


@dataclass(frozen=True)
class ContactDecision:
    allowed: bool
    reasons: list[str]
    next_allowed_at: datetime | None
    policy: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "allowed": self.allowed,
            "reasons": self.reasons,
            "policy": self.policy,
            "next_allowed_at": self.next_allowed_at.isoformat() if self.next_allowed_at else None,
        }
