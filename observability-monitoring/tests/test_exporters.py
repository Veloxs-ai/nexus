# Copyright 2026 Veloxs AI Inc. All rights reserved.
#
# This file is part of Nexus, proprietary and confidential software of
# Veloxs AI Inc. Use is subject to the Nexus Proprietary Software License;
# see the LICENSE file in the project root. Unauthorized copying,
# distribution, or modification of this file, via any medium, is strictly
# prohibited.
#
# SPDX-License-Identifier: LicenseRef-Veloxs-AI-Proprietary

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

