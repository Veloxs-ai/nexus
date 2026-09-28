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

"""Condition monitoring: anomaly scores, data quality, time to limit and diagnosis."""

import random
from datetime import UTC, datetime, timedelta

import pytest

from nexus.operations import AssetMonitor, diagnose, specs_from_dict, window_stats

SPECS = specs_from_dict(
    {
        "vibration_rms": {
            "unit": " mm/s",
            "warn_high": 4.5,
            "alarm_high": 7.1,
            "valid_min": 0,
            "valid_max": 50,
            "max_rate_per_hour": 0.5,
        },
        "bearing_temp": {
            "unit": " °C",
            "warn_high": 80,
            "alarm_high": 90,
            "valid_min": -20,
            "valid_max": 200,
        },
        "motor_current": {
            "unit": " A",
            "warn_high": 48,
            "alarm_high": 55,
            "valid_min": 0,
            "valid_max": 200,
        },
        "discharge_pressure": {
            "unit": " bar",
            "warn_low": 3.5,
            "alarm_low": 2.5,
            "valid_min": 0,
            "valid_max": 40,
        },
    }
)
T0 = datetime(2026, 10, 1, tzinfo=UTC)
START = 18 * 60  # faults begin after 18 hours of normal running


def _run(change, hours=24):
    rnd = random.Random(1)
    monitor = AssetMonitor(SPECS)
    ts = T0
    for i in range(hours * 60):
        ts = T0 + timedelta(minutes=i)
        r = {
            "vibration_rms": 2.5 + rnd.gauss(0, 0.15),
            "bearing_temp": 60 + rnd.gauss(0, 1),
            "motor_current": 40 + rnd.gauss(0, 0.8),
            "discharge_pressure": 6 + rnd.gauss(0, 0.1),
        }
        change(i, r)
        monitor.update(ts, r)
    return monitor, monitor.assess(ts)


def _ramp(**rates):
    def change(i, r):
        for metric, rate in rates.items():
            r[metric] += max(0, i - START) * rate

    return change


def test_normal_operation_is_quiet():
    _, a = _run(lambda i, r: None)
    assert a.anomaly_score < 0.1 and a.failure_risk < 0.1 and a.data_quality == "valid"
    assert diagnose(a).failure_mode == "normal"


@pytest.mark.parametrize(
    ("change", "mode"),
    [
        (_ramp(vibration_rms=0.004, bearing_temp=0.02), "bearing wear"),
        (_ramp(discharge_pressure=-0.008, vibration_rms=0.004), "cavitation"),
        (_ramp(bearing_temp=0.05, motor_current=0.03), "electrical overload"),
    ],
)
def test_degradation_is_detected_and_diagnosed(change, mode):
    _, a = _run(change)
    assert a.anomaly_score > 0.9 and a.failure_risk > 0.7
    assert a.time_to_limit_hours is not None and a.time_to_limit_hours < 24
    d = diagnose(a)
    assert d.failure_mode == mode and d.recommended_checks and d.evidence


def test_early_trend_gives_warning_hours_ahead():
    def change(i, r):
        r["vibration_rms"] += max(0, i - 22 * 60) * 0.004  # two hours into a slow rise

    _, a = _run(change)
    assert a.failure_risk > 0.5 and 8 < a.time_to_limit_hours < 30


def test_single_glitch_is_ignored_but_a_sustained_step_is_not():
    _, glitch = _run(lambda i, r: r.__setitem__("vibration_rms", 6.0) if i == 24 * 60 - 1 else None)
    assert glitch.anomaly_score < 0.1
    _, step = _run(lambda i, r: r.__setitem__("vibration_rms", 6.0) if i >= 24 * 60 - 3 else None)
    assert step.anomaly_score > 0.9 and step.top_signal == "vibration_rms"


def test_sensor_problems_are_data_quality_not_failures():
    _, stuck = _run(lambda i, r: r.__setitem__("vibration_rms", 2.61) if i > START else None)
    assert stuck.data_quality == "suspect" and diagnose(stuck).failure_mode == "sensor fault"
    _, bad = _run(lambda i, r: r.__setitem__("bearing_temp", 999) if i > START else None)
    assert bad.data_quality == "invalid" and any(
        "SENSOR_FAULT" in c for c in bad.facts()["anomaly_reasons"]
    )


def test_state_round_trips_and_stale_data_is_flagged():
    monitor, _ = _run(lambda i, r: None, hours=2)
    restored = AssetMonitor.from_dict(SPECS, monitor.to_dict())
    later = T0 + timedelta(hours=2)
    assert restored.assess(later).anomaly_score == monitor.assess(later).anomaly_score
    stale = restored.assess(later + timedelta(hours=3))
    assert stale.data_quality == "suspect" and any(
        r["code"].endswith("_STALE") for r in stale.reasons
    )


def test_unknown_signal_settings_are_rejected():
    with pytest.raises(ValueError, match="unknown settings"):
        specs_from_dict({"x": {"alarm_hi": 3}})


def test_window_stats():
    rows = window_stats(
        [(T0 + timedelta(minutes=m), float(m)) for m in range(30)], timedelta(minutes=10)
    )
    assert [r["count"] for r in rows] == [10, 10, 10] and rows[1]["mean"] == 14.5
