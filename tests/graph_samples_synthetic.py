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

"""Synthetic labelled corpus for the knowledge-graph extractors.

``synthetic_corpus(seed)``: documents and tables shaped like Nexora's RAG evaluation fixture
(contracts, tickets, call transcripts, orders, customers), with gold entities and the
documents each one appears in, computed from the hidden rows.
"""

from __future__ import annotations

import random
import re
from typing import Any

_CUSTOMERS = (
    "Acme Corp",
    "Globex",
    "Initech",
    "Umbrella Health",
    "Stark Retail",
    "Wayne Foods",
    "Hooli",
    "Vandelay",
    "Soylent",
    "Tyrell Labs",
    "Cyberdyne",
    "Wonka Sweets",
    "Pied Piper",
    "Massive Dynamic",
)
_ADJ = (
    "Northwind",
    "Bluepeak",
    "Silverline",
    "Redwood",
    "Granite",
    "Evergreen",
    "Brightwater",
    "Ironclad",
)
_NOUN = ("Logistics", "Supplies", "Analytics", "Systems", "Foods", "Textiles", "Energy", "Robotics")
_SUFFIX = ("Ltd", "Inc", "GmbH", "LLC", "Co")
_THEMES = ("late delivery", "billing errors", "damaged packaging", "slow support replies")
_FILLER = (
    "Invoices are payable within thirty days of receipt.",
    "Neither party is liable for delays caused by events beyond its reasonable control.",
    "Changes take effect only when approved by the responsible owner.",
    "Records are kept according to the records schedule.",
)
PLANTED = "Orion Retail"


def synthetic_corpus(
    seed: int = 7, contracts: int = 30, tickets: int = 60, calls: int = 10
) -> dict[str, Any]:
    """Documents (``(chunk_key, text, doc)``), tables and gold ``(name, type, docs)``."""
    rng = random.Random(seed)
    # distinct (name, sector) pairs: companies differing only by legal suffix are one entity
    pairs = rng.sample([(a, b) for a in _ADJ for b in _NOUN], contracts)
    vendors = [f"{a} {b} {rng.choice(_SUFFIX)}" for a, b in pairs]
    texts: list[tuple[str, str, str]] = []
    for i, vendor in enumerate(vendors):
        doc = f"contract_C-{1000 + i}"
        texts.append(
            (
                f"{doc}#0",
                f"Section: Contract C-{1000 + i} with {vendor} > Parties\nContract C-{1000 + i} "
                f"between {vendor} (vendor) and Veloxs Holdings (customer). " + rng.choice(_FILLER),
                doc,
            )
        )
        texts.append(
            (
                f"{doc}#1",
                f"Section: Contract C-{1000 + i} > Term\nAuto-renew: no. " + rng.choice(_FILLER),
                doc,
            )
        )
    planted = set(rng.sample(range(tickets), tickets // 8))
    ticket_rows = []
    for i in range(tickets):
        customer = PLANTED if i in planted else rng.choice(_CUSTOMERS)
        vendor = rng.choice(vendors)
        doc = f"ticket_T-{2000 + i}"
        ticket_rows.append(
            {
                "ticket_id": f"T-{2000 + i}",
                "customer": customer,
                "vendor": vendor,
                "priority": rng.choice(("P1", "P2", "P3")),
                "status": rng.choice(("open", "closed")),
            }
        )
        texts.append(
            (
                f"{doc}#0",
                f"Ticket T-{2000 + i} opened by {customer}. Priority: P2. The issue concerns a "
                f"product supplied by {vendor}. The customer reports {rng.choice(_THEMES)}.",
                doc,
            )
        )
    for i in range(calls):
        customer = PLANTED if i % 4 == 0 else rng.choice(_CUSTOMERS)
        doc = f"call_CALL-{3000 + i}"
        lines = [
            f"[00:00:{j:02d}] Customer ({customer}): We are unhappy about {rng.choice(_THEMES)}."
            if j % 2
            else f"[00:00:{j:02d}] Agent: I understand. " + rng.choice(_FILLER)
            for j in range(8)
        ]
        texts.append((f"{doc}#0", "\n".join(lines), doc))
    customers = [
        {
            "customer_id": f"CU-{100 + i}",
            "name": name,
            "segment": rng.choice(("SMB", "Enterprise")),
            "country": rng.choice(("India", "Germany", "Japan")),
        }
        for i, name in enumerate((*_CUSTOMERS, PLANTED))
    ]
    orders = [
        {
            "id": i + 1,
            "order_no": f"SO-{100000 + i}",
            "customer": rng.choice(customers)["name"],
            "region": rng.choice(("North", "South")),
            "amount": round(rng.uniform(20, 500), 2),
        }
        for i in range(600)
    ]
    doc_text: dict[str, str] = {}
    for _, text, doc in texts:
        doc_text[doc] = doc_text.get(doc, "") + "\n" + text
    gold: dict[str, tuple[str, str, set[str]]] = {}

    def add(name: str, etype: str, docs: set[str]) -> None:
        old = gold.get(name)
        gold[name] = (name, etype, (old[2] if old else set()) | docs)

    for name in (*_CUSTOMERS, PLANTED, "Veloxs Holdings", *vendors):
        pat = re.compile(r"(?<![\w-])" + re.escape(name) + r"(?![\w-])")
        add(name, "org", {d for d, t in doc_text.items() if pat.search(t)})
    for ident in set(re.findall(r"\b(?:C|T|CALL)-\d+\b", "\n".join(doc_text.values()))):
        add(
            ident,
            "record",
            {d for d, t in doc_text.items() if re.search(rf"(?<![\w-]){ident}(?![\w-])", t)},
        )
    for country in ("India", "Germany", "Japan"):
        add(country, "place", {"customers"})
    for row in orders:
        add(row["customer"], "org", {"orders"})
    for region in ("North", "South"):  # sales territories: place entities
        add(region, "place", {"orders"})
    return {
        "texts": texts,
        "customers": customers,
        "orders": orders,
        "tickets": ticket_rows,
        "gold": list(gold.values()),
        "planted": PLANTED,
    }
