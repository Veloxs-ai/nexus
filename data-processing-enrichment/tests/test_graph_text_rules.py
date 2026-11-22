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

"""Span boundaries, vetoes, lowercase mentions and relations of the text extractor (3.6.0)."""

from __future__ import annotations

from nexus_processing.graph_lexicon import given_names, layer_data, places, plain
from nexus_processing.graph_relations import chunk_relations
from nexus_processing.graph_spans import find_abbreviations
from nexus_processing.graph_text import TextGraphConfig, _Acc, extract_mentions
from nexus_processing.graph_tokens import tokenise

_CFG = TextGraphConfig(noun_phrases=False)


def _names(text, **cfg):
    x = extract_mentions([("c", text)], config=TextGraphConfig(noun_phrases=False, **cfg))
    return {(m.surface, m.entity_type) for m in x.mentions}


def _typed(text):
    x = extract_mentions([("c", text)], config=_CFG)
    names = {(e.type, e.key): e.name for e in x.entities}
    return {
        (names[(r.src_type, r.src_key)], r.type, names[(r.dst_type, r.dst_key)])
        for r in x.relations
        if r.type != "co_mentioned"
    }


# -- span boundaries -------------------------------------------------------------------------
def test_legal_suffix_abbreviations_and_numbers_after_them():
    got = _names("Our vendor is Cloudreach Solutions Pvt. Ltd., based in Bengaluru.")
    assert ("Cloudreach Solutions Pvt. Ltd", "org") in got
    assert ("Orion Pharma Oy", "org") in _names("Invoices go to Orion Pharma Oy 5 days later.")
    assert ("Atlas 300", "product") in _names("Atlas 300 is a model.")  # a model number stays


def test_possessive_ends_a_name_and_owner_is_kept():
    got = _names("We met HSBC's Global Banking team. Safaricom's M-Pesa grew.")
    assert {"HSBC", "Global Banking", "Safaricom", "M-Pesa"} <= {s for s, _ in got}
    assert not any("'s" in s for s, _ in got)
    assert ("St. Mary's Hospital", "org") in _names("She works at St. Mary's Hospital in Cork.")


def test_versioned_and_digit_names():
    got = _names("We moved to Java 21, patched Apache Log4j 2.14 and run SAP S/4HANA.")
    assert {("Java 21", "product"), ("Apache Log4j", "product"), ("SAP S/4HANA", "product")} <= got
    assert ("Atlas Mobile", "product") in _names("Please install Atlas Mobile 3.8.1 today.")


def test_camel_case_brands_but_not_code_identifiers():
    got = _names("Drone maker ideaForge won. Our iOS 17 app and eBay shop. Set the userId field.")
    assert {"ideaForge", "iOS 17", "eBay"} <= {s for s, _ in got}
    assert "userId" not in {s for s, _ in got}
    assert "getUser" not in {s for s, _ in _names("Then call getUser() on the client.")}


def test_name_particles_and_honorifics():
    got = _names("Sheikh Mohammed bin Rashid met Ana de la Cruz in Dubai.")
    assert {("Mohammed bin Rashid", "person"), ("Ana de la Cruz", "person")} <= got


def test_ministry_of_a_and_b_stays_one_name_but_two_orgs_split():
    got = _names("The Ministry of Electronics and Information Technology issued rules.")
    assert ("Ministry of Electronics and Information Technology", "org") in got
    got = _names("The University of Toronto and Veloxs signed an agreement.")
    assert ("University of Toronto", "org") in got and "Veloxs" in {s for s, _ in got}


def test_hyphenated_places_split_and_hyphenated_names_kept():
    got = _names("The Mumbai-Chennai MPLS link failed. CERT-In was notified by Fatima Al-Mansouri.")
    assert {("Mumbai", "place"), ("Chennai", "place")} <= got
    assert "CERT-In" in {s for s, _ in got} and ("Fatima Al-Mansouri", "person") in got


# -- vetoes ----------------------------------------------------------------------------------
def test_title_case_phrases_labels_and_demonyms_are_not_entities():
    text = (
        "Please book Economy Class and the Large Conference Room. Have a Great Weekend! "
        "Purchase Order PO-55102 covers the Kenyan rollout, written in English. "
        "The Licensor grants the Licensee a licence. SOC 2 Type II is due. NPS rose 4% YoY."
    )
    assert {s for s, _ in _names(text)} == {"PO-55102", "SOC 2"}
    assert ("Annual Report", "entity") in _names("See the Annual Report 2025 for details.")
    assert ("Customer Advisory Board", "org") in _names("The Customer Advisory Board met.")


def test_role_before_department_and_role_phrase_before_a_name():
    got = _names("Contact: Anjali Nair (Head of Procurement). VP Engineering: Rebecca Thornton.")
    assert {"Procurement", "VP Engineering"}.isdisjoint({s for s, _ in got})
    got = _names("He reports to Chief Technology Officer Alejandro Ruiz.")
    assert ("Alejandro Ruiz", "person") in got


def test_abbreviation_with_letters_inside_words():
    tk = tokenise("Hindustan Unilever (HUL) moved. Bharat Petroleum (BPCL) did not.")
    abbrs: dict = {}
    find_abbreviations(tk, abbrs)
    assert set(abbrs) == {"HUL"} and abbrs["HUL"][2] == "Hindustan Unilever"
    got = _names("Hindustan Unilever (HUL) moved. HUL's IT lead agreed.")
    assert ("HUL", "org") in got


# -- lowercase mentions ------------------------------------------------------------------------
def test_lowercase_known_names_need_safe_words_or_cues():
    got = _names("priya: did infosys fix it? grafana shows 500s, rahul's on it (ana) ok")
    assert {("priya", "person"), ("infosys", "org"), ("grafana", "product")} <= got
    assert {("rahul", "person"), ("ana", "person")} <= got
    assert _names("we will grant access and mark it done", lowercase=True) == set()
    got = _names("the old react 17 build broke and stripe webhooks lag; we react fast")
    assert {("react 17", "product"), ("stripe", "org")} <= got and len(got) == 2
    assert _names("ping rahul", lowercase=False) == set()


# -- typing ----------------------------------------------------------------------------------
def test_typing_from_surnames_known_firms_versions_and_documents():
    got = _names("Bartholomew Achterberg called. Thales India signed. José Luis Pérez agreed.")
    assert {("Bartholomew Achterberg", "person"), ("José Luis Pérez", "person")} <= got
    assert ("Thales India", "org") in _names("We signed with Thales. Thales India will deliver.")
    assert ("Hindustan Unilever", "org") in _names("Hindustan Unilever moved its portal.")
    got = _names("Project Phoenix shipped. The Phoenix team celebrated.")
    assert ("Phoenix", "project") in got
    got = _names("They join from Flutterwave, Paystack and Globant.")
    assert {("Paystack", "org"), ("Globant", "org")} <= got


def test_lexicons_include_the_guardrails_layer_lists_when_installed():
    extra = layer_data("ner_names_world", "PACKED")
    if extra:  # the guardrails layer is installed next to this one (the Nexus monorepo)
        assert "bartholomew" in given_names() and "ameerpet" in places()
    assert layer_data("no_such_module", "PACKED") == ""
    assert plain("josé") == "jose" and plain("pune") == "pune"


# -- relations -------------------------------------------------------------------------------
def test_typed_relations_from_patterns():
    text = (
        "Dr. Lena Hoffmann, CEO of Brightline Analytics, spoke. Brightline Analytics acquired "
        "Nordwind Labs. Nordwind Labs is headquartered in Hamburg. Ravi Menon works at Acme "
        "Corp. Kestrel Ltd was acquired by Acme Corp. Safaricom's M-Pesa grew."
    )
    assert _typed(text) >= {
        ("Lena Hoffmann", "works_for", "Brightline Analytics"),
        ("Brightline Analytics", "acquired", "Nordwind Labs"),
        ("Nordwind Labs", "located_in", "Hamburg"),
        ("Ravi Menon", "works_for", "Acme Corp"),
        ("Acme Corp", "acquired", "Kestrel Ltd"),
    }
    assert not _typed("Acme Corp and Globex Inc met in Pune.")


def test_window_and_record_co_mentions():
    text = (
        "Account: Mahindra Ltd\nContact: Anjali Nair\nStage: Negotiation\n"
        "Notes: wants pricing for the Nashik plant."
    )
    x = extract_mentions([("c", text)], config=_CFG)
    names = {(e.type, e.key): e.name for e in x.entities}
    pairs = {
        frozenset((names[(r.src_type, r.src_key)], names[(r.dst_type, r.dst_key)]))
        for r in x.relations
    }
    assert frozenset(("Mahindra Ltd", "Anjali Nair")) in pairs
    assert frozenset(("Mahindra Ltd", "Nashik")) in pairs  # one record, four lines apart
    long = (
        "Acme Corp signed the renewal after a long review of every clause in the master "
        "agreement with its lawyers. Globex Inc opened a new office far away from everything "
        "else that week and nobody noticed it at all."
    )
    x = extract_mentions([("c", long)], config=_CFG)
    assert not x.relations  # long sentences without a link stay apart
    acc = _Acc()
    tk = tokenise("Acme Corp met Globex Inc.")
    chunk_relations(tk, [], _CFG, acc, "c")
    assert not acc.relations and not acc.typed
