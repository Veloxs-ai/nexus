# Copyright 2026 Veloxs AI Inc. All rights reserved.
#
# This file is part of Nexus, proprietary and confidential software of
# Veloxs AI Inc. Use is subject to the Nexus Proprietary Software License;
# see the LICENSE file in the project root. Unauthorized copying,
# distribution, or modification of this file, via any medium, is strictly
# prohibited.
#
# SPDX-License-Identifier: LicenseRef-Veloxs-AI-Proprietary

from nexus_security.config import ObservabilityConfig
from nexus_security.observability import ObservabilityRecorder


def test_observability_recorder_writes_event(tmp_path):
    recorder = ObservabilityRecorder(
        ObservabilityConfig(output_uri="events.jsonl", service_name="security"),
        tmp_path,
    )

    recorder.emit("access_check", 1, {"decision": "allowed"})

    records = recorder.read_all()
    assert records[0]["metric_name"] == "access_check"
    assert records[0]["attributes"] == {"decision": "allowed"}


def test_observability_disabled_skips_event(tmp_path):
    recorder = ObservabilityRecorder(ObservabilityConfig(enabled=False), tmp_path)

    recorder.emit("access_check", 1)

    assert recorder.read_all() == []

