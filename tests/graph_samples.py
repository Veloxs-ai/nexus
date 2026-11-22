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

"""Labelled samples for the knowledge-graph extractors.

``HAND_LABELLED``: 40 enterprise-style passages written for these tests (email, meeting
notes, handbook, tickets, wiki pages, transcripts), each with every entity a careful
annotator marks: ``(name, type, extra surface forms in the passage)``. Job titles and roles
("Chief Risk Officer", "Head of Sales") are not entities. Masked text is
included (``[EMAIL]``, ``[PHONE]``): masked values are never entities.

``graph_samples_synthetic.synthetic_corpus`` and ``graph_samples_heldout.HELD_OUT`` hold the
other labelled sets.
"""

from __future__ import annotations

HAND_LABELLED: list[tuple[str, list[tuple[str, str, tuple[str, ...]]]]] = [
    (
        "Hi Priya,\nThanks for the update on the Falcon migration. Marcus Lee from Contoso Ltd "
        "will join the "
        "call on Thursday. Please send the revised SOW to [EMAIL] before then.\nRegards,\nDaniel",
        [
            ("Priya", "person", ()),
            ("Falcon", "project", ()),
            ("Marcus Lee", "person", ()),
            ("Contoso Ltd", "org", ()),
            ("Daniel", "person", ()),
        ],
    ),
    (
        "Meeting notes - Q3 planning\nAttendees: Ravi Kumar, Anita Desai, Tom Becker\nAction "
        "items:\n"
        "- Ravi to confirm the budget with Finance by Friday.\n- Anita to review the Atlas "
        "dashboard.",
        [
            ("Ravi Kumar", "person", ("Ravi",)),
            ("Anita Desai", "person", ("Anita",)),
            ("Tom Becker", "person", ()),
            ("Finance", "org", ()),
            ("Atlas", "product", ()),
        ],
    ),
    (
        "The Service Level Agreement (SLA) between Northwind Traders and Globex Corporation "
        "requires a first "
        "response within four hours. Breaches of the SLA are reported monthly to the Vendor "
        "Management Office.",
        [
            ("Service Level Agreement", "entity", ("SLA",)),
            ("Northwind Traders", "org", ()),
            ("Globex Corporation", "org", ()),
            ("Vendor Management Office", "org", ()),
        ],
    ),
    (
        "Ticket INC0012345: the customer Initech reports that invoices from March are missing in "
        "the "
        "billing portal. Assigned to Sara Ahmed (Tier 2). Related change: CHG-20417.",
        [
            ("INC0012345", "record", ()),
            ("Initech", "org", ()),
            ("Sara Ahmed", "person", ()),
            ("CHG-20417", "record", ()),
        ],
    ),
    (
        "Our Pune office moves to the Hinjewadi campus in October. Employees based in Mumbai keep "
        "their "
        "current desks. Contact Facilities at [PHONE] with questions.",
        [
            ("Pune", "place", ()),
            ("Hinjewadi", "place", ()),
            ("Mumbai", "place", ()),
            ("Facilities", "org", ()),
        ],
    ),
    (
        "Acme Corp signed a three-year renewal worth 1.2 million USD. The deal was led by Julia "
        "Roberts and "
        "approved by the Deal Desk. Acme Corp will move to the Enterprise plan on 1 January 2027.",
        [
            ("Acme Corp", "org", ()),
            ("Julia Roberts", "person", ()),
            ("Deal Desk", "org", ()),
            ("Enterprise", "product", ()),
        ],
    ),
    (
        "Dr. Elena Petrova, Chief Medical Officer at St. Mary's Hospital, presented the results "
        "of the "
        "telehealth pilot to the board. The pilot ran in Boston and Chicago.",
        [
            ("Elena Petrova", "person", ()),
            ("St. Mary's Hospital", "org", ()),
            ("Boston", "place", ()),
            ("Chicago", "place", ()),
        ],
    ),
    (
        "Release 4.2 of Nimbus Analytics adds row-level security and a new export API. Customers "
        "on the "
        "legacy Starter plan must upgrade before the end of support.",
        [("Nimbus Analytics", "product", ()), ("Starter", "product", ())],
    ),
    (
        "From the Employee Handbook: annual leave requests go to your line manager in Workday. "
        "Requests "
        "longer than ten days also need approval from Human Resources.",
        [
            ("Employee Handbook", "entity", ()),
            ("Workday", "product", ()),
            ("Human Resources", "org", ()),
        ],
    ),
    (
        "Call transcript CALL-3042\n[00:00:05] Agent: Thank you for calling Blue Sun support.\n"
        "[00:00:11] Customer (Wayne Foods): Our shipment to Hyderabad is late again.",
        [
            ("CALL-3042", "record", ()),
            ("Blue Sun", "org", ()),
            ("Wayne Foods", "org", ()),
            ("Hyderabad", "place", ()),
        ],
    ),
    (
        "The Data Protection Officer (DPO) reviews every request under the General Data Protection "
        "Regulation (GDPR). The DPO reports to the Chief Risk Officer.",
        [("General Data Protection Regulation", "entity", ("GDPR",))],
    ),
    (
        "Project Orion kicked off on Monday. Kenji Watanabe owns the integration with SAP, and "
        "Fatima "
        "Khan owns data migration from the old CRM.",
        [
            ("Orion", "project", ("Project Orion",)),
            ("Kenji Watanabe", "person", ()),
            ("SAP", "org", ()),
            ("Fatima Khan", "person", ()),
        ],
    ),
    (
        "Purchase order PO-7781 for 40 laptops from Dell Technologies was approved by "
        "Procurement. Delivery "
        "to the Bengaluru warehouse is expected in two weeks.",
        [
            ("PO-7781", "record", ()),
            ("Dell Technologies", "org", ()),
            ("Procurement", "org", ()),
            ("Bengaluru", "place", ()),
        ],
    ),
    (
        "Incident summary: on 12 May the payments gateway returned errors for 37 minutes. Root "
        "cause was an "
        "expired certificate on the Stripe webhook endpoint. Owner: Lucas Martin.",
        [("Stripe", "org", ()), ("Lucas Martin", "person", ())],
    ),
    (
        "WEEKLY STATUS REPORT\nThe Quartz team closed 14 stories. Mobile app crash rate fell to "
        "0.4%. "
        "Next week the team pairs with Cobalt Security on the penetration test.",
        [("Quartz", "project", ()), ("Cobalt Security", "org", ())],
    ),
    (
        "Mr. Rajesh Iyer from the State Bank of India confirmed the loan terms. The bank needs "
        "the audited "
        "statements from Deloitte by the end of the month.",
        [
            ("Rajesh Iyer", "person", ()),
            ("State Bank of India", "org", ()),
            ("Deloitte", "org", ()),
        ],
    ),
    (
        "Per the Travel Policy, economy class is required for flights under six hours. Exceptions "
        "need sign "
        "off from a Vice President and are reviewed by Internal Audit.",
        [("Travel Policy", "entity", ()), ("Internal Audit", "org", ())],
    ),
    (
        "Vendor onboarding checklist for Harbor Freight Solutions: tax form, bank letter, "
        "insurance "
        "certificate. Send documents to the procurement mailbox, not to individuals.",
        [("Harbor Freight Solutions", "org", ())],
    ),
    (
        "The quarterly business review with Tyrell Labs is scheduled in Singapore. Attendees from "
        "our side: "
        "Grace Lim and Oliver Brown. Topics: renewal pricing and the Willow roadmap.",
        [
            ("Tyrell Labs", "org", ()),
            ("Singapore", "place", ()),
            ("Grace Lim", "person", ()),
            ("Oliver Brown", "person", ()),
            ("Willow", "product", ()),
        ],
    ),
    (
        "Customer feedback survey results: 82% satisfied. Most complaints concern slow support "
        "replies and "
        "billing errors. Detailed comments are attached as an export.",
        [],
    ),
    (
        "Jira ticket NEX-482 tracks the login timeout bug reported by Umbrella Health. The fix "
        "ships in the "
        "next patch; QA sign-off by Meera Nair.",
        [("NEX-482", "record", ()), ("Umbrella Health", "org", ()), ("Meera Nair", "person", ())],
    ),
    (
        "The board approved the acquisition of Pied Piper by Hooli for an undisclosed amount. "
        "Closing is "
        "expected after regulatory approval in the European Union.",
        [("Pied Piper", "org", ()), ("Hooli", "org", ()), ("European Union", "org", ())],
    ),
    (
        "Note: all passwords must be rotated every 90 days. Contact the Service Desk if your "
        "account is "
        "locked. Do not share credentials over email or chat.",
        [("Service Desk", "org", ())],
    ),
    (
        "Minutes of the Safety Committee, 3 June\nPresent: Carlos Mendes (chair), Aisha Bello, "
        "Henry Ford\n"
        "The committee reviewed two near misses at the Surat plant.",
        [
            ("Safety Committee", "org", ()),
            ("Carlos Mendes", "person", ()),
            ("Aisha Bello", "person", ()),
            ("Henry Ford", "person", ()),
            ("Surat", "place", ()),
        ],
    ),
    (
        "Gringotts requested a copy of contract C-1044 and the amendment signed in 2025. Legal "
        "will send "
        "both through the secure portal.",
        [("Gringotts", "org", ()), ("C-1044", "record", ()), ("Legal", "org", ())],
    ),
    (
        "The new expense tool replaces the old spreadsheets. Receipts are scanned with the mobile "
        "app and "
        "matched automatically to card transactions.",
        [],
    ),
    (
        "Shipment SO-100231 left the Nagpur hub on Tuesday and arrives at Massive Dynamic in "
        "Delhi on "
        "Friday. Carrier: Blue Dart.",
        [
            ("SO-100231", "record", ()),
            ("Nagpur", "place", ()),
            ("Massive Dynamic", "org", ()),
            ("Delhi", "place", ()),
            ("Blue Dart", "org", ()),
        ],
    ),
    (
        "Welcome to the Engineering Wiki. This space documents the Vertex platform: services, "
        "runbooks and "
        "on-call rotations. Ask questions in the platform channel.",
        [("Engineering Wiki", "entity", ()), ("Vertex", "product", ())],
    ),
    (
        "Sophia Turner (Head of Sales, EMEA) will present the pipeline review. Forecast accuracy "
        "improved "
        "after the move to Salesforce.",
        [("Sophia Turner", "person", ()), ("EMEA", "place", ()), ("Salesforce", "org", ())],
    ),
    (
        "The Key Performance Indicator (KPI) for support is first contact resolution. The KPI "
        "target for "
        "this year is 75 percent, measured weekly.",
        [("Key Performance Indicator", "entity", ("KPI",))],
    ),
    (
        "Monarch Hotels and Oceanic Air launched a joint loyalty program. Members earn points at "
        "any "
        "Monarch Hotels property in Japan and Australia.",
        [
            ("Monarch Hotels", "org", ()),
            ("Oceanic Air", "org", ()),
            ("Japan", "place", ()),
            ("Australia", "place", ()),
        ],
    ),
    (
        "Please review the attached draft before Wednesday. The changes are marked in red and the "
        "open "
        "questions are listed at the end.",
        [],
    ),
    (
        "Ms. Hannah Schmidt joined Evergreen Energy GmbH as Head of Compliance. She was "
        "previously at "
        "Siemens in Munich.",
        [
            ("Hannah Schmidt", "person", ()),
            ("Evergreen Energy GmbH", "org", ()),
            ("Siemens", "org", ()),
            ("Munich", "place", ()),
        ],
    ),
    (
        "The Redwood Logistics account is managed by Kevin O'Brien. Open escalations: two damaged "
        "pallets "
        "and a missing proof of delivery.",
        [("Redwood Logistics", "org", ()), ("Kevin O'Brien", "person", ())],
    ),
    (
        "Annual security training is mandatory. Completion is tracked in the Learning Portal and "
        "reported "
        "to the Chief Information Security Officer every quarter.",
        [("Learning Portal", "product", ())],
    ),
    (
        "Stark Retail placed 3 orders this week: SO-100402, SO-100417 and SO-100433. All three "
        "ship from the "
        "Indore warehouse.",
        [
            ("Stark Retail", "org", ()),
            ("SO-100402", "record", ()),
            ("SO-100417", "record", ()),
            ("SO-100433", "record", ()),
            ("Indore", "place", ()),
        ],
    ),
    (
        "The University of Toronto and Veloxs signed a research agreement on retrieval evaluation. "
        "Professor Ahmed Hassan leads the work.",
        [
            ("University of Toronto", "org", ()),
            ("Veloxs", "org", ()),
            ("Ahmed Hassan", "person", ()),
        ],
    ),
    (
        "Reminder: the office is closed on Monday for the public holiday. The help desk remains "
        "reachable "
        "by phone for urgent issues.",
        [],
    ),
    (
        "In the Lumen Media case, the arbitrator ruled for the supplier. Counsel at Baker "
        "McKenzie advised "
        "against an appeal.",
        [("Lumen Media", "org", ()), ("Baker McKenzie", "org", ())],
    ),
    (
        "Our Customer Advisory Board met in London with representatives from Soylent, Cyberdyne "
        "and "
        "Vandelay Industries.",
        [
            ("Customer Advisory Board", "org", ()),
            ("London", "place", ()),
            ("Soylent", "org", ()),
            ("Cyberdyne", "org", ()),
            ("Vandelay Industries", "org", ()),
        ],
    ),
]
