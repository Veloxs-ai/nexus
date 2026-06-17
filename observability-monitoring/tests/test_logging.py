# Copyright 2026 Veloxs AI Inc. All rights reserved.
#
# This file is part of Nexus, proprietary and confidential software of
# Veloxs AI Inc. Use is subject to the Nexus Proprietary Software License;
# see the LICENSE file in the project root. Unauthorized copying,
# distribution, or modification of this file, via any medium, is strictly
# prohibited.
#
# SPDX-License-Identifier: LicenseRef-Veloxs-AI-Proprietary

from nexus_observability.logging import StructuredLogger
from nexus_observability.models import Severity


def test_structured_logger_writes_jsonl(sample_config, tmp_path):
    logger = StructuredLogger(sample_config.storage, tmp_path)

    event = logger.write("orchestration-guardrails", Severity.INFO, "allowed", tenant="default")

    records = logger.read_all()
    assert records[0]["event_id"] == event.event_id
    assert records[0]["severity"] == "info"
    assert records[0]["message"] == "allowed"

