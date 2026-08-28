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

import json

from nexus_observability.cli import main


def write_config(tmp_path):
    config_path = tmp_path / "observability.json"
    config_path.write_text(
        json.dumps(
            {
                "storage": {
                    "metrics_uri": "metrics.jsonl",
                    "logs_uri": "logs.jsonl",
                    "traces_uri": "traces.jsonl",
                    "ai_interactions_uri": "ai.jsonl",
                    "alerts_uri": "alerts.jsonl",
                },
                "services": {
                    "svc": {
                        "layer": "test",
                        "owner": "test",
                        "slo_latency_ms": 100,
                        "slo_error_rate": 0.01,
                    }
                },
                "alerts": {
                    "latency_ms_threshold": 100,
                    "error_rate_threshold": 0.05,
                    "min_ai_confidence": 0.5,
                },
                "exporters": {},
            }
        ),
        encoding="utf-8",
    )
    return config_path


def test_validate_config_command(capsys):
    exit_code = main(["validate-config", "configs/observability.json"])

    assert exit_code == 0
    assert "Loaded 7 monitored services and 6 exporters." in capsys.readouterr().out


def test_record_metric_command(tmp_path, capsys):
    config_path = write_config(tmp_path)

    exit_code = main(
        [
            "record-metric",
            str(config_path),
            "experience-api-engagement",
            "request_latency_ms",
            "125",
            "--kind",
            "histogram",
            "--tenant",
            "default",
        ]
    )

    assert exit_code == 0
    assert "metric_event_id:" in capsys.readouterr().out


def test_log_command(tmp_path, capsys):
    config_path = write_config(tmp_path)

    exit_code = main(["log", str(config_path), "svc", "info", "hello"])

    assert exit_code == 0
    assert "log_event_id:" in capsys.readouterr().out


def test_trace_command(tmp_path, capsys):
    config_path = write_config(tmp_path)

    exit_code = main(["trace", str(config_path), "svc", "ask", "42", "trace-1"])

    assert exit_code == 0
    assert "span_id:" in capsys.readouterr().out


def test_record_ai_command(tmp_path, capsys):
    config_path = write_config(tmp_path)

    exit_code = main(["record-ai", str(config_path), "default", "allowed", "0.1", "1", "99"])

    assert exit_code == 0
    assert "ai_event_id:" in capsys.readouterr().out


def test_evaluate_alerts_command(tmp_path, capsys):
    config_path = write_config(tmp_path)
    main(["record-metric", str(config_path), "svc", "request_latency_ms", "500"])

    exit_code = main(["evaluate-alerts", str(config_path)])

    assert exit_code == 0
    assert "alerts_written:" in capsys.readouterr().out
