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

from .config import ObservabilityConfig
from .io import append_jsonl, read_jsonl
from .models import TelemetryEvent


class ObservabilityRecorder:
    def __init__(self, config: ObservabilityConfig, base_dir: Path) -> None:
        self.config = config
        self.base_dir = base_dir

    def emit(self, metric_name: str, value: float, attributes: dict | None = None) -> None:
        if not self.config.enabled:
            return
        append_jsonl(
            self.config.output_uri,
            self.base_dir,
            TelemetryEvent(
                service_name=self.config.service_name,
                metric_name=metric_name,
                value=value,
                attributes=attributes or {},
            ),
        )

    def read_all(self) -> list[dict]:
        return read_jsonl(self.config.output_uri, self.base_dir)
