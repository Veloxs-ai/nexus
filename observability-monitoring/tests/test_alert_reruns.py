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

from nexus_observability.io import append_jsonl, iter_jsonl, read_jsonl
from nexus_observability.models import MetricKind
from nexus_observability.service import ObservabilityService


def test_re_evaluating_alerts_writes_each_alert_once(sample_config, tmp_path):
    service = ObservabilityService(sample_config, tmp_path)
    for value in (250, 900, 10):
        service.metrics.record("svc", "request_latency_ms", value, MetricKind.HISTOGRAM)
    service.record_ai_interaction("default", "allowed", 0.9, 1, 100)

    assert service.evaluate_existing_alerts() == 2
    assert service.evaluate_existing_alerts() == 0
    assert len(service.alerts.read_all()) == 2
    service.metrics.record("svc", "request_latency_ms", 700, MetricKind.HISTOGRAM)
    assert service.evaluate_existing_alerts() == 1


def test_append_creates_missing_directories_and_reads_stream(tmp_path):
    append_jsonl("deep/dir/events.jsonl", tmp_path, {"a": 1})
    append_jsonl("deep/dir/events.jsonl", tmp_path, {"a": 2})
    assert read_jsonl("deep/dir/events.jsonl", tmp_path) == [{"a": 1}, {"a": 2}]
    assert next(iter_jsonl("deep/dir/events.jsonl", tmp_path)) == {"a": 1}
    assert list(iter_jsonl("missing.jsonl", tmp_path)) == []
