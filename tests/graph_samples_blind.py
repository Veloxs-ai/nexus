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

"""Blind labelled passages for text entity typing (3.4.0).

Written before the 3.4.0 typing work started and never used to tune it: the numbers reported
for 3.4.0 come from this set untouched. Same shape as ``graph_samples.HAND_LABELLED``:
``(text, [(name, type, aliases), ...])``; gold type ``entity`` accepts any predicted type.
"""

from __future__ import annotations

BLIND: list[tuple[str, list[tuple[str, str, tuple[str, ...]]]]] = [
    (
        "Hi Rebecca,\nThe Lisbon office will host the partner summit with Northwind Traders "
        "in May. Please book rooms for Tomas Almeida and Hiroko Sato.\nRegards,\nDaniel",
        [
            ("Rebecca", "person", ()),
            ("Lisbon", "place", ()),
            ("Northwind Traders", "org", ()),
            ("Tomas Almeida", "person", ()),
            ("Hiroko Sato", "person", ()),
            ("Daniel", "person", ()),
        ],
    ),
    (
        "Legal will review the master services agreement with Fabrikam Inc. before Friday. "
        "Finance has already approved the payment schedule.",
        [("Legal", "org", ()), ("Fabrikam Inc.", "org", ()), ("Finance", "org", ())],
    ),
    (
        "The Zephyr X2 router shipped with firmware 4.1, which broke VLAN tagging for "
        "customers in Rotterdam. Support opened ticket SUP-30417.",
        [
            ("Zephyr X2", "product", ()),
            ("Rotterdam", "place", ()),
            ("Support", "org", ()),
            ("SUP-30417", "record", ()),
        ],
    ),
    (
        "Contoso Pharmaceuticals appointed Dr. Amara Okafor as head of clinical operations. "
        "She previously worked at Novacare Labs in Lagos.",
        [
            ("Contoso Pharmaceuticals", "org", ()),
            ("Amara Okafor", "person", ()),
            ("Novacare Labs", "org", ()),
            ("Lagos", "place", ()),
        ],
    ),
    (
        "Our warehouse in Monterrey ran out of the Atlas 300 pallets. Procurement placed "
        "purchase order PO-77120 with Vortex Packaging Ltd.",
        [
            ("Monterrey", "place", ()),
            ("Atlas 300", "product", ()),
            ("Procurement", "org", ()),
            ("PO-77120", "record", ()),
            ("Vortex Packaging Ltd", "org", ()),
        ],
    ),
    (
        "Meeting notes, 12 March\nAttendees: Sofia Marquez, Liam O'Brien, Priyanka Das\n"
        "Decision: move the data platform from Snowflake to Databricks by Q3.",
        [
            ("Sofia Marquez", "person", ()),
            ("Liam O'Brien", "person", ()),
            ("Priyanka Das", "person", ()),
            ("Snowflake", "product", ()),
            ("Databricks", "product", ()),
        ],
    ),
    (
        "The audit committee of Halcyon Bank flagged three exceptions in the Nairobi branch. "
        "Mwangi Kariuki will present the remediation plan.",
        [
            ("Halcyon Bank", "org", ()),
            ("Nairobi", "place", ()),
            ("Mwangi Kariuki", "person", ()),
        ],
    ),
    (
        "Customers on the Pro plan reported that the Lumen 5 tablet loses Wi-Fi after "
        "sleeping. Engineering in Krakow reproduced the bug.",
        [("Lumen 5", "product", ()), ("Engineering", "org", ()), ("Krakow", "place", ())],
    ),
    (
        "Alicia Fernandes from Bluepeak Energy asked for a revised quote. Bluepeak wants "
        "delivery to their plant in Porto Alegre, Brazil.",
        [
            ("Alicia Fernandes", "person", ()),
            ("Bluepeak Energy", "org", ("Bluepeak",)),
            ("Porto Alegre", "place", ()),
            ("Brazil", "place", ()),
        ],
    ),
    (
        "Incident INC-44871: payments to Stellar Mutual failed for two hours. Root cause was "
        "an expired certificate on the gateway in Frankfurt.",
        [
            ("INC-44871", "record", ()),
            ("Stellar Mutual", "org", ()),
            ("Frankfurt", "place", ()),
        ],
    ),
    (
        "Hello Kenji,\nCould you forward the Orion R7 spec sheet to Marta Kowalski at Tidewater "
        "Logistics? She is evaluating it for their Gdansk depot.\nThanks, Fatima",
        [
            ("Kenji", "person", ()),
            ("Orion R7", "product", ()),
            ("Marta Kowalski", "person", ()),
            ("Tidewater Logistics", "org", ()),
            ("Gdansk", "place", ()),
            ("Fatima", "person", ()),
        ],
    ),
    (
        "HR will run the annual engagement survey in October. Results go to the leadership "
        "team and to Gareth Lloyd, our chief people officer.",
        [("HR", "org", ()), ("Gareth Lloyd", "person", ())],
    ),
    (
        "Quarterly review: revenue from Westbrook Holdings grew 14 percent, driven by new "
        "stores in Manchester and Leeds.",
        [
            ("Westbrook Holdings", "org", ()),
            ("Manchester", "place", ()),
            ("Leeds", "place", ()),
        ],
    ),
    (
        "The contract between Pinecrest Medical Group and Quantix Software LLC renews "
        "automatically unless either party gives notice. Contact Sanjay Iyer for questions.",
        [
            ("Pinecrest Medical Group", "org", ()),
            ("Quantix Software LLC", "org", ()),
            ("Sanjay Iyer", "person", ()),
        ],
    ),
    (
        "Field engineers in Queensland replaced the compressor on unit HX-220. The Vega 9 "
        "controller logged a fault code before the failure.",
        [
            ("Queensland", "place", ()),
            ("HX-220", "record", ()),
            ("Vega 9", "product", ()),
        ],
    ),
    (
        "Marketing launched the spring campaign in Toronto and Vancouver. Chloe Bergstrom "
        "owns the budget; spend is tracked in HubSpot.",
        [
            ("Marketing", "org", ()),
            ("Toronto", "place", ()),
            ("Vancouver", "place", ()),
            ("Chloe Bergstrom", "person", ()),
            ("HubSpot", "product", ()),
        ],
    ),
    (
        "Ines Duarte joined Redline Motors as plant manager in Seville. Before that she led "
        "quality at Corvel Automotive.",
        [
            ("Ines Duarte", "person", ()),
            ("Redline Motors", "org", ()),
            ("Seville", "place", ()),
            ("Corvel Automotive", "org", ()),
        ],
    ),
    (
        "Security asked all staff to enable multi-factor authentication in Okta by Monday. "
        "Questions go to Arjun Mehta.",
        [("Security", "org", ()), ("Okta", "product", ()), ("Arjun Mehta", "person", ())],
    ),
    (
        "Shipment SH-90213 left Singapore on 3 June and is expected in Mombasa next week. "
        "The carrier is Meridian Shipping.",
        [
            ("SH-90213", "record", ()),
            ("Singapore", "place", ()),
            ("Mombasa", "place", ()),
            ("Meridian Shipping", "org", ()),
        ],
    ),
    (
        "Dear Ms. Whitaker,\nThank you for choosing Aurora Hotels. Your booking in Reykjavik "
        "is confirmed.\nKind regards,\nOliver Grant",
        [
            ("Whitaker", "person", ()),
            ("Aurora Hotels", "org", ()),
            ("Reykjavik", "place", ()),
            ("Oliver Grant", "person", ()),
        ],
    ),
    (
        "The Nimbus 12 server line is end of life. Customers such as Ridgeway Credit Union "
        "should move to the Nimbus 20 before December.",
        [
            ("Nimbus 12", "product", ()),
            ("Ridgeway Credit Union", "org", ()),
            ("Nimbus 20", "product", ()),
        ],
    ),
    (
        "Thanks to Yusuf Demir and Elif Arslan for closing the Ankara deal with Kestrel "
        "Aerospace. Sales will book it this quarter.",
        [
            ("Yusuf Demir", "person", ()),
            ("Elif Arslan", "person", ()),
            ("Ankara", "place", ()),
            ("Kestrel Aerospace", "org", ()),
            ("Sales", "org", ()),
        ],
    ),
    (
        "Operations moved the night shift from Dallas to Phoenix. Graham Whitfield signed off "
        "after checking staffing with Coastal Staffing Partners.",
        [
            ("Operations", "org", ()),
            ("Dallas", "place", ()),
            ("Phoenix", "place", ()),
            ("Graham Whitfield", "person", ()),
            ("Coastal Staffing Partners", "org", ()),
        ],
    ),
    (
        "Bug report from Lena Hoffmann: the export button in Jira fails for projects with "
        "more than 500 issues. Reproduced in Chrome and Firefox.",
        [
            ("Lena Hoffmann", "person", ()),
            ("Jira", "product", ()),
            ("Chrome", "product", ()),
            ("Firefox", "product", ()),
        ],
    ),
    (
        "Mr. Chukwuemeka Obi of Sahel Agritech visited the Accra site with two investors "
        "from Lionsgate Capital.",
        [
            ("Chukwuemeka Obi", "person", ()),
            ("Sahel Agritech", "org", ()),
            ("Accra", "place", ()),
            ("Lionsgate Capital", "org", ()),
        ],
    ),
]
