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

import pytest

from nexus_pipeline.connectors.api import (
    ConnectorSecurityError,
    RestApiConnector,
    _RefuseRedirects,
)


def install_fake_fetch(monkeypatch, responses):
    calls = []

    def fake_fetch(url, headers):
        calls.append({"url": url, "headers": headers})
        return responses.pop(0)

    monkeypatch.setattr("nexus_pipeline.connectors.api._fetch_json", fake_fetch)
    return calls


def test_rest_api_connector_pages_and_uses_checkpoint(monkeypatch, make_source):
    calls = install_fake_fetch(
        monkeypatch,
        [
            {"data": [{"id": "1"}], "next": "/v1/accounts?page=2"},
            {"data": [{"id": "2"}]},
        ],
    )
    monkeypatch.setenv("CRM_API_TOKEN", "secret")
    source = make_source(
        connection={
            "base_url": "https://crm.example.com",
            "auth_env": "CRM_API_TOKEN",
            "endpoint": "/v1/accounts",
            "page_size": 100,
        }
    )

    records = list(RestApiConnector(source).read("2026-05-06T00:00:00+00:00"))

    assert records == [{"id": "1"}, {"id": "2"}]
    assert calls[0]["url"] == (
        "https://crm.example.com/v1/accounts"
        "?limit=100&updated_after=2026-05-06T00%3A00%3A00%2B00%3A00"
    )
    assert calls[0]["headers"] == {"Authorization": "Bearer secret"}
    assert calls[1]["url"] == "https://crm.example.com/v1/accounts?page=2"
    assert calls[1]["headers"] == {"Authorization": "Bearer secret"}


def test_rest_api_connector_refuses_cross_origin_next(monkeypatch, make_source):
    calls = install_fake_fetch(
        monkeypatch,
        [{"data": [{"id": "1"}], "next": "http://attacker.example/leak"}],
    )
    monkeypatch.setenv("CRM_API_TOKEN", "secret")
    source = make_source(
        connection={
            "base_url": "https://crm.example.com",
            "auth_env": "CRM_API_TOKEN",
            "endpoint": "/v1/accounts",
        }
    )

    with pytest.raises(ConnectorSecurityError):
        list(RestApiConnector(source).read())

    assert all("attacker.example" not in call["url"] for call in calls)


def test_rest_api_connector_refuses_ssrf_to_metadata_service(monkeypatch, make_source):
    install_fake_fetch(
        monkeypatch,
        [{"data": [], "next": "http://169.254.169.254/latest/meta-data/"}],
    )
    monkeypatch.setenv("CRM_API_TOKEN", "secret")
    source = make_source(
        connection={
            "base_url": "https://crm.example.com",
            "auth_env": "CRM_API_TOKEN",
            "endpoint": "/v1/accounts",
        }
    )

    with pytest.raises(ConnectorSecurityError):
        list(RestApiConnector(source).read())


def test_rest_api_connector_refuses_non_http_scheme(monkeypatch, make_source):
    install_fake_fetch(monkeypatch, [{"data": [], "next": "file:///etc/passwd"}])
    monkeypatch.setenv("CRM_API_TOKEN", "secret")
    source = make_source(
        connection={
            "base_url": "https://crm.example.com",
            "auth_env": "CRM_API_TOKEN",
            "endpoint": "/v1/accounts",
        }
    )

    with pytest.raises(ConnectorSecurityError):
        list(RestApiConnector(source).read())


def test_rest_api_connector_refuses_non_http_base_url(monkeypatch, make_source):
    install_fake_fetch(monkeypatch, [])
    source = make_source(
        connection={
            "base_url": "file:///srv/data",
            "auth_env": "CRM_API_TOKEN",
            "endpoint": "/v1/accounts",
        }
    )

    with pytest.raises(ConnectorSecurityError):
        list(RestApiConnector(source).read())


def test_rest_api_connector_allows_same_origin_absolute_next(monkeypatch, make_source):
    install_fake_fetch(
        monkeypatch,
        [
            {"data": [{"id": "1"}], "next": "https://crm.example.com/v1/accounts?page=2"},
            {"data": [{"id": "2"}]},
        ],
    )
    monkeypatch.setenv("CRM_API_TOKEN", "secret")
    source = make_source(
        connection={
            "base_url": "https://crm.example.com",
            "auth_env": "CRM_API_TOKEN",
            "endpoint": "/v1/accounts",
        }
    )

    records = list(RestApiConnector(source).read())

    assert [record["id"] for record in records] == ["1", "2"]


def test_redirect_handler_fails_closed():
    handler = _RefuseRedirects()

    with pytest.raises(ConnectorSecurityError):
        handler.redirect_request(None, None, 302, "Found", {}, "https://attacker.example/")
