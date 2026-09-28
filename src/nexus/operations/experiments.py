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

"""Measuring a strategy against a holdout, honestly.

A treatment is only worth what it adds over doing nothing, so every strategy keeps a
randomized holdout (``cases.assign_arm``) and results compare rates between arms:

  * ``rate`` — successes / trials with a Wilson score interval (well-behaved for small
    samples and rates near 0 or 1, unlike the normal approximation)
  * ``compare`` — absolute and relative lift of a treatment over the control, a
    two-sided two-proportion z-test p-value, and a confidence interval for the
    difference; results are flagged ``conclusive`` only with enough trials per arm and
    p below the chosen alpha

Pure Python (no SciPy), deterministic, and cheap enough to run on every dashboard load.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

MIN_TRIALS_PER_ARM = 30


def _z(confidence: float) -> float:
    return {0.90: 1.6449, 0.95: 1.9600, 0.99: 2.5758}.get(round(confidence, 2), 1.9600)


def _normal_sf(x: float) -> float:
    """P(Z > x) for a standard normal."""
    return 0.5 * math.erfc(x / math.sqrt(2))


@dataclass(frozen=True)
class RateEstimate:
    successes: int
    trials: int
    rate: float | None
    low: float | None
    high: float | None

    def as_dict(self) -> dict[str, Any]:
        return {
            "successes": self.successes,
            "trials": self.trials,
            "rate": self.rate,
            "low": self.low,
            "high": self.high,
        }


def rate(successes: int, trials: int, confidence: float = 0.95) -> RateEstimate:
    """Proportion with a Wilson score interval."""
    if trials <= 0:
        return RateEstimate(successes, trials, None, None, None)
    successes = max(0, min(successes, trials))
    z = _z(confidence)
    p = successes / trials
    denom = 1 + z * z / trials
    centre = (p + z * z / (2 * trials)) / denom
    half = z * math.sqrt(p * (1 - p) / trials + z * z / (4 * trials * trials)) / denom
    return RateEstimate(
        successes,
        trials,
        round(p, 6),
        round(max(0.0, centre - half), 6),
        round(min(1.0, centre + half), 6),
    )


@dataclass(frozen=True)
class Comparison:
    treatment: RateEstimate
    control: RateEstimate
    lift: float | None  # absolute difference in rate
    relative_lift: float | None
    p_value: float | None
    diff_low: float | None
    diff_high: float | None
    conclusive: bool
    note: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "treatment": self.treatment.as_dict(),
            "control": self.control.as_dict(),
            "lift": self.lift,
            "relative_lift": self.relative_lift,
            "p_value": self.p_value,
            "diff_low": self.diff_low,
            "diff_high": self.diff_high,
            "conclusive": self.conclusive,
            "note": self.note,
        }


def compare(
    treatment: tuple[int, int],
    control: tuple[int, int],
    confidence: float = 0.95,
    min_trials: int = MIN_TRIALS_PER_ARM,
) -> Comparison:
    """Treatment vs control as (successes, trials) each."""
    t, c = rate(*treatment, confidence), rate(*control, confidence)
    if t.rate is None or c.rate is None:
        return Comparison(t, c, None, None, None, None, None, False, "no trials in one arm yet")
    diff = t.rate - c.rate
    relative = diff / c.rate if c.rate > 0 else None
    pooled = (t.successes + c.successes) / (t.trials + c.trials)
    se_pooled = math.sqrt(pooled * (1 - pooled) * (1 / t.trials + 1 / c.trials))
    p_value = 1.0 if se_pooled == 0 else min(1.0, 2 * _normal_sf(abs(diff) / se_pooled))
    se = math.sqrt(t.rate * (1 - t.rate) / t.trials + c.rate * (1 - c.rate) / c.trials)
    z = _z(confidence)
    enough = min(t.trials, c.trials) >= min_trials
    significant = p_value < (1 - confidence)
    if not enough:
        note = f"needs at least {min_trials} trials per arm before drawing conclusions"
    elif significant:
        note = "difference is statistically significant"
    else:
        note = "no significant difference yet"
    return Comparison(
        treatment=t,
        control=c,
        lift=round(diff, 6),
        relative_lift=round(relative, 6) if relative is not None else None,
        p_value=round(p_value, 6),
        diff_low=round(diff - z * se, 6),
        diff_high=round(diff + z * se, 6),
        conclusive=enough and significant,
        note=note,
    )


def summarize_arms(
    counts: dict[str, tuple[int, int]],
    control: str = "holdout",
    confidence: float = 0.95,
) -> dict[str, Any]:
    """Rates for every arm plus each non-control arm compared with ``control``."""
    arms = {arm: rate(s, n, confidence).as_dict() for arm, (s, n) in counts.items()}
    comparisons = {
        arm: compare(value, counts[control], confidence).as_dict()
        for arm, value in counts.items()
        if arm != control and control in counts
    }
    return {"control": control, "arms": arms, "comparisons": comparisons}
