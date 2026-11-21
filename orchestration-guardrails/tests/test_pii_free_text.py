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

"""Free-text phone numbers (open item O1) and the guards that keep ids and amounts intact."""

import pytest

from nexus_guardrails.config import PiiConfig
from nexus_guardrails.pii import mask_pii
from nexus_guardrails.pii_columns import mask_records

FREE_TEXT_PHONES = [
    ("my number is 5553334444", "5553334444"),
    ("call me at 555 333 4444", "555 333 4444"),
    ("+1-555-333-4444", "555-333-4444"),
    ("text me at 5553334444 tonight", "5553334444"),
    ("reach me on 9876543210", "9876543210"),
    ("his no. 9876543210", "9876543210"),
    ("Our office number is 2125550147.", "2125550147"),
    ("Spoke to the customer, 5553334444, about the refund", "5553334444"),
    ("numbers: 4155551234,5553334444", "4155551234"),
    ("numbers: 4155551234,5553334444", "5553334444"),
    ("tel#5553334444", "5553334444"),
]

NOT_PHONES = [
    "Order 5553334444 shipped",
    "id 5553334444",
    "amount 5553334444",
    "total: 5553334444",
    "$5553334444 was wired",
    "batch 1234567890",
    "2025011512",
    "order_id: 5553334444 | amount: 5553334444",
    "invoice INV-5553334444",
    "1700000000 seconds",
    "#5553334444",
    "price 1234567890,50",
]


@pytest.mark.parametrize(("text", "secret"), FREE_TEXT_PHONES)
def test_free_text_phone_numbers_are_masked(text, secret):
    masked = mask_pii(text, PiiConfig())
    assert secret not in masked
    assert "[PHONE]" in masked


@pytest.mark.parametrize("text", NOT_PHONES)
def test_ids_amounts_and_dates_stay(text):
    assert mask_pii(text, PiiConfig()) == text


def test_id_and_amount_columns_stay_while_phone_and_notes_are_masked():
    rows = [
        {
            "order_id": 5553334444,
            "amount": "5553334444",
            "phone": "5553334444",
            "notes": "my number is 5553334444",
        },
        {"order_id": 5553334445, "amount": "12.00", "phone": "5553334445", "notes": ""},
    ]
    masked, kinds = mask_records(rows, PiiConfig())
    assert kinds["order_id"] == "identifier" and kinds["amount"] == "numeric"
    assert masked[0]["order_id"] == 5553334444 and masked[0]["amount"] == "5553334444"
    assert masked[0]["phone"] == "[PHONE]"
    assert masked[0]["notes"] == "my number is [PHONE]"


def test_card_number_after_a_number_sign_cue_is_masked():
    masked = mask_pii("cc#4111111111111111", PiiConfig())
    assert "4111111111111111" not in masked and "[CREDIT_CARD]" in masked
