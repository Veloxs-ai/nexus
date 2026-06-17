# Copyright 2026 Veloxs AI Inc. All rights reserved.
#
# This file is part of Nexus, proprietary and confidential software of
# Veloxs AI Inc. Use is subject to the Nexus Proprietary Software License;
# see the LICENSE file in the project root. Unauthorized copying,
# distribution, or modification of this file, via any medium, is strictly
# prohibited.
#
# SPDX-License-Identifier: LicenseRef-Veloxs-AI-Proprietary

from nexus_observability.traces import TraceRecorder


def test_trace_recorder_writes_span(sample_config, tmp_path):
    recorder = TraceRecorder(sample_config.storage, tmp_path)

    span = recorder.record("experience-api-engagement", "ask", 55, "trace-1")

    records = recorder.read_all()
    assert records[0]["span_id"] == span.span_id
    assert records[0]["trace_id"] == "trace-1"

