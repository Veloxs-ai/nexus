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

"""ServiceNow, Maximo and Teams work items: idempotent create, request shapes, errors."""

import io
import json
import urllib.error
import urllib.request

import pytest

from nexus.operations import WorkItem, outbound, work_provider_from_config
from nexus.operations.workorders import MaximoProvider, ServiceNowProvider, TeamsProvider

ITEM = WorkItem(
    title="P-101 bearing wear",
    description="Vibration rising; bearing wear likely.",
    idempotency_key="P-101|2026-10-01|work_order",
    asset_ref="P-101",
    priority=2,
    details={"anomaly": 0.97, "time to limit": "13 h"},
)


class FakeHttp:
    def __init__(self, responses):
        self.responses, self.calls = list(responses), []

    def __call__(self, request, timeout=None):
        self.calls.append(
            (
                request.get_method(),
                request.full_url,
                dict(request.header_items()),
                json.loads(request.data) if request.data else None,
            )
        )
        status, body = self.responses.pop(0)
        if status >= 400:
            raise urllib.error.HTTPError(request.full_url, status, "err", {}, io.BytesIO(b"boom"))
        return io.BytesIO(json.dumps(body).encode())


def _patch(monkeypatch, responses):
    fake = FakeHttp(responses)

    class Ctx:
        def __init__(self, stream):
            self.stream = stream

        def __enter__(self):
            return self.stream

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(
        outbound, "transport", lambda req, timeout=None: Ctx(fake(req, timeout))
    )
    return fake


def test_servicenow_creates_once_with_correlation_id(monkeypatch):
    fake = _patch(
        monkeypatch,
        [(200, {"result": []}), (201, {"result": {"number": "INC0010001", "sys_id": "abc"}})],
    )
    r = ServiceNowProvider("https://bank.service-now.com", username="svc", password="pw").submit(
        ITEM
    )
    assert r.ok and r.created and r.ref == "INC0010001"
    method, url, headers, body = fake.calls[1]
    assert method == "POST" and url.endswith("/api/now/table/incident")
    assert body["correlation_id"] == ITEM.idempotency_key and body["cmdb_ci"] == "P-101"
    assert headers["Authorization"].startswith("Basic ")
    fake = _patch(monkeypatch, [(200, {"result": [{"number": "INC0010001", "sys_id": "abc"}]})])
    again = ServiceNowProvider("https://bank.service-now.com", token="t").submit(ITEM)
    assert again.ok and not again.created and again.ref == "INC0010001" and len(fake.calls) == 1


def test_maximo_work_order_and_retryable_errors(monkeypatch):
    fake = _patch(monkeypatch, [(200, {"member": []}), (201, {"wonum": "1042"})])
    r = MaximoProvider("https://maximo.bank.in", "key", "PLANT1").submit(ITEM)
    assert r.ok and r.ref == "1042"
    _, url, headers, body = fake.calls[1]
    assert "mxapiwodetail" in url and headers["Apikey"] == "key"
    assert (
        body["externalrefid"] == ITEM.idempotency_key
        and body["assetnum"] == "P-101"
        and body["wopriority"] == 2
    )
    _patch(monkeypatch, [(503, {})])
    down = MaximoProvider("https://maximo.bank.in", "key", "PLANT1").submit(ITEM)
    assert not down.ok and down.retryable
    _patch(monkeypatch, [(200, {"member": []}), (400, {})])
    rejected = MaximoProvider("https://maximo.bank.in", "key", "PLANT1").submit(ITEM)
    assert not rejected.ok and not rejected.retryable


def test_teams_card_and_safety(monkeypatch):
    fake = _patch(monkeypatch, [(200, {})])
    assert TeamsProvider("https://example.webhook.office.com/x").submit(ITEM).ok
    card = fake.calls[0][3]["attachments"][0]["content"]
    assert card["type"] == "AdaptiveCard" and card["body"][0]["text"] == ITEM.title
    with pytest.raises(ValueError):
        ServiceNowProvider("http://bank.service-now.com", token="t")
    with pytest.raises(ValueError):
        ServiceNowProvider("https://bank.service-now.com")
    dry = work_provider_from_config({})
    assert dry.submit(ITEM).ok and dry.items == [ITEM]
    with pytest.raises(ValueError):
        work_provider_from_config({"provider": "jira"})


def test_ticket_status_is_read_back_and_normalized(monkeypatch):
    fake = _patch(
        monkeypatch,
        [
            (
                200,
                {
                    "result": [
                        {
                            "number": "INC1",
                            "state": "6",
                            "resolved_at": "2026-10-02 09:15:00",
                            "close_code": "Solution provided",
                        }
                    ]
                },
            ),
            (200, {"result": []}),
        ],
    )
    snow = ServiceNowProvider("https://bank.service-now.com", token="t")
    status = snow.status("INC1")
    assert status.ok and status.state == "resolved" and status.done
    assert status.resolved_at == "2026-10-02 09:15:00" and status.resolution == "Solution provided"
    assert "number%3DINC1" in fake.calls[0][1]
    missing = snow.status("INC404")
    assert not missing.ok and missing.error == "ticket not found"

    fake = _patch(
        monkeypatch,
        [
            (200, {"member": [{"wonum": "1042", "status": "INPRG"}]}),
            (
                200,
                {
                    "member": [
                        {
                            "wonum": "1042",
                            "status": "CLOSE",
                            "actfinish": "2026-10-03T11:00:00+05:30",
                        }
                    ]
                },
            ),
        ],
    )
    maximo = MaximoProvider("https://maximo.bank.in", "key", "PLANT1")
    working = maximo.status("1042")
    assert working.state == "in_progress" and not working.done
    closed = maximo.status("1042")
    assert closed.state == "closed" and closed.resolved_at.startswith("2026-10-03")
    assert "siteid" in fake.calls[0][1]
