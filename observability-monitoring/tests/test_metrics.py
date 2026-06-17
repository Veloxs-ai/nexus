# Copyright 2026 Veloxs AI Inc. All rights reserved.
#
# This file is part of Nexus, proprietary and confidential software of
# Veloxs AI Inc. Use is subject to the Nexus Proprietary Software License;
# see the LICENSE file in the project root. Unauthorized copying,
# distribution, or modification of this file, via any medium, is strictly
# prohibited.
#
# SPDX-License-Identifier: LicenseRef-Veloxs-AI-Proprietary

from nexus_observability.metrics import MetricRecorder
from nexus_observability.models import MetricKind


def test_metric_recorder_writes_jsonl(sample_config, tmp_path):
    recorder = MetricRecorder(sample_config.storage, tmp_path)

    event = recorder.record(
        "experience-api-engagement",
        "request_latency_ms",
        42,
        MetricKind.HISTOGRAM,
        "default",
    )

    records = recorder.read_all()
    assert records[0]["event_id"] == event.event_id
    assert records[0]["kind"] == "histogram"

