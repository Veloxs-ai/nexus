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

from nexus_processing.graph_lexicon import column_type
from nexus_processing.graph_text import TextGraphConfig, extract_mentions, type_of_span
from nexus_processing.graph_tokens import BREAK, JOIN, START, Gazetteer, tokenise


def _names(x, method=None):
    return {(m.surface, m.entity_type) for m in x.mentions if method is None or m.method == method}


def _entities(x):
    return {(e.name, e.type) for e in x.entities if e.status == "active"}


# -- tokenisation -------------------------------------------------------------------------
def test_tokenise_flags_and_sentences():
    tk = tokenise("Acme Corp met Globex. Then: Initech\nnext")
    assert tk.toks == ["Acme", "Corp", "met", "Globex", "Then", "Initech", "next"]
    assert tk.flags[0] & START and tk.flags[1] & JOIN
    assert tk.flags[4] & BREAK and tk.flags[5] & START and not tk.flags[5] & BREAK
    assert tk.sentence == [0, 0, 0, 0, 1, 1, 2]


def test_tokenise_blocks_masks_and_heading_lines():
    tk = tokenise("Mail [EMAIL] or <PERSON> now\nQUARTERLY REVIEW SUMMARY\nAcme")
    blocked = {tk.toks[i] for i in tk.blocked}
    assert {"EMAIL", "PERSON", "QUARTERLY", "REVIEW", "SUMMARY"} <= blocked
    assert "Acme" not in blocked


def test_honorific_and_saint_abbreviations_do_not_break_names():
    x = extract_mentions([("c", "We met Dr. Elena Petrova at St. Mary's Hospital yesterday.")])
    assert ("Elena Petrova", "person") in _names(x)
    assert ("St. Mary's Hospital", "org") in _names(x)


# -- gazetteer ------------------------------------------------------------------------------
def test_gazetteer_longest_match_and_case_rules():
    gaz = Gazetteer.build(
        [
            ("Acme", "acme", "org"),
            ("Acme Corp", "acme", "org"),
            ("IT", "it", "org"),
            ("Northwind Logistics Ltd", "northwind logistics", "org"),
            ("Pune", "pune", "place"),
        ]
    )
    x = extract_mentions(
        [("c", "acme corp and it teams; IT reviewed Northwind Logistics in pune and Pune.")],
        gazetteer=gaz,
    )
    got = [(m.surface, m.method) for m in x.mentions if m.method == "gazetteer"]
    assert ("acme corp", "gazetteer") in got  # multi-token names match in any case
    assert ("IT", "gazetteer") in got and ("it", "gazetteer") not in got  # short tokens are exact
    assert ("Northwind Logistics", "gazetteer") in got  # legal suffix optional for orgs
    assert ("Pune", "gazetteer") in got and (
        "pune",
        "gazetteer",
    ) not in got  # single tokens capitalised
    assert all(m.confidence == 0.95 for m in x.mentions if m.method == "gazetteer")
    assert len(gaz) >= 5


def test_gazetteer_hits_do_not_create_entities():
    gaz = Gazetteer.build([("Orion Retail", "orion retail", "org")])
    x = extract_mentions(
        [("c", "Orion Retail called twice.")],
        gazetteer=gaz,
        config=TextGraphConfig(noun_phrases=False),
    )
    assert [m.entity_key for m in x.mentions] == ["orion retail"]
    assert x.entities == ()


# -- capitalised spans ------------------------------------------------------------------------
def test_capitalised_span_filters():
    text = (
        "The report was sent on Monday. Contract Term\nStatus: Open\nWe visited Boston and Chicago "
        "with Ravi Kumar of Acme Corp. Chief Risk Officer approved. A B C D E F Gh is long."
    )
    x = extract_mentions([("c", text)], config=TextGraphConfig(noun_phrases=False))
    names = _names(x)
    assert ("Boston", "place") in names and ("Chicago", "place") in names  # "and" splits names
    assert ("Ravi Kumar", "person") in names and ("Acme Corp", "org") in names
    surfaces = {s for s, _ in names}
    assert not surfaces & {"The", "Monday", "Contract Term", "Status", "Open", "Chief Risk Officer"}
    assert not any(len(s.split()) >= 6 for s in surfaces)


def test_role_before_a_name_is_not_part_of_it():
    text = (
        "Q3 review: CFO Daniel Abernathy expects growth. The board met in Toronto, where "
        "Chair Eleanor Whitfield asked for a pause. Partner Bank Holdings declined."
    )
    x = extract_mentions([("c", text)], config=TextGraphConfig(noun_phrases=False))
    names = _names(x)
    assert ("Daniel Abernathy", "person") in names and ("Eleanor Whitfield", "person") in names
    surfaces = {s for s, _ in names}
    assert not surfaces & {"CFO Daniel Abernathy", "Chair Eleanor Whitfield"}
    assert "Partner Bank Holdings" in surfaces  # no given name after the role word: one name


def test_sentence_start_single_token_needs_evidence():
    x = extract_mentions([("c", "Zorbex is new. We like Zorbex.")])
    assert ("Zorbex", "entity") in _names(x)
    x = extract_mentions([("c", "Zorbex is new. We like it.")])
    assert not _names(x)
    x = extract_mentions([("c", "Gringotts requested a copy.")])  # subject of a past-tense verb
    assert ("Gringotts", "org") in _names(x)  # typed by the verb cue (3.4.0)


def test_lowercase_use_elsewhere_rejects_single_token():
    x = extract_mentions(
        [("c", "We discussed Billing at length. The billing team agreed.")],
        config=TextGraphConfig(noun_phrases=False),
    )
    assert not _names(x)


def test_possessive_and_masked_values():
    x = extract_mentions(
        [("c", "We reviewed Hooli's offer. Reach Priya Shah at [EMAIL] or [PHONE].")],
        config=TextGraphConfig(noun_phrases=False),
    )
    names = {s for s, _ in _names(x)}
    assert "Hooli" in names and "Priya Shah" in names
    assert not names & {"EMAIL", "PHONE"}


# -- typing -------------------------------------------------------------------------------------
def test_type_of_span():
    assert type_of_span(["acme", "corp"]) == "org"
    assert type_of_span(["state", "bank", "of", "india"]) == "org"
    assert type_of_span(["priya", "nair"]) == "person"
    assert type_of_span(["smith"], honorific=True) == "person"
    assert type_of_span(["new", "york"]) == "place"
    assert type_of_span(["zorbex"]) == "entity"


def test_column_type_lexicon():
    assert column_type("assignee") == "person"
    assert column_type("customer_id") == "org"
    assert column_type("Warehouse") == "place"
    assert column_type("sku_name") == "product"
    assert column_type("epic") == "project"
    assert column_type("colour") == "entity"


# -- ids, abbreviations, noun phrases -----------------------------------------------------------
def test_ids_are_record_entities():
    x = extract_mentions(
        [("c", "See INC0012345, CHG-20417 and T-2000; not P1, FY2025 or 2025-03-04.")]
    )
    ids = {m.surface for m in x.mentions if m.method == "id"}
    assert ids == {"INC0012345", "CHG-20417", "T-2000"}
    assert all(m.entity_type == "record" for m in x.mentions if m.method == "id")


def test_abbreviations_both_directions_across_chunks():
    chunks = [
        (
            "c1",
            "The Service Level Agreement (SLA) and GDPR (General Data Protection Regulation) "
            "apply.",
            "d",
        ),
        ("c2", "Breaches of the SLA and of GDPR are reported.", "d"),
    ]
    x = extract_mentions(chunks, config=TextGraphConfig(noun_phrases=False))
    abbrev = [(m.chunk_key, m.surface, m.entity_key) for m in x.mentions if m.method == "abbrev"]
    assert ("c2", "SLA", "service level agreement") in abbrev
    assert ("c2", "GDPR", "general data protection regulation") in abbrev
    aliases = {(a.alias, a.entity_key, a.source) for a in x.aliases}
    assert ("SLA", "service level agreement", "abbrev") in aliases


def test_abbreviation_scope_is_the_document():
    chunks = [
        ("c1", "The Key Performance Indicator (KPI) is set.", "d1"),
        ("c2", "The KPI fell.", "d2"),
    ]
    x = extract_mentions(chunks)
    assert not [m for m in x.mentions if m.chunk_key == "c2" and m.method == "abbrev"]


def test_noun_phrases_are_candidates_and_capped():
    text = " ".join(
        ["Customers report billing errors and late delivery and damaged packaging."] * 3
    )
    x = extract_mentions([("c", text)], config=TextGraphConfig(max_concepts_per_chunk=2))
    concepts = {e.key for e in x.entities if e.type == "concept"}
    assert concepts and len(concepts) <= 2
    assert all(e.status == "candidate" for e in x.entities if e.type == "concept")
    assert not [r for r in x.relations if "concept" in (r.src_type, r.dst_type)]


# -- relations, hook, stats --------------------------------------------------------------------
def test_co_mentions_per_sentence_with_counts():
    text = "Acme Corp hired Globex Inc. Later Acme Corp and Globex Inc signed. Initech Ltd waited."
    x = extract_mentions([("c", text)], config=TextGraphConfig(noun_phrases=False))
    rels = {(r.src_key, r.dst_key): r.count for r in x.relations}
    assert rels == {("acme corp", "globex inc"): 2}
    assert all(r.type == "co_mentioned" and r.chunk_key == "c" for r in x.relations)


def test_extra_detector_hook():
    def detector(text):
        start = text.index("zeta widget")
        return [(start, start + len("zeta widget"), "product")]

    x = extract_mentions([("c", "We sell the zeta widget worldwide.")], extra_detector=detector)
    hook = [m for m in x.mentions if m.method == "hook"]
    assert hook and hook[0].entity_type == "product" and hook[0].confidence == 0.85


def test_offsets_point_at_surface_and_stats():
    text = "Ticket T-2000 opened by Orion Retail in Pune."
    x = extract_mentions([("c", text)])
    for m in x.mentions:
        assert text[m.start : m.end] == m.surface
    assert x.stats["chunks"] == 1 and x.stats["chars"] == len(text)
    assert x.stats["text_mentions"] == len(x.mentions)


def test_disable_passes():
    cfg = TextGraphConfig(
        ids=False, capitalised=False, noun_phrases=False, abbreviations=False, relations=False
    )
    x = extract_mentions([("c", "Acme Corp filed T-2000 about late delivery.")], config=cfg)
    assert x.mentions == () and x.relations == ()


def test_empty_and_whitespace_chunks():
    x = extract_mentions([("a", ""), ("b", "   "), ("c", None)])  # type: ignore[list-item]
    assert x.mentions == () and x.stats["chunks"] == 3
