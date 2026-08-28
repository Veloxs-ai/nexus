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

from nexus_observability.traces import TraceRecorder


def test_trace_recorder_writes_span(sample_config, tmp_path):
    recorder = TraceRecorder(sample_config.storage, tmp_path)

    span = recorder.record("experience-api-engagement", "ask", 55, "trace-1")

    records = recorder.read_all()
    assert records[0]["span_id"] == span.span_id
    assert records[0]["trace_id"] == "trace-1"
