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

"""Context-aware number detectors and column-aware record masking."""

import pytest

from nexus_guardrails.config import PiiConfig
from nexus_guardrails.engine import GuardrailsEngine
from nexus_guardrails.pii import mask_pii
from nexus_guardrails.pii_columns import classify_columns, mask_records

# Real PII: every secret must be gone after masking (recall must stay 100%).
PII_GOLDEN = [
    ("Email jane.doe@example.com today", "jane.doe@example.com"),
    ("ssn 123-45-6789 on file", "123-45-6789"),
    ("call 415-555-0100 now", "415-555-0100"),
    ("phone: (415) 555-0100", "555-0100"),
    ("Phone 415.555.0100", "415.555.0100"),
    ("tel 415 555 0100", "415 555 0100"),
    ("call +91 98765 43210, thanks", "98765 43210"),
    ("+1 415-555-0100 is my cell", "415-555-0100"),
    ("+44 20 7946 0958 office", "7946 0958"),
    ("mobile: 9876543210", "9876543210"),
    ("call me at 4155550100", "4155550100"),
    ("whatsapp 9876543210 please", "9876543210"),
    ("card 4111 1111 1111 1111 exp 12/27", "4111 1111 1111 1111"),
    ("visa 4111-1111-1111-1111", "4111-1111-1111-1111"),
    ("card number 4111111111111111", "4111111111111111"),
    ("paid with 5500005555555559", "5500005555555559"),
    ("amex 378282246310005", "378282246310005"),
    ("key sk-proj-abcdefghijklmnop1234 used", "sk-proj-abcdefghijklmnop1234"),
    ("token eyJhbGciOi.eyJzdWIiOi.SflKxwRJSM", "eyJhbGciOi.eyJzdWIiOi.SflKxwRJSM"),
    ("AKIAIOSFODNN7EXAMPLE leaked", "AKIAIOSFODNN7EXAMPLE"),
    ("contact: 415-555-0199 | email: a@b.io", "415-555-0199"),
]

# Data values that only look like phone numbers or cards: must survive unchanged.
VALUES_GOLDEN = [
    "created_at: 1700000000",
    "Order 4155551234 shipped",
    "total 1234567890.50 USD",
    "ORD-555-123-4567",
    "order_id: 9876543210",
    "invoice INV-2025-000123",
    "date 2025-01-15",
    "event_ts: 1700000000123",
    "amount: 9876543210.00",
    "account_no: 1000234567",
    "order_id: 4539578763621486",
    "build 20250115123045",
]


@pytest.mark.parametrize(("text", "secret"), PII_GOLDEN)
def test_real_pii_is_still_masked(text, secret):
    assert secret not in mask_pii(text, PiiConfig())


@pytest.mark.parametrize("text", VALUES_GOLDEN)
def test_ids_timestamps_and_amounts_are_not_masked(text):
    assert mask_pii(text, PiiConfig()) == text


ROWS = [
    {
        "order_id": "4155551234",
        "account_no": 1000234567,
        "amount": "9876543210.00",
        "created_at": 1700000000,
        "email": "jane@example.com",
        "phone": "9876543210",
        "card_number": "4111111111111111",
        "card_type": "visa",
        "notes": "call 415-555-0100 about order 4155551234",
    },
    {
        "order_id": "4155551235",
        "account_no": 1000234568,
        "amount": "12.50",
        "created_at": 1700000100,
        "email": "joe@example.com",
        "phone": "+1 415 555 0101",
        "card_number": "5500005555555559",
        "card_type": "mastercard",
        "notes": "",
    },
]


def test_columns_are_classified_once_by_name_and_values():
    kinds = classify_columns(ROWS)
    assert kinds == {
        "order_id": "identifier",
        "account_no": "identifier",
        "amount": "numeric",
        "created_at": "timestamp",
        "email": "email",
        "phone": "phone",
        "card_number": "credit_card",
        "card_type": "text",
        "notes": "text",
    }


def test_records_keep_ids_amounts_and_times_and_mask_pii_columns():
    masked, _ = mask_records(ROWS, PiiConfig())
    first = masked[0]
    assert first["order_id"] == "4155551234"
    assert first["account_no"] == 1000234567
    assert first["amount"] == "9876543210.00"
    assert first["created_at"] == 1700000000
    assert first["email"] == "[EMAIL]" and first["phone"] == "[PHONE]"
    assert first["card_number"] == "[CREDIT_CARD]" and first["card_type"] == "visa"
    assert first["notes"] == "call [PHONE] about order 4155551234"
    # group-by / equality on the identifier still see distinct values
    assert len({r["order_id"] for r in masked}) == 2


def test_value_detected_pii_columns_without_telling_names():
    rows = [{"contact": f"user{i}@corp.example", "ref": f"A-{i}"} for i in range(5)]
    kinds = classify_columns(rows)
    assert kinds["contact"] == "email" and kinds["ref"] == "identifier"


def test_prose_in_an_identifier_named_column_is_still_masked():
    rows = [{"reference": "please call me at 415-555-0100 tomorrow morning, thanks"}] * 3
    masked, kinds = mask_records(rows, PiiConfig())
    assert kinds["reference"] == "text" and "[PHONE]" in masked[0]["reference"]


def test_token_secret_gives_deterministic_groupable_tokens():
    rows = [{"email": "a@x.io"}, {"email": "A@x.io "}, {"email": "b@x.io"}]
    masked, _ = mask_records(rows, PiiConfig(), token_secret="tenant-secret")
    assert masked[0]["email"] == masked[1]["email"] != masked[2]["email"]
    assert masked[0]["email"].startswith("[EMAIL:") and "a@x.io" not in masked[0]["email"]


def test_nested_documents_are_masked_by_key():
    rows = [
        {
            "_id": "o1",
            "customer": {"email": "c@x.io", "id": "9876543210"},
            "lines": [{"sku": "4155551234"}],
        }
    ]
    masked = GuardrailsEngine().mask_records(rows)
    assert masked[0]["customer"] == {"email": "[EMAIL]", "id": "9876543210"}
    assert masked[0]["lines"] == [{"sku": "4155551234"}]


def test_disabled_masking_returns_rows_unchanged():
    masked, _ = mask_records(ROWS, PiiConfig(enabled=False))
    assert masked == ROWS


def test_secrets_and_emails_inside_id_columns_are_still_masked():
    rows = [
        {"code": "AKIA" + "B" * 16, "user_ref": "u-1", "order_id": 5553334444},
        {"code": "C-2", "user_ref": "bob@example.com", "order_id": 5553334445},
        {"code": "C-3", "user_ref": "u-3", "order_id": 5553334446},
    ]
    masked, kinds = mask_records(rows, PiiConfig())
    assert kinds["code"] == "identifier" and kinds["user_ref"] == "identifier"
    assert masked[0]["code"] == "[API_KEY]" and masked[1]["code"] == "C-2"
    assert masked[1]["user_ref"] == "[EMAIL]" and masked[0]["user_ref"] == "u-1"
    assert masked[0]["order_id"] == 5553334444


def test_contact_columns_of_bare_dialable_numbers_are_phones():
    rows = [{"contact": "5553334444", "emergency_contact": 9876543210, "contact_count": 3}]
    masked, kinds = mask_records(rows, PiiConfig())
    assert kinds["contact"] == "phone" and kinds["emergency_contact"] == "phone"
    assert masked[0]["contact"] == "[PHONE]" and masked[0]["emergency_contact"] == "[PHONE]"
    assert masked[0]["contact_count"] == 3
