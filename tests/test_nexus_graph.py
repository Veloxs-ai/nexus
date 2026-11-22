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

"""The ``nexus.graph`` facade end to end, and extraction quality on the labelled samples."""

from __future__ import annotations

import ast
import pathlib
import sys
import time

from graph_samples import HAND_LABELLED
from graph_samples_heldout import HELD_OUT, INDEPENDENT
from graph_samples_synthetic import synthetic_corpus

import nexus.graph as graph
from nexus.graph import (
    CSRGraph,
    ForeignKey,
    IncrementalGraph,
    TableInput,
    ego_subgraph,
    entity_id,
    extract_graph,
    leiden,
    pagerank,
)
from nexus.graph_eval import GoldEntity, score_extraction

ROOT = pathlib.Path(__file__).resolve().parents[1]
GRAPH_MODULES = [
    *sorted((ROOT / "data-processing-enrichment/src/nexus_processing").glob("graph_*.py")),
    *sorted((ROOT / "embedding-retrieval-intelligence/src/nexus_retrieval").glob("graph_*.py")),
    ROOT / "src/nexus/graph.py",
    ROOT / "src/nexus/graph_eval.py",
]


def test_facade_exports_everything_it_lists():
    for name in graph.__all__:
        assert hasattr(graph, name), name


def test_graph_modules_use_the_standard_library_only_and_stay_small():
    allowed = set(sys.stdlib_module_names) | {"nexus", "nexus_processing", "nexus_retrieval"}
    for path in GRAPH_MODULES:
        source = path.read_text()
        assert source.count("\n") < 500, path.name
        for node in ast.walk(ast.parse(source)):
            if isinstance(node, ast.Import):
                roots = [a.name.split(".")[0] for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.level == 0:
                roots = [(node.module or "").split(".")[0]]
            else:
                continue
            assert set(roots) <= allowed, (path.name, roots)


def _labelled(samples):
    texts, gold = [], {}
    for i, (text, entities) in enumerate(samples):
        texts.append((f"p{i}", text, f"p{i}"))
        for name, etype, aliases in entities:
            docs = set(gold[name].documents) if name in gold else set()
            gold[name] = GoldEntity(name, etype, frozenset(docs | {f"p{i}"}), tuple(aliases))
    return texts, list(gold.values())


def test_quality_on_hand_labelled_passages():
    texts, gold = _labelled(HAND_LABELLED)
    report = score_extraction(extract_graph(texts=texts), gold)
    assert report["entity_precision"] >= 0.9, report["false_positives"]
    assert report["mention_recall"] >= 0.95


def test_quality_on_held_out_passages():
    texts, gold = _labelled(HELD_OUT)
    report = score_extraction(extract_graph(texts=texts), gold)
    assert report["entity_precision"] >= 0.85, report["false_positives"]
    assert report["mention_recall"] >= 0.9


def test_quality_on_independent_passages():
    texts, gold = _labelled(INDEPENDENT)
    report = score_extraction(extract_graph(texts=texts), gold)
    assert report["entity_precision"] >= 0.9, report["false_positives"]
    assert report["mention_recall"] >= 0.95


def _synthetic():
    corpus = synthetic_corpus()
    customers = [(f"customers:{r['customer_id']}", r) for r in corpus["customers"]]
    orders = [(f"orders:{r['id']}", r) for r in corpus["orders"]]
    tables = [
        TableInput("customers", customers, primary_key="customer_id"),
        TableInput(
            "orders",
            orders,
            primary_key="id",
            foreign_keys=(ForeignKey("customer", "customers", "name"),),
        ),
    ]
    documents = {ck: doc for ck, _, doc in corpus["texts"]}
    documents.update({ck: "customers" for ck, _ in customers})
    documents.update({ck: "orders" for ck, _ in orders})
    gold = [GoldEntity(n, t, frozenset(d)) for n, t, d in corpus["gold"]]
    return corpus, tables, documents, gold


def test_quality_on_synthetic_fixture_with_tables():
    corpus, tables, documents, gold = _synthetic()
    x = extract_graph(texts=corpus["texts"], tables=tables)
    report = score_extraction(x, gold, documents=documents)
    assert report["entity_precision"] >= 0.95, report["false_positives"]
    assert report["mention_recall"] >= 0.98
    assert report["per_entity_recall"][corpus["planted"]] == 1.0  # "everything about Orion Retail"
    assert report["typing_accuracy"] >= 0.95
    planted = next(e for e in x.entities if e.name == corpus["planted"])
    assert planted.type == "org" and planted.origin == "structured"
    # the planted customer's pk alias and its orders (foreign key by name)
    assert any(a.alias == "CU-114" and a.entity_key == planted.key for a in x.aliases)
    fk = [m for m in x.mentions if m.method == "fk" and m.entity_key == planted.key]
    assert fk and all(documents[m.chunk_key] == "orders" for m in fk)


def test_extract_graph_resolves_text_names_to_structured_entities():
    customers = [("c:1", {"id": "CU-1", "name": "Acme Corp", "country": "India"})]
    texts = [
        ("t1", "ACME Corp. renewed. Ticket CU-1 refers to it.", "d1"),
        ("t2", "Acme Corporation called about [EMAIL].", "d2"),
    ]
    x = extract_graph(texts=texts, tables=[TableInput("customers", customers, primary_key="id")])
    refs = {(m.chunk_key, m.entity_type, m.entity_key) for m in x.mentions}
    assert ("t1", "org", "acme corp") in refs and ("t2", "org", "acme corp") in refs
    assert ("t1", "org", "acme corp") in {
        (m.chunk_key, m.entity_type, m.entity_key) for m in x.mentions if m.surface == "CU-1"
    }  # the pk resolves through the gazetteer
    assert not any("EMAIL" in m.surface for m in x.mentions)
    assert x.stats["auto_merges"] == 0


def test_masked_columns_never_become_entities():
    rows = [
        (f"r{i}", {"owner": f"Person {i % 5}", "email": "[EMAIL]", "phone": "[PHONE]"})
        for i in range(50)
    ]
    x = extract_graph(tables=[TableInput("leads", rows, column_kinds={"owner": "person_name"})])
    assert x.entities == ()  # owner is classified as personal data; email/phone are masked


def test_incremental_build_matches_a_full_build():
    corpus = synthetic_corpus(seed=3, contracts=8, tickets=20, calls=4)
    texts = corpus["texts"]
    full = IncrementalGraph()
    full.add(extract_graph(texts=texts, resolve_entities=False))
    inc = IncrementalGraph()
    for i in range(0, len(texts), 7):
        inc.add(extract_graph(texts=texts[i : i + 7], resolve_entities=False))
    for ref in [e.ref for e in full.entities() if e.type != "concept"]:
        assert inc.mention_count(ref) == full.mention_count(ref), ref
    removed = [ck for ck, _, doc in texts if doc.startswith("ticket_")]
    inc.remove_chunks(removed)
    assert all(not ck.startswith("ticket_") for e in inc.entities() for ck in inc.chunks_of(e.ref))


def test_communities_rank_and_ego_on_extracted_graph():
    corpus, tables, documents, _ = _synthetic()
    g = IncrementalGraph()
    g.add(extract_graph(texts=corpus["texts"], tables=tables), documents=documents)
    nodes, edges = g.edges(min_evidence=1)
    csr = CSRGraph.from_edges(len(nodes), edges)
    levels = leiden(csr)
    assert len(levels[-1]) == len(nodes) and len(set(levels[-1])) > 1
    pr = pagerank(csr)
    planted = nodes.index(("org", "orion retail"))
    neighbours = {v: list(zip(*csr.neighbours(v), strict=True)) for v in range(csr.n)}
    sel = ego_subgraph(planted, neighbours, hops=2, limit=25, node_weight=dict(enumerate(pr)))
    assert sel.nodes[0] == planted and len(sel.nodes) <= 25
    assert entity_id("ws", *nodes[planted]) == entity_id("ws", "org", "orion retail")


def test_throughput_smoke():
    corpus = synthetic_corpus(seed=5, contracts=30, tickets=200, calls=20)
    texts = corpus["texts"] * 4
    start = time.perf_counter()
    extract_graph(texts=texts)
    elapsed = time.perf_counter() - start
    assert elapsed < 5.0  # about 0.1 s on a laptop; generous for slow CI machines


def test_score_extraction_counts_aliases_and_candidates():
    x = extract_graph(
        texts=[
            ("c", "The Service Level Agreement (SLA) applies. Billing errors and billing errors.")
        ]
    )
    gold = [GoldEntity("Service Level Agreement", "entity", frozenset({"c"}), ("SLA",))]
    report = score_extraction(x, gold)
    assert report["entity_precision"] == 1.0 and report["mention_recall"] == 1.0
    assert report["active_entities"] == 1  # noun-phrase candidates are not scored
    empty = score_extraction(extract_graph(), [])
    assert empty["entity_precision"] == 1.0 and empty["mention_recall"] == 1.0
