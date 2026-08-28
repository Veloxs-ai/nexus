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
