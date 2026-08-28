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

from nexus_observability.config import ExporterConfig
from nexus_observability.exporters import enabled_exporters, validate_exporter, validate_exporters


def test_validate_exporter_accepts_supported_enabled_exporter():
    issues = validate_exporter(
        "otel",
        ExporterConfig(enabled=True, type="opentelemetry", endpoint="http://localhost:4318"),
    )

    assert issues == []


def test_validate_exporter_rejects_unsupported_type():
    issues = validate_exporter("bad", ExporterConfig(enabled=True, type="unknown", endpoint="x"))

    assert issues == ["bad: unsupported exporter type unknown"]


def test_validate_exporter_reports_missing_api_key(monkeypatch):
    monkeypatch.delenv("DATADOG_API_KEY", raising=False)

    issues = validate_exporter(
        "datadog",
        ExporterConfig(
            enabled=True,
            type="datadog",
            endpoint="https://api.datadoghq.com",
            api_key_env="DATADOG_API_KEY",
        ),
    )

    assert issues == ["datadog: missing API key environment variable DATADOG_API_KEY"]


def test_enabled_exporters_returns_enabled_names(sample_config):
    assert enabled_exporters(sample_config) == ["otel"]
    assert validate_exporters(sample_config) == []
