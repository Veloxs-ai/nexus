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

from nexus_observability.logging import StructuredLogger
from nexus_observability.models import Severity


def test_structured_logger_writes_jsonl(sample_config, tmp_path):
    logger = StructuredLogger(sample_config.storage, tmp_path)

    event = logger.write("orchestration-guardrails", Severity.INFO, "allowed", tenant="default")

    records = logger.read_all()
    assert records[0]["event_id"] == event.event_id
    assert records[0]["severity"] == "info"
    assert records[0]["message"] == "allowed"
