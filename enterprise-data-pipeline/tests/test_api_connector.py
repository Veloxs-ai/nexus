from __future__ import annotations

from nexus_pipeline.connectors.api import RestApiConnector


class FakeResponse:
    def __init__(self, body):
        self.body = body

    def json(self):
        return self.body

    def raise_for_status(self):
        return None


class FakeClient:
    calls = []
    responses = [
        FakeResponse({"data": [{"id": "1"}], "next": "/v1/accounts?page=2"}),
        FakeResponse({"data": [{"id": "2"}]}),
    ]

    def __init__(self, *, base_url, timeout):
        self.base_url = base_url
        self.timeout = timeout

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return None

    def get(self, path, *, headers, params):
        self.calls.append({"path": path, "headers": headers, "params": params})
        return self.responses.pop(0)


def test_rest_api_connector_pages_and_uses_checkpoint(monkeypatch, make_source):
    FakeClient.calls = []
    FakeClient.responses = [
        FakeResponse({"data": [{"id": "1"}], "next": "/v1/accounts?page=2"}),
        FakeResponse({"data": [{"id": "2"}]}),
    ]
    monkeypatch.setenv("CRM_API_TOKEN", "secret")
    monkeypatch.setattr("nexus_pipeline.connectors.api.httpx.Client", FakeClient)
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
    assert FakeClient.calls[0] == {
        "path": "/v1/accounts",
        "headers": {"Authorization": "Bearer secret"},
        "params": {"limit": 100, "updated_after": "2026-05-06T00:00:00+00:00"},
    }
    assert FakeClient.calls[1] == {
        "path": "/v1/accounts?page=2",
        "headers": {"Authorization": "Bearer secret"},
        "params": {},
    }

