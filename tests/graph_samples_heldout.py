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

"""Held-out labelled passages for the knowledge-graph extractors (see graph_samples)."""

from __future__ import annotations

# Written after the extractor rules were frozen and never used to tune them: the honest
# precision/recall estimate (HAND_LABELLED was used during development).
HELD_OUT: list[tuple[str, list[tuple[str, str, tuple[str, ...]]]]] = [
    (
        "Hello team,\nThe Granite Systems renewal is blocked until Olivia Chen signs the order "
        "form. Olivia is "
        "travelling to Dubai this week, so expect a delay.\nThanks,\nMaya",
        [
            ("Granite Systems", "org", ()),
            ("Olivia Chen", "person", ("Olivia",)),
            ("Dubai", "place", ()),
            ("Maya", "person", ()),
        ],
    ),
    (
        "Change request CR-5521 updates the firewall rules for the Kolkata data centre. Approved "
        "by the "
        "Change Advisory Board on 4 April.",
        [("CR-5521", "record", ()), ("Kolkata", "place", ()), ("Change Advisory Board", "org", ())],
    ),
    (
        "Brightwater Foods Inc. disputes invoice INV-88213. Their controller, Peter Novak, says "
        "the unit "
        "price differs from the quote.",
        [
            ("Brightwater Foods Inc.", "org", ()),
            ("INV-88213", "record", ()),
            ("Peter Novak", "person", ()),
        ],
    ),
    (
        "Onboarding guide\nNew joiners get a laptop, a badge and access to Slack and Confluence "
        "on day one. "
        "Your buddy will walk you through the Engineering Handbook.",
        [
            ("Slack", "product", ()),
            ("Confluence", "product", ()),
            ("Engineering Handbook", "entity", ()),
        ],
    ),
    (
        "The Reserve Bank of India raised the repo rate by 25 basis points. Treasury expects "
        "funding costs to "
        "rise next quarter.",
        [("Reserve Bank of India", "org", ()), ("Treasury", "org", ())],
    ),
    (
        "Customer: Wonka Sweets\nIssue: duplicate charges on the March statement\nOwner: Ahmed "
        "Siddiqui\n"
        "Next step: refund the second charge and confirm by email.",
        [("Wonka Sweets", "org", ()), ("Ahmed Siddiqui", "person", ())],
    ),
    (
        "We migrated the search cluster from Elasticsearch to OpenSearch. Latency at the 95th "
        "percentile "
        "dropped from 480 ms to 210 ms.",
        [("Elasticsearch", "product", ()), ("OpenSearch", "product", ())],
    ),
    (
        "Isabella Rossi and Marco Bianchi from the Milan branch will audit the inventory at the "
        "Pune "
        "warehouse in July.",
        [
            ("Isabella Rossi", "person", ()),
            ("Marco Bianchi", "person", ()),
            ("Milan", "place", ()),
            ("Pune", "place", ()),
        ],
    ),
    (
        "The Information Security Policy applies to all contractors. Violations are reported to "
        "the "
        "Security Operations Center (SOC) within one hour.",
        [
            ("Information Security Policy", "entity", ()),
            ("Security Operations Center", "org", ("SOC",)),
        ],
    ),
    (
        "Q: Can I expense a taxi to the airport?\nA: Yes, if the flight leaves before 7 am. Keep "
        "the receipt "
        "and submit it within 30 days.",
        [],
    ),
    (
        "Silverline Robotics LLC shipped the replacement arm to Toyota Motor Corporation in "
        "Nagoya. The "
        "installation is planned with the plant engineers next week.",
        [
            ("Silverline Robotics LLC", "org", ()),
            ("Toyota Motor Corporation", "org", ()),
            ("Nagoya", "place", ()),
        ],
    ),
    (
        "Retrospective: the release slipped because the staging database ran out of disk. Action: "
        "add "
        "alerts on free space and a weekly capacity review.",
        [],
    ),
    (
        "Account manager Lena Fischer escalated the Cobalt Media complaint to Customer Success. A "
        "credit "
        "note will be issued.",
        [
            ("Lena Fischer", "person", ()),
            ("Cobalt Media", "org", ()),
            ("Customer Success", "org", ()),
        ],
    ),
    (
        "The Pioneer project replaces the payroll system for the Chennai and Jaipur offices. "
        "Go-live is "
        "planned for the first payroll run of the new financial year.",
        [("Pioneer", "project", ()), ("Chennai", "place", ()), ("Jaipur", "place", ())],
    ),
    (
        "Contract C-2107 with Sterling Packaging Ltd ends on 30 June. The notice period is 60 "
        "days, so "
        "Procurement must decide by 1 May.",
        [
            ("C-2107", "record", ()),
            ("Sterling Packaging Ltd", "org", ()),
            ("Procurement", "org", ()),
        ],
    ),
    (
        "Board meeting summary: the directors approved the dividend and re-appointed KPMG as "
        "auditors. "
        "Nina Petrov was elected chair.",
        [("KPMG", "org", ()), ("Nina Petrov", "person", ())],
    ),
    (
        "Support hours are 9 am to 6 pm on weekdays. Outside these hours, priority one incidents "
        "page the "
        "on-call engineer through the paging tool.",
        [],
    ),
    (
        "Mrs. Kavita Rao (Head of Procurement) will negotiate with Maple Textiles and Juniper "
        "Paper. Both "
        "suppliers are based in Gujarat.",
        [
            ("Kavita Rao", "person", ()),
            ("Maple Textiles", "org", ()),
            ("Juniper Paper", "org", ()),
            ("Gujarat", "place", ()),
        ],
    ),
    (
        "Demo script: open the Insights tab, filter by region, then export the chart. Mention "
        "that the "
        "export respects row-level permissions.",
        [("Insights", "product", ())],
    ),
    (
        "Aurora Clinics reported a data incident affecting 120 patient records. The Health "
        "Ministry was "
        "notified within 72 hours as required.",
        [("Aurora Clinics", "org", ()), ("Health Ministry", "org", ())],
    ),
]


# Written by an independent reviewer of 3.3.0 (support tickets, minutes, contracts, finance, HR,
# audit and product notes), never used to tune the rules.
INDEPENDENT: list[tuple[str, list[tuple[str, str, tuple[str, ...]]]]] = [
    (
        "Ticket INC0048812: Marisol Duarte from Brightwater Utilities reported that the billing "
        "portal in Lisbon "
        "times out after the Halcyon upgrade. Escalated to Tomasz Wierzbicki.",
        [
            ("INC0048812", "record", ()),
            ("Marisol Duarte", "person", ()),
            ("Brightwater Utilities", "org", ()),
            ("Lisbon", "place", ()),
            ("Halcyon", "product", ()),
            ("Tomasz Wierzbicki", "person", ()),
        ],
    ),
    (
        "Minutes of the steering call. Attendees: Kenji Watanabe (Northfield Capital), Amara "
        "Okafor, Lars Henriksen. "
        "Northfield Capital wants the Project Tidewater pilot moved from Oslo to Copenhagen.",
        [
            ("Kenji Watanabe", "person", ()),
            ("Northfield Capital", "org", ()),
            ("Amara Okafor", "person", ()),
            ("Lars Henriksen", "person", ()),
            ("Project Tidewater", "project", ("Tidewater",)),
            ("Oslo", "place", ()),
            ("Copenhagen", "place", ()),
        ],
    ),
    (
        "The Data Processing Addendum (DPA) between Velmora Health Inc. and Quillon Analytics "
        "GmbH takes effect on "
        "1 March. Under the DPA, Quillon Analytics may not move records outside Frankfurt.",
        [
            ("Data Processing Addendum", "concept", ("DPA",)),
            ("Velmora Health Inc.", "org", ()),
            ("Quillon Analytics GmbH", "org", ("Quillon Analytics",)),
            ("Frankfurt", "place", ()),
        ],
    ),
    (
        "Customer C-2291 (Harborline Freight) disputed invoice 88213. Rahul Mehta approved a "
        "credit of 4,200 EUR "
        "on Tuesday after speaking with Harborline Freight's controller, Ines Vogel.",
        [
            ("C-2291", "record", ()),
            ("Harborline Freight", "org", ()),
            ("Rahul Mehta", "person", ()),
            ("Ines Vogel", "person", ()),
        ],
    ),
    (
        "Call transcript summary: the agent confirmed that the Zephyr X2 router shipped from the "
        "Rotterdam warehouse. "
        "The caller, Beatriz Santos, asked for a replacement Zephyr X2 power adapter.",
        [
            ("Zephyr X2", "product", ()),
            ("Rotterdam", "place", ()),
            ("Beatriz Santos", "person", ()),
        ],
    ),
    (
        "Q3 review: Orchid Pharmaceuticals grew revenue 12% in Singapore and 7% in Jakarta. CFO "
        "Daniel Abernathy "
        "attributes the growth to the Lumina distribution deal with Pacifica Logistics.",
        [
            ("Orchid Pharmaceuticals", "org", ()),
            ("Singapore", "place", ()),
            ("Jakarta", "place", ()),
            ("Daniel Abernathy", "person", ()),
            ("Lumina", "product", ()),
            ("Pacifica Logistics", "org", ()),
        ],
    ),
    (
        "Security incident SEC-0412 was closed by Priyanka Iyer. The phishing emails impersonated "
        "Brightwater "
        "Utilities and targeted staff in Lisbon and Porto.",
        [
            ("SEC-0412", "record", ()),
            ("Priyanka Iyer", "person", ()),
            ("Brightwater Utilities", "org", ()),
            ("Lisbon", "place", ()),
            ("Porto", "place", ()),
        ],
    ),
    (
        "Please send the signed statement of work to Grace Holloway at Kestrel Dynamics Ltd "
        "before Friday. "
        "Kestrel Dynamics will start the Atlas migration once legal approves.",
        [
            ("Grace Holloway", "person", ()),
            ("Kestrel Dynamics Ltd", "org", ("Kestrel Dynamics",)),
            ("Atlas", "project", ()),
        ],
    ),
    (
        "Vendor onboarding checklist for Sunridge Textiles: bank details verified, W-9 received, "
        "contact person "
        "Olumide Adeyemi, warehouse in Manchester.",
        [
            ("Sunridge Textiles", "org", ()),
            ("Olumide Adeyemi", "person", ()),
            ("Manchester", "place", ()),
        ],
    ),
    (
        "The board of Meridian Bancorp met in Toronto. Chair Eleanor Whitfield asked management "
        "to pause the "
        "Polaris core banking replacement until Deloitte finishes its review.",
        [
            ("Meridian Bancorp", "org", ()),
            ("Toronto", "place", ()),
            ("Eleanor Whitfield", "person", ()),
            ("Polaris", "project", ()),
            ("Deloitte", "org", ()),
        ],
    ),
    (
        "Order 55120 for 300 units of the Aurora desk lamp was split between the Dallas and "
        "Phoenix stores. "
        "Store manager Carlos Ruiz flagged a shortfall in Phoenix.",
        [
            ("Aurora", "product", ()),
            ("Dallas", "place", ()),
            ("Phoenix", "place", ()),
            ("Carlos Ruiz", "person", ()),
        ],
    ),
    (
        "Renewal notice: the Service Level Agreement (SLA) with Brightwater Utilities expires in "
        "June. "
        "The SLA guarantees four-hour response in Lisbon. Contact: Marisol Duarte.",
        [
            ("Service Level Agreement", "concept", ("SLA",)),
            ("Brightwater Utilities", "org", ()),
            ("Lisbon", "place", ()),
            ("Marisol Duarte", "person", ()),
        ],
    ),
    (
        "HR note: Yusuf Demir transfers from the Istanbul office to Berlin on 1 April and will "
        "report to Hannah Fischer.",
        [
            ("Yusuf Demir", "person", ()),
            ("Istanbul", "place", ()),
            ("Berlin", "place", ()),
            ("Hannah Fischer", "person", ()),
        ],
    ),
    (
        "Audit finding: Glenmore Insurance stored claim photos in an unencrypted bucket. "
        "Remediation owner: "
        "Siobhan Kelly. Due date: 30 May.",
        [("Glenmore Insurance", "org", ()), ("Siobhan Kelly", "person", ())],
    ),
    (
        "Weekly update from the Nimbus team: Arjun Patel fixed the export bug, and Chloe Martin "
        "started the "
        "Nimbus mobile beta with testers in Melbourne and Sydney.",
        [
            ("Nimbus", "product", ()),
            ("Arjun Patel", "person", ()),
            ("Chloe Martin", "person", ()),
            ("Melbourne", "place", ()),
            ("Sydney", "place", ()),
        ],
    ),
]
