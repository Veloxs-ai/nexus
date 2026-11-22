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

"""Table masking: memoised values equal per-row masking; nested values never leak."""

from __future__ import annotations

import random

from nexus_guardrails import pii_columns
from nexus_guardrails.config import PiiConfig
from nexus_guardrails.engine import GuardrailsEngine
from nexus_guardrails.pii import mask_pii
from nexus_guardrails.pii_columns import classify_columns, mask_record, mask_records
from nexus_guardrails.policy import _raw_pii_present

CFG = PiiConfig()


def _rows(n: int) -> list[dict]:
    rng = random.Random(5)
    cities = ["Pune", "Austin", "Berlin", "Lyon"]
    return [
        {
            "id": i,
            "email": f"user{i % 50}@example.com",
            "phone": rng.choice(["415-555-0134", "N/A", "", "+44 20 7946 0958"]),
            "city": rng.choice(cities),
            "notes": rng.choice(["call me at 415-555-0199", "all good", "mail a@b.co"]),
            "created_at": "2024-03-1" + str(i % 9),
        }
        for i in range(n)
    ]


def test_memoised_mask_records_equals_row_by_row():
    rows = _rows(400)
    kinds = classify_columns(rows)
    expected = [mask_record(r, kinds, CFG) for r in rows]
    assert mask_records(rows, CFG)[0] == expected
    secret = mask_records(rows, CFG, token_secret="s3")[0]
    assert secret == [mask_record(r, kinds, CFG, "s3") for r in rows]


def test_memo_is_bounded(monkeypatch):
    monkeypatch.setattr(pii_columns, "_MEMO_ENTRIES", 10)
    rows = [{"notes": f"note {i}"} for i in range(100)]
    assert mask_records(rows, CFG)[0] == rows


def test_nested_values_are_masked_in_every_column_kind():
    rows = [
        {
            "order_id": {"order_details": {"email": "a@b.com"}},
            "updated_at": {"by": "sam@x.com"},
            "amount": [{"payer": "pay@x.com"}],
            "ref": ["sam@x.com"],
            "meta": {"order": {"customer": {"email": "c@d.org"}}},
        }
    ]
    masked = mask_records(rows, CFG)[0][0]
    assert "@" not in repr(masked)
    assert masked["meta"] == {"order": {"customer": {"email": "[EMAIL]"}}}


def test_placeholders_stay_but_secrets_are_always_masked():
    rows = [{"phone": v, "password": "N/A"} for v in ("N/A", "none", "415-555-0134", "-")]
    masked = mask_records(rows, CFG)[0]
    assert [m["phone"] for m in masked] == ["N/A", "none", "[PHONE]", "-"]
    assert all(m["password"] == "[SECRET]" for m in masked)


def test_policy_sees_international_numbers_and_emails():
    assert _raw_pii_present("reach me at +44 20 7946 0958")
    assert _raw_pii_present("x" * 50 + " jo@ex.com")
    assert not _raw_pii_present("the refund window is 30 days")


def test_evaluate_masks_the_query_like_mask_pii():
    engine = GuardrailsEngine(search_provider=lambda q, k: [])
    query = "my card 4111 1111 1111 1111 and mail a@b.co"
    response = engine.evaluate(query)
    assert response.masked_query == mask_pii(query, CFG)
    assert {f.message for f in response.findings if f.category == "pii"} == {
        "Detected email",
        "Detected credit_card",
    }
