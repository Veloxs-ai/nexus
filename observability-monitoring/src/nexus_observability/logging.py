# Copyright 2026 Veloxs AI Inc. All rights reserved.
#
# This file is part of Nexus, proprietary and confidential software of
# Veloxs AI Inc. Use is subject to the Nexus Proprietary Software License;
# see the LICENSE file in the project root. Unauthorized copying,
# distribution, or modification of this file, via any medium, is strictly
# prohibited.
#
# SPDX-License-Identifier: LicenseRef-Veloxs-AI-Proprietary

from __future__ import annotations

from pathlib import Path

from nexus_observability.config import StorageConfig
from nexus_observability.io import append_jsonl, read_jsonl
from nexus_observability.models import LogEvent, Severity


class StructuredLogger:
    def __init__(self, storage: StorageConfig, base_dir: Path) -> None:
        self.storage = storage
        self.base_dir = base_dir

    def write(
        self,
        service: str,
        severity: Severity,
        message: str,
        tenant: str | None = None,
        trace_id: str | None = None,
        attributes: dict | None = None,
    ) -> LogEvent:
        event = LogEvent(
            service=service,
            severity=severity,
            message=message,
            tenant=tenant,
            trace_id=trace_id,
            attributes=attributes or {},
        )
        append_jsonl(self.storage.logs_uri, self.base_dir, event)
        return event

    def read_all(self) -> list[dict]:
        return read_jsonl(self.storage.logs_uri, self.base_dir)

