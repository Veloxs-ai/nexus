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

"""Text entity typing (3.4.0): lexicons, context cues, document voting; keys and review."""

from __future__ import annotations

import ast
import pathlib
import sys

from nexus_processing import graph_lexicon
from nexus_processing.graph_keys import guess_primary_key, key_like_column
from nexus_processing.graph_resolve import resolve
from nexus_processing.graph_review import merge_proposals, promote_concepts
from nexus_processing.graph_structured import ForeignKey, detect_foreign_keys
from nexus_processing.graph_text import extract_mentions
from nexus_processing.graph_types import EntityRef

SRC = pathlib.Path(__file__).resolve().parents[1] / "src" / "nexus_processing"


def _types(text: str, *more: str) -> dict[str, str]:
    chunks = [("c0", text, "d0")] + [(f"c{i + 1}", t, f"d{i + 1}") for i, t in enumerate(more)]
    x = extract_mentions(chunks)
    return {e.name: e.type for e in x.entities if e.status == "active"}


def test_lexicons_are_large_and_lazy():
    assert len(graph_lexicon.given_names()) >= 2800
    assert len(graph_lexicon.places()) >= 3500
    assert graph_lexicon.given_names() is graph_lexicon.given_names()  # built once
    assert "priyanka" in graph_lexicon.GIVEN_NAMES and "rotterdam" in graph_lexicon.PLACES
    assert "reading" in graph_lexicon.ambiguous_places()


def test_new_modules_are_stdlib_only_and_small():
    allowed = set(sys.stdlib_module_names) | {"nexus", "nexus_processing", "nexus_retrieval"}
    names = ["graph_names", "graph_places", "graph_orgs", "graph_typing", "graph_keys"]
    names += ["graph_review", "cdc_ddl", "github_markdown"]
    for name in names:
        source = (SRC / f"{name}.py").read_text()
        assert source.count("\n") < 500, name
        for node in ast.walk(ast.parse(source)):
            if isinstance(node, ast.Import):
                roots = {a.name.split(".")[0] for a in node.names}
            elif isinstance(node, ast.ImportFrom) and node.level == 0:
                roots = {(node.module or "").split(".")[0]}
            else:
                continue
            assert roots <= allowed, (name, roots)


def test_people_places_and_orgs_by_lexicon_and_suffix():
    t = _types("Tomasz Wierzbicki met Olumide Adeyemi in Rotterdam and then flew to Queensland.")
    assert t["Tomasz Wierzbicki"] == "person" and t["Olumide Adeyemi"] == "person"
    assert t["Rotterdam"] == "place" and t["Queensland"] == "place"
    t = _types("We signed with Harborline Freight and Sunridge Textiles last week.")
    assert t["Harborline Freight"] == "org" and t["Sunridge Textiles"] == "org"


def test_model_numbers_are_products_not_partial_names():
    t = _types("The Zephyr X2 router and the Atlas 300 pallets shipped. Phase 2 starts soon.")
    assert t.get("Zephyr X2") == "product" and t.get("Atlas 300") == "product"
    assert "Zephyr" not in t and "Atlas" not in t and "Phase 2" not in t
    assert "Annual Report" in _types("See the Annual Report 2025 for details.")


def test_departments_at_sentence_start_and_mid_sentence():
    t = _types("Legal will review the contract. The invoice was approved by Finance yesterday.")
    assert t.get("Legal") == "org" and t.get("Finance") == "org"
    t = _types("HR will run the survey. Customer Success owns renewals.")
    assert t.get("HR") == "org" and t.get("Customer Success") == "org"
    t = _types("Sophia Turner (Head of Sales, EMEA) presented. Security is a priority.")
    assert "Sales" not in t and "Security" not in t


def test_context_cues():
    t = _types("The customer Initech reports late invoices. Kestrel Dynamics will start the "
               "Falcon migration after the Halcyon upgrade. Our Pune office moves to the "
               "Hinjewadi campus.")  # fmt: skip
    assert t["Initech"] == "org"
    assert t["Falcon"] == "project" and t["Halcyon"] == "product"
    assert t["Hinjewadi"] == "place" and t["Pune"] == "place"
    assert _types("Gringotts requested a copy of the contract.")["Gringotts"] == "org"
    assert _types("Project Orion slipped by a month.")["Project Orion"] == "project"
    # a project head word last wins over a given name first ("Orion" is a given name)
    assert _types("The Orion Initiative covers three regions.")["Orion Initiative"] == "project"
    assert _types("Grace Programme funding was approved.")["Grace Programme"] == "project"


def test_coordination_and_document_voting():
    t = _types("Representatives from Soylent, Cyberdyne and Vandelay Industries met in London.")
    assert t["Soylent"] == "org" and t["Cyberdyne"] == "org"
    t = _types("Bluepeak Energy asked for a quote, and Bluepeak wants delivery in March. "
               "Olivia Chen signs today; Olivia is travelling.")  # fmt: skip
    assert t["Bluepeak"] == "org" and t["Olivia"] == "person"


def test_untyped_names_take_their_type_from_other_documents():
    t = _types("We met Zorvex yesterday.", "The supplier Zorvex sent a revised quote.")
    assert t == {"Zorvex": "org"}


def test_guess_primary_key():
    rows = [{"order_no": i, "id": 100 + i, "customer_id": i % 3} for i in range(10)]
    assert guess_primary_key(["order_no", "id", "customer_id"], rows, table="orders") == "id"
    assert guess_primary_key(["order_no", "customer_id"], rows, table="orders") == "order_no"
    rows = [{"CustomerId": f"C-{i}", "name": f"n{i}"} for i in range(5)]
    assert guess_primary_key(["name", "CustomerId"], rows, table="customers") == "CustomerId"
    assert guess_primary_key(["name"], rows) is None  # unique but not named like a key
    rows = [{"id": 1}, {"id": 1}]
    assert guess_primary_key(["id"], rows) is None
    rows = [{"id": 1}, {"id": None}]
    assert guess_primary_key(["id"], rows) is None
    profile = {
        "rows": 1000,
        "columns": [
            {"name": "ticket_id", "distinct": 1000, "nulls": 0, "type": "text"},
            {"name": "account_id", "distinct": 40, "nulls": 0, "type": "text"},
        ],
    }
    assert guess_primary_key(profile["columns"], table="tickets", profile=profile) == "ticket_id"
    assert key_like_column("userId") and not key_like_column("name")


def test_foreign_keys_name_both_tables():
    profiles = {
        "customers": {"rows": 4, "columns": [
            {"name": "customer_id", "type": "text", "distinct": 4}]},
        "orders": {"rows": 6, "columns": [
            {"name": "id", "type": "integer", "distinct": 6},
            {"name": "customer_id", "type": "text", "distinct": 3}]},
    }  # fmt: skip
    samples = {
        "customers": [{"customer_id": f"C{i}"} for i in range(4)],
        "orders": [{"id": i, "customer_id": f"C{i % 3}"} for i in range(6)],
    }
    fks = detect_foreign_keys(profiles, samples, primary_keys={"customers": "customer_id"})
    fk = next(f for f in fks if f.column == "customer_id")
    assert (fk.table, fk.from_table, fk.to_table, fk.ref_column) == (
        "orders", "orders", "customers", "customer_id",
    )  # fmt: skip
    assert ForeignKey("a", "b", "c").table == ""  # 3.3.0 positional form still works


def test_merge_proposals_are_a_stable_list_with_reasons():
    entities = [
        EntityRef("atlas labs", "Atlas Labs", "org", "text"),
        EntityRef("atlas labs gmbh", "Atlas Labs GmbH", "org", "structured"),
        EntityRef("atlas labs inc", "Atlas Labs Inc", "org", "structured"),
    ]
    res = resolve(entities)
    assert len(res.proposal_reasons) == len(res.proposals)
    first = merge_proposals(res, entities)
    assert first == merge_proposals(resolve(entities), entities)  # stable
    by_source = {(p.source_key, p.target_key): p for p in first}
    assert len(by_source) == len(first)  # one row per pair
    assert {p.reason for p in first if p.source_key == "atlas labs"} == {"ambiguous"}
    assert first[0].score >= first[-1].score
    row = next(p for p in first if p.source_key == "atlas labs").as_dict()
    assert row["source"]["name"] == "Atlas Labs" and row["reason"] == "ambiguous"
    res = resolve(
        [EntityRef("acme inc", "Acme Inc", "org", "text"),
         EntityRef("acme ltd", "Acme Ltd", "org", "text")]
    )  # fmt: skip
    assert {p.reason for p in merge_proposals(res)} == {"legal_suffix"}


def test_concepts_need_two_documents_and_no_template_text():
    boiler = "Invoices are payable within thirty days of receipt by the customer."
    texts = [
        ("a1", f"Order 1 for Acme. {boiler} The renewal pricing was discussed.", "A"),
        ("b1", f"Order 2 for Initech. {boiler} Buyers questioned the renewal pricing again.", "B"),
        ("c1", f"Order 3 for Hooli. {boiler} The data retention policy applies.", "C"),
    ]
    x = extract_mentions(texts)
    candidates = {e.key for e in x.entities if e.type == "concept"}
    decision = promote_concepts(x, {k: t for k, t, _ in texts}, {k: d for k, _, d in texts})
    assert "renewal pricing" in decision.promoted
    assert any("thirty days" in k for k in decision.boilerplate & candidates)
    assert "data retention policy" in decision.rare
    active = {e.key for e in decision.apply(x).entities if e.status == "active"}
    assert "renewal pricing" in active and not decision.boilerplate & active
