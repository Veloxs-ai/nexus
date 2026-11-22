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

"""Failure-mode diagnosis for ``nexus.operations.signals`` assessments.

``diagnose`` maps the symptoms in an ``Assessment`` (which metric kinds moved, and which way)
to the most specific matching failure pattern, with evidence and recommended checks.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .signals import Assessment

__all__ = ["FAILURE_PATTERNS", "Diagnosis", "diagnose"]


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
