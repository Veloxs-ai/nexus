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

from __future__ import annotations

from pathlib import Path

from .config import StorageConfig
from .io import append_jsonl, read_jsonl
from .models import LogEvent, Severity


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
