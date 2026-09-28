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

"""Condition monitoring: explainable anomaly scores from streaming sensor readings.

An ``AssetMonitor`` keeps a small, serializable state per asset and turns readings into an
``Assessment`` that decision tables can use (``anomaly_score``, ``failure_risk``,
``data_quality``, ``top_signal``) plus reason codes a maintenance engineer can check:

  * limits      — beyond the engineering alarm (1.0) or warning (0.6) limit
  * robust z    — distance from the recent median in MADs (resistant to the spikes it detects)
  * drift       — fast EWMA versus slow EWMA baseline, in baseline standard deviations
  * rate        — least-squares slope over the window versus the allowed rate of change
  * time to limit — at the current slope, hours until the alarm limit (drives failure risk)
  * data quality — implausible values, flatlined (stuck) sensors, missing data

Per-metric scores are fused with a noisy-OR, so two moderate symptoms (vibration drifting
and temperature rising) outrank one noisy one. ``diagnose`` maps the pattern of symptoms to
a likely failure mode with recommended checks; it is a transparent starting point for a
technician, not a replacement for one.
"""

from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from statistics import median
from typing import Any

RECENT_POINTS = 120  # raw readings kept (about two hours at one per minute)
HISTORY_POINTS = 288  # down-sampled baseline: one point per HISTORY_STEP (a day at 5 minutes)
HISTORY_STEP = 300.0
FAST_TAU = 15 * 60.0  # seconds: the "current level"
SLOW_TAU = 12 * 3600.0  # seconds: the baseline the current level is compared with
SLOPE_MIN_T = 4.0  # a trend must be this many standard errors from zero to count


def _aware(ts: datetime) -> datetime:
    return ts if ts.tzinfo else ts.replace(tzinfo=UTC)


def _logistic(x: float, center: float, steepness: float = 1.5) -> float:
    return 1.0 / (1.0 + math.exp(-steepness * (x - center)))


@dataclass(frozen=True)
class SignalSpec:
    """How to judge one metric. Limits are engineering values in the metric's unit."""

    name: str
    unit: str = ""
    warn_high: float | None = None
    alarm_high: float | None = None
    warn_low: float | None = None
    alarm_low: float | None = None
    valid_min: float | None = None  # outside = sensor fault, not an anomaly
    valid_max: float | None = None
    max_rate_per_hour: float | None = None
    z_threshold: float = 3.5
    drift_threshold: float = 3.0
    flatline_minutes: float = 30.0
    expected_interval_seconds: float = 60.0
    weight: float = 1.0

    @classmethod
    def from_dict(cls, name: str, data: dict[str, Any]) -> SignalSpec:
        allowed = set(cls.__dataclass_fields__) - {"name"}
        unknown = set(data) - allowed
        if unknown:
            raise ValueError(f"signal '{name}': unknown settings {sorted(unknown)}")
        return cls(name=name, **{k: v for k, v in data.items() if k in allowed})


@dataclass
class _Series:
    """Recent raw points, a down-sampled day of history, and time-aware EWMAs."""

    points: deque = field(default_factory=lambda: deque(maxlen=RECENT_POINTS))  # (epoch s, value)
    history: deque = field(
        default_factory=lambda: deque(maxlen=HISTORY_POINTS)
    )  # one per HISTORY_STEP
    fast: float | None = None
    slow: float | None = None
    slow_var: float = 0.0
    last_t: float | None = None

    def add(self, t: float, value: float) -> None:
        self.points.append((t, value))
        if not self.history or t - self.history[-1][0] >= HISTORY_STEP:
            self.history.append((t, value))
        if self.fast is None or self.slow is None or self.last_t is None:
            self.fast = self.slow = value
            self.last_t = t
            return
        dt = max(0.0, t - self.last_t)
        self.last_t = t
        a_fast = 1 - math.exp(-dt / FAST_TAU)
        a_slow = 1 - math.exp(-dt / SLOW_TAU)
        self.fast += a_fast * (value - self.fast)
        delta = value - self.slow
        self.slow += a_slow * delta
        self.slow_var = (1 - a_slow) * (self.slow_var + a_slow * delta * delta)

    def to_dict(self) -> dict[str, Any]:
        return {
            # compact: whole seconds and 4 decimals keep a day of four signals to a few kB
            "points": [[int(t), round(v, 4)] for t, v in self.points],
            "history": [[int(t), round(v, 4)] for t, v in self.history],
            "fast": self.fast,
            "slow": self.slow,
            "slow_var": self.slow_var,
            "last_t": self.last_t,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> _Series:
        s = cls()
        s.points.extend((float(t), float(v)) for t, v in data.get("points") or [])
        s.history.extend((float(t), float(v)) for t, v in data.get("history") or [])
        s.fast, s.slow, s.slow_var = (
            data.get("fast"),
            data.get("slow"),
            float(data.get("slow_var") or 0.0),
        )
        s.last_t = data.get("last_t")
        return s


@dataclass
class Assessment:
    anomaly_score: float
    failure_risk: float
    data_quality: str  # valid | suspect | invalid
    top_signal: str | None
    time_to_limit_hours: float | None
    reasons: list[dict[str, Any]]
    features: dict[str, dict[str, Any]]

    def facts(self) -> dict[str, Any]:
        """The flat facts a strategy reads."""
        return {
            "anomaly_score": self.anomaly_score,
            "failure_risk": self.failure_risk,
            "data_quality": self.data_quality,
            "top_signal": self.top_signal,
            "time_to_limit_hours": self.time_to_limit_hours,
            "anomaly_reasons": [r["code"] for r in self.reasons],
        }

    def as_dict(self) -> dict[str, Any]:
        return {**self.facts(), "reasons": self.reasons, "features": self.features}


class AssetMonitor:
    """Streaming state for one asset. Feed readings in time order; assess at any time."""

    def __init__(self, specs: dict[str, SignalSpec], horizon_hours: float = 72.0):
        self.specs = specs
        self.horizon_hours = horizon_hours
        self.series: dict[str, _Series] = {name: _Series() for name in specs}
        self.last_seen: float | None = None
        self.invalid: dict[str, str] = {}

    # -- input -------------------------------------------------------------------
    def update(self, ts: datetime, readings: dict[str, float | None]) -> None:
        t = _aware(ts).timestamp()
        self.last_seen = max(self.last_seen or t, t)
        for name, value in readings.items():
            spec = self.specs.get(name)
            if spec is None or value is None:
                continue
            try:
                value = float(value)
            except (TypeError, ValueError):
                self.invalid[name] = "not a number"
                continue
            if math.isnan(value) or math.isinf(value):
                self.invalid[name] = "not a number"
                continue
            if (spec.valid_min is not None and value < spec.valid_min) or (
                spec.valid_max is not None and value > spec.valid_max
            ):
                self.invalid[name] = f"implausible value {value:g}{spec.unit}"
                continue
            self.invalid.pop(name, None)
            self.series[name].add(t, value)

    # -- assessment ----------------------------------------------------------------
    def assess(self, now: datetime | None = None) -> Assessment:
        now_t = _aware(now or datetime.now(UTC)).timestamp()
        reasons: list[dict[str, Any]] = []
        features: dict[str, dict[str, Any]] = {}
        scores: list[tuple[float, float, str]] = []  # (score, weight, metric)
        quality = "valid"
        ttl_min: float | None = None
        for name, spec in self.specs.items():
            s = self.series[name]
            if name in self.invalid:
                quality = "invalid"
                reasons.append(
                    {
                        "code": f"{name.upper()}_SENSOR_FAULT",
                        "metric": name,
                        "score": 0.0,
                        "detail": self.invalid[name],
                    }
                )
                continue
            if not s.points:
                continue
            last_t, raw = s.points[-1]
            # Judge the median of the last three readings: one glitch never raises an alarm.
            value = median(v for _, v in list(s.points)[-3:])
            f: dict[str, Any] = {"value": raw, "unit": spec.unit}
            gap = now_t - last_t
            if gap > max(5 * spec.expected_interval_seconds, 300):
                quality = "invalid" if quality == "invalid" else "suspect"
                reasons.append(
                    {
                        "code": f"{name.upper()}_STALE",
                        "metric": name,
                        "score": 0.0,
                        "detail": f"no reading for {gap / 60:.0f} min",
                    }
                )
            window = list(s.points)
            values = [v for _, v in window]
            # flatline: a sensor that reports the same value for too long is probably stuck
            flat_window = [v for t, v in window if t >= last_t - spec.flatline_minutes * 60]
            varied_before = len({v for _, v in s.history}) > 1 or len(set(values)) > 1
            if (
                len(flat_window) >= 10
                and max(flat_window) - min(flat_window) == 0
                and varied_before
            ):
                quality = "invalid" if quality == "invalid" else "suspect"
                reasons.append(
                    {
                        "code": f"{name.upper()}_FLATLINE",
                        "metric": name,
                        "score": 0.0,
                        "detail": f"unchanged for {spec.flatline_minutes:.0f} min",
                    }
                )
            metric_scores: list[
                tuple[str, float, str, str]
            ] = []  # (kind, score, detail, direction)
            # limits
            if spec.alarm_high is not None and value >= spec.alarm_high:
                metric_scores.append(
                    ("ALARM_HIGH", 1.0, f"{value:g} ≥ alarm {spec.alarm_high:g}{spec.unit}", "up")
                )
            elif spec.warn_high is not None and value >= spec.warn_high:
                metric_scores.append(
                    ("WARN_HIGH", 0.6, f"{value:g} ≥ warning {spec.warn_high:g}{spec.unit}", "up")
                )
            if spec.alarm_low is not None and value <= spec.alarm_low:
                metric_scores.append(
                    ("ALARM_LOW", 1.0, f"{value:g} ≤ alarm {spec.alarm_low:g}{spec.unit}", "down")
                )
            elif spec.warn_low is not None and value <= spec.warn_low:
                metric_scores.append(
                    ("WARN_LOW", 0.6, f"{value:g} ≤ warning {spec.warn_low:g}{spec.unit}", "down")
                )
            # robust z against the history before the latest few points
            history = [v for t, v in s.history if t < last_t - 3600] if len(s.history) > 24 else []
            if history:
                med = median(history)
                mad = median(abs(v - med) for v in history) * 1.4826
                if mad > 0:
                    z = abs(value - med) / mad
                    f["robust_z"] = round(z, 2)
                    if z >= spec.z_threshold * 0.7:
                        metric_scores.append(
                            (
                                "SPIKE",
                                _logistic(z, spec.z_threshold),
                                f"{z:.1f} MADs {'above' if value > med else 'below'} the recent "
                                f"median {med:g}{spec.unit}",
                                "up" if value > med else "down",
                            )
                        )
            # drift of the fast average away from the slow baseline
            if (
                s.fast is not None
                and s.slow is not None
                and s.slow_var > 0
                and len(s.history) >= 24
            ):
                drift = (s.fast - s.slow) / math.sqrt(s.slow_var)
                f["drift"] = round(drift, 2)
                if abs(drift) >= spec.drift_threshold * 0.7:
                    metric_scores.append(
                        (
                            "DRIFT",
                            _logistic(abs(drift), spec.drift_threshold),
                            f"running {'above' if drift > 0 else 'below'} its baseline by "
                            f"{abs(drift):.1f} standard deviations",
                            "up" if drift > 0 else "down",
                        )
                    )
            # slope over the last hour (per hour) and time to the alarm limit
            recent = [(t, v) for t, v in window if t >= last_t - 3 * 3600]
            slope = _slope(recent)
            if slope is not None:
                f["slope_per_hour"] = round(slope, 4)
                if spec.max_rate_per_hour and abs(slope) > spec.max_rate_per_hour:
                    ratio = abs(slope) / spec.max_rate_per_hour
                    metric_scores.append(
                        (
                            "FAST_CHANGE",
                            _logistic(ratio, 1.5, 3.0),
                            f"changing {slope:+.3g}{spec.unit}/h "
                            f"(allowed {spec.max_rate_per_hour:g})",
                            "up" if slope > 0 else "down",
                        )
                    )
                ttl = None
                if spec.alarm_high is not None and slope > 0 and value < spec.alarm_high:
                    ttl = (spec.alarm_high - value) / slope
                elif spec.alarm_low is not None and slope < 0 and value > spec.alarm_low:
                    ttl = (value - spec.alarm_low) / -slope
                if ttl is not None:
                    f["time_to_limit_hours"] = round(ttl, 1)
                    if ttl_min is None or ttl < ttl_min:
                        ttl_min = ttl
            best = max(metric_scores, key=lambda m: m[1]) if metric_scores else None
            f["score"] = round(best[1], 4) if best else 0.0
            features[name] = f
            if best and best[1] >= 0.3:
                scores.append((best[1], spec.weight, name))
                reasons.append(
                    {
                        "code": f"{name.upper()}_{best[0]}",
                        "metric": name,
                        "score": round(best[1], 3),
                        "detail": best[2],
                        "direction": best[3],
                    }
                )
        miss = 1.0
        for score, weight, _ in scores:
            miss *= 1.0 - min(1.0, score * weight)
        anomaly = round(1.0 - miss, 4)
        if ttl_min is not None and ttl_min <= self.horizon_hours:
            ttl_risk = 1.0 - ttl_min / self.horizon_hours
        else:
            ttl_risk = 0.0
        alarm = any(
            r["code"].endswith("ALARM_HIGH") or r["code"].endswith("ALARM_LOW") for r in reasons
        )
        failure_risk = round(max(ttl_risk, 1.0 if alarm else 0.0, anomaly * 0.6), 4)
        reasons.sort(key=lambda r: -r["score"])
        top = max(scores)[2] if scores else None
        return Assessment(
            anomaly_score=anomaly,
            failure_risk=failure_risk,
            data_quality=quality,
            top_signal=top,
            time_to_limit_hours=round(ttl_min, 1) if ttl_min is not None else None,
            reasons=reasons,
            features=features,
        )

    # -- persistence -----------------------------------------------------------------
    def to_dict(self) -> dict[str, Any]:
        return {
            "series": {k: s.to_dict() for k, s in self.series.items()},
            "last_seen": self.last_seen,
            "invalid": self.invalid,
        }

    @classmethod
    def from_dict(
        cls, specs: dict[str, SignalSpec], data: dict[str, Any] | None, horizon_hours: float = 72.0
    ) -> AssetMonitor:
        monitor = cls(specs, horizon_hours)
        for name, series in ((data or {}).get("series") or {}).items():
            if name in specs:
                monitor.series[name] = _Series.from_dict(series)
        monitor.last_seen = (data or {}).get("last_seen")
        monitor.invalid = dict((data or {}).get("invalid") or {})
        return monitor


def _slope(points: list[tuple[float, float]]) -> float | None:
    """Least-squares slope in value units per hour, or None when it is not significant."""
    n = len(points)
    if n < 10:
        return None
    t0 = points[0][0]
    xs = [(t - t0) / 3600 for t, _ in points]
    ys = [v for _, v in points]
    mx, my = sum(xs) / n, sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    if sxx == 0:
        return None
    slope = sum((x - mx) * (y - my) for x, y in zip(xs, ys, strict=True)) / sxx
    residual = sum((y - (my + slope * (x - mx))) ** 2 for x, y in zip(xs, ys, strict=True))
    stderr = math.sqrt(residual / (n - 2) / sxx) if n > 2 else 0.0
    if stderr > 0 and abs(slope) / stderr < SLOPE_MIN_T:
        return None  # indistinguishable from noise
    return slope


def specs_from_dict(data: dict[str, dict[str, Any]]) -> dict[str, SignalSpec]:
    return {name: SignalSpec.from_dict(name, spec or {}) for name, spec in (data or {}).items()}


# ---------------------------------------------------------------------------
# Diagnosis
# ---------------------------------------------------------------------------


@dataclass
class Diagnosis:
    failure_mode: str
    confidence: float
    evidence: list[str]
    recommended_checks: list[str]

    def as_dict(self) -> dict[str, Any]:
        return {
            "failure_mode": self.failure_mode,
            "confidence": self.confidence,
            "evidence": self.evidence,
            "recommended_checks": self.recommended_checks,
        }


# (failure mode, required symptoms, supporting symptoms, checks).
# Symptoms are "<metric kind>:<direction>".
FAILURE_PATTERNS: list[tuple[str, set[str], set[str], list[str]]] = [
    (
        "sensor fault",
        {"any:fault"},
        set(),
        [
            "Check the sensor wiring and connector",
            "Compare with a handheld reading",
            "Recalibrate or replace the sensor",
        ],
    ),
    (
        "bearing wear",
        {"vibration:up"},
        {"temperature:up"},
        [
            "Measure vibration spectrum at the bearing housings",
            "Check lubrication (quantity, contamination)",
            "Inspect for looseness and misalignment",
            "Plan bearing replacement if the trend continues",
        ],
    ),
    (
        "cavitation",
        {"pressure:down", "vibration:up"},
        set(),
        [
            "Check suction pressure and NPSH available",
            "Inspect the suction strainer for blockage",
            "Verify the pump is operating near its best efficiency point",
        ],
    ),
    (
        "electrical overload",
        {"current:up"},
        {"temperature:up"},
        [
            "Check phase currents for imbalance",
            "Inspect terminals for heat damage",
            "Verify the driven load",
        ],
    ),
    (
        "overheating",
        {"temperature:up"},
        set(),
        [
            "Check cooling (fan, heat exchanger, airflow)",
            "Check lubricant level and condition",
            "Compare against ambient temperature",
        ],
    ),
    (
        "leak or blockage",
        {"pressure:down"},
        set(),
        [
            "Inspect for leaks on the discharge side",
            "Check valves and filters",
            "Verify set points",
        ],
    ),
]


def _kind(metric: str) -> str:
    m = metric.lower()
    for kind, words in (
        ("vibration", ("vib",)),
        ("temperature", ("temp",)),
        ("current", ("current", "amp")),
        ("pressure", ("press",)),
        ("flow", ("flow",)),
        ("speed", ("speed", "rpm")),
    ):
        if any(w in m for w in words):
            return kind
    return m


def diagnose(assessment: Assessment) -> Diagnosis:
    symptoms: set[str] = set()
    evidence: list[str] = []
    for r in assessment.reasons:
        metric = r.get("metric") or ""
        kind = _kind(metric)
        code = r["code"]
        if code.endswith(("SENSOR_FAULT", "FLATLINE")):
            symptoms.add("any:fault")
        elif r.get("direction") in ("up", "down"):
            symptoms.add(f"{kind}:{r['direction']}")
        else:
            continue
        evidence.append(f"{metric}: {r.get('detail')}")
    # Most specific pattern first (sensor faults always win: the other symptoms may be artefacts).
    ordered = sorted(FAILURE_PATTERNS, key=lambda p: (p[0] != "sensor fault", -len(p[1])))
    for mode, required, supporting, checks in ordered:
        if required <= symptoms:
            support = len(supporting & symptoms) / len(supporting) if supporting else 0.0
            confidence = round(min(0.95, 0.55 + 0.3 * support + 0.1 * (len(required) - 1)), 2)
            return Diagnosis(mode, confidence, evidence, checks)
    if assessment.anomaly_score >= 0.5:
        return Diagnosis(
            "unclassified anomaly",
            0.3,
            evidence,
            ["Review the trends of the flagged signals", "Inspect the asset on the next round"],
        )
    return Diagnosis("normal", 0.9, evidence, [])


def window_stats(points: list[tuple[datetime, float]], size: timedelta) -> list[dict[str, Any]]:
    """Tumbling-window aggregates (count, mean, min, max, last) for charts and features."""
    out: dict[int, list[float]] = {}
    step = size.total_seconds()
    for ts, value in points:
        bucket = int(_aware(ts).timestamp() // step)
        out.setdefault(bucket, []).append(value)
    return [
        {
            "window_start": datetime.fromtimestamp(b * step, UTC).isoformat(),
            "count": len(vs),
            "mean": round(sum(vs) / len(vs), 4),
            "min": min(vs),
            "max": max(vs),
            "last": vs[-1],
        }
        for b, vs in sorted(out.items())
    ]
