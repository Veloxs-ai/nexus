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

from __future__ import annotations

import uuid

from nexus_processing.graph_resolve import (
    AliasIndex,
    acronym,
    apply_resolution,
    blocking_keys,
    normalise_name,
    org_base,
    resolve,
    similarity,
)
from nexus_processing.graph_types import (
    Alias,
    EntityRef,
    GraphExtraction,
    Mention,
    RelationRef,
    entity_id,
    merge_extractions,
    relation_id,
)


def test_normalise_name_rules():
    assert normalise_name("Acme Corp") == "acme corp"
    assert normalise_name("Acme Corp.", entity_type="org") == "acme corp"
    assert normalise_name("ACME Corporation", entity_type="org") == "acme corp"
    assert normalise_name("The Acme Company Limited", entity_type="org") == "acme co ltd"
    assert normalise_name("Atlas Labs GmbH", entity_type="org") != normalise_name(
        "Atlas Labs Inc", entity_type="org"
    )
    assert org_base("acme corp") == "acme" and org_base("acme") == "acme"
    assert (
        normalise_name("Tata Consultancy Services Private Limited", entity_type="org")
        == "tata consultancy services pvt ltd"
    )
    assert normalise_name("Johnson & Johnson", entity_type="org") == "johnson and johnson"
    assert normalise_name("The Ltd", entity_type="org") == "ltd"  # never empty when words are left
    assert normalise_name("Kumar, Ravi", entity_type="person") == normalise_name(
        "Ravi Kumar", entity_type="person"
    )
    assert normalise_name("Dr. Ravi Kumar", entity_type="person") == "kumar ravi"
    assert normalise_name("Zürich Café") == "zurich cafe"
    assert normalise_name("ＡＣＭＥ") == "acme"  # NFKC full-width
    assert normalise_name("C-1014") == "c 1014"
    assert normalise_name("  ...  ") == ""


def test_acronym_similarity_and_blocking():
    assert acronym("service level agreement") == "sla"
    assert acronym("bank of india") == "bi"
    assert acronym("acme") == ""
    assert similarity("acme", "acme") == 1.0
    assert similarity("northwind logistic", "northwind logistics") > 0.85
    assert similarity("acme", "globex") < 0.2
    assert blocking_keys("service level agreement") == ["service level agreement", "sla"]


def test_ids_are_deterministic_and_relations_symmetric():
    a = entity_id("ws1", "org", "acme")
    assert a == entity_id("ws1", "org", "acme") and uuid.UUID(a)
    assert a != entity_id("ws2", "org", "acme") and a != entity_id("ws1", "person", "acme")
    b = entity_id("ws1", "org", "globex")
    assert relation_id("ws1", a, b, "co_mentioned") == relation_id("ws1", b, a, "co_mentioned")
    assert relation_id("ws1", a, b, "customer") != relation_id("ws1", b, a, "customer")


def _e(key, etype="entity", origin="text", name=None):
    return EntityRef(key, name or key.title(), etype, origin)


def test_generic_type_upgrades_to_the_specific_entity():
    res = resolve([_e("globex"), _e("globex", "org", "structured")])
    assert res.mapping[("entity", "globex")] == ("org", "globex")
    assert res.mapping[("org", "globex")] == ("org", "globex")
    assert res.stats["type_upgrades"] == 1


def test_known_alias_maps_to_existing_entity():
    index = AliasIndex.from_rows(
        [("cu 100", "acme", "org", "Acme Corp"), ("acme", "acme", "org", "Acme Corp")]
    )
    assert len(index) == 1 and index.lookup("cu 100") == [("acme", "org", "Acme Corp")]
    res = resolve([_e("cu 100", "record")], index)
    assert res.mapping[("record", "cu 100")] == (
        "record",
        "cu 100",
    )  # record vs org: not compatible
    res = resolve([_e("cu 100")], index)
    assert res.mapping[("entity", "cu 100")] == ("org", "acme")
    assert any(a.alias_key == "cu 100" and a.entity_key == "acme" for a in res.new_aliases)


def test_fuzzy_merge_text_into_structured_and_never_person_into_org():
    res = resolve(
        [
            _e("northwind logistic", "org"),
            _e("northwind logistics", "org", "structured"),
            _e("jordan", "person"),
            _e("jordan", "place"),
        ]
    )
    assert res.mapping[("org", "northwind logistic")] == ("org", "northwind logistics")
    assert res.merges and res.merges[0][1] == ("org", "northwind logistics")
    assert res.mapping[("person", "jordan")] == ("person", "jordan")
    assert res.mapping[("place", "jordan")] == ("place", "jordan")
    assert any(a.source == "fuzzy" for a in res.new_aliases)


def test_org_without_suffix_merges_only_when_unambiguous():
    res = resolve([_e("acme", "org"), _e("acme corp", "org", "structured")])
    assert res.mapping[("org", "acme")] == ("org", "acme corp")
    res = resolve(
        [
            _e("atlas labs", "org"),
            _e("atlas labs gmbh", "org", "structured"),
            _e("atlas labs inc", "org", "structured"),
        ]
    )
    assert res.mapping[("org", "atlas labs")] == ("org", "atlas labs")  # two legal entities
    assert res.stats["ambiguous"] == 1 and len(res.proposals) >= 2
    res = resolve([_e("acme inc", "org"), _e("acme ltd", "org", "structured")])
    assert res.merges == () and res.proposals  # different suffixes: proposed only


def test_two_structured_entities_are_only_proposed():
    res = resolve(
        [
            _e("northwind logistic", "org", "structured"),
            _e("northwind logistics", "org", "structured"),
        ]
    )
    assert res.merges == ()
    assert res.proposals and res.proposals[0][2] >= 0.8
    assert res.mapping[("org", "northwind logistic")] == ("org", "northwind logistic")


def test_numbers_and_primary_keys_keep_entities_apart():
    res = resolve([_e("acme corp 17", "org"), _e("acme corp 18", "org", "structured")])
    assert res.mapping[("org", "acme corp 17")] == ("org", "acme corp 17")
    res = resolve([_e("acme#cu 1", "org", "structured"), _e("acme#cu 2", "org", "structured")])
    assert res.merges == () and res.proposals == ()


def test_merge_direction_follows_weights_for_text_entities():
    res = resolve(
        [_e("bluepeak analytic", "org"), _e("bluepeak analytics", "org")],
        weights={("org", "bluepeak analytic"): 9.0, ("org", "bluepeak analytics"): 1.0},
    )
    assert res.mapping[("org", "bluepeak analytics")] == ("org", "bluepeak analytic")


def test_apply_resolution_rekeys_and_drops_self_loops():
    x = GraphExtraction(
        entities=(_e("globex"), _e("globex", "org", "structured"), _e("acme", "org", "structured")),
        mentions=(
            Mention("globex", "entity", "c1", 0, 6, "Globex", "caps", 0.6),
            Mention("globex", "org", "c1", 0, 6, "Globex", "gazetteer", 0.95),
            Mention("acme", "org", "c1", 10, 14, "Acme", "caps", 0.8),
        ),
        relations=(
            RelationRef("globex", "entity", "globex", "org", "co_mentioned", "c1"),
            RelationRef("globex", "entity", "acme", "org", "co_mentioned", "c1"),
            RelationRef("acme", "org", "globex", "org", "co_mentioned", "c1"),
        ),
        aliases=(Alias("gx", "GX", "globex", "entity", "abbrev", 0.9),),
        stats={"x": 1},
    )
    res = resolve(list(x.entities))
    out = apply_resolution(x, res)
    assert {e.ref for e in out.entities} == {("org", "globex"), ("org", "acme")}
    assert len(out.mentions) == 2  # the two Globex mentions at offset 0 collapse
    assert len(out.relations) == 1 and out.relations[0].count == 2
    assert out.relations[0].src_key == "acme"  # symmetric relations are ordered
    assert ("gx", "org", "globex") in {
        (a.alias_key, a.entity_type, a.entity_key) for a in out.aliases
    }
    assert out.stats["merged_entities"] == 1 and out.stats["x"] == 1


def test_merge_extractions_prefers_structured_and_sums():
    a = GraphExtraction(
        (_e("acme", "org", "text", "ACME"),),
        (Mention("acme", "org", "c", 0, 4, "ACME", "caps", 0.8),),
        (RelationRef("acme", "org", "b", "org", "co_mentioned", "c"),),
        (),
        {"n": 1},
    )
    b = GraphExtraction(
        (_e("acme", "org", "structured", "Acme Corp"),),
        (Mention("acme", "org", "c", 0, 4, "ACME", "gazetteer", 0.95),),
        (RelationRef("acme", "org", "b", "org", "co_mentioned", "c", 2, "structured"),),
        (),
        {"n": 2},
    )
    m = merge_extractions([a, b])
    assert m.entities[0].name == "Acme Corp" and m.entities[0].origin == "structured"
    assert len(m.mentions) == 1
    assert m.relations[0].count == 3 and m.relations[0].origin == "structured"
    assert m.stats["n"] == 3
