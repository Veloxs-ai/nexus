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

import ast
import logging
import sys
import threading
import time
import types
from itertools import pairwise
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))

import ner_samples
import ner_samples_heldout

from nexus_guardrails import ner, ner_lexicon
from nexus_guardrails.config import PiiConfig
from nexus_guardrails.pii import PiiSpan, detect_pii_spans, mask_pii, mask_spans

SRC = Path(__file__).resolve().parents[1] / "src" / "nexus_guardrails"


def _found(text: str, backend: str = "lexicon") -> dict[str, str]:
    return {text[s.start : s.end]: s.entity for s in ner.find_entities(text, backend=backend)}


@pytest.fixture
def no_spacy(monkeypatch):
    """spaCy not importable (``import spacy`` raises ImportError)."""
    monkeypatch.setitem(sys.modules, "spacy", None)
    ner.reset_models()
    yield
    ner.reset_models()


class _Ent:
    def __init__(self, text: str, word: str, label: str) -> None:
        self.start_char = text.index(word)
        self.end_char = self.start_char + len(word)
        self.label_ = label


@pytest.fixture
def fake_spacy(monkeypatch):
    """A stand-in spaCy whose model labels fixed words; records every ``load`` call."""
    labels = {"Asha": "PERSON", "Pune": "GPE", "Alps": "LOC", "Gateway": "FAC", "Acme": "ORG"}
    loads: list[str] = []

    def load(name, disable=()):
        loads.append(name)
        time.sleep(0.02)  # slow enough that concurrent first calls overlap

        def nlp(text):
            ents = [_Ent(text, w, label) for w, label in labels.items() if w in text]
            return types.SimpleNamespace(ents=ents)

        return nlp

    monkeypatch.setitem(sys.modules, "spacy", types.SimpleNamespace(load=load))
    ner.reset_models()
    yield loads
    ner.reset_models()


# --- lexicon backend ------------------------------------------------------------------


def test_lexicon_people_and_places():
    found = _found("Dear Mr. Sharma, Priya Nair will meet Tanvir Ahmed in Pune and Chennai.")
    assert found == {
        "Sharma": "person",
        "Priya Nair": "person",
        "Tanvir Ahmed": "person",
        "Pune": "location",
        "Chennai": "location",
    }


def test_lexicon_trims_role_labels_and_honorifics():
    assert _found("Customer Ravi Shankar reports a crash.") == {"Ravi Shankar": "person"}
    assert _found("Smt. Lakshmi Devi submitted the form.") == {"Lakshmi Devi": "person"}
    assert _found("Patient John Matthews was admitted.") == {"John Matthews": "person"}


def test_lexicon_regions_surname_endings_and_cues():
    assert _found("Collections for South India are late.") == {"South India": "location"}
    assert _found("Kateryna Bondarenko leads the team.")["Kateryna Bondarenko"] == "person"
    assert _found("this is Anita from accounts") == {"Anita": "person"}
    assert _found("Mateus Rocha visited the plant.") == {"Mateus Rocha": "person"}


def test_lexicon_leaves_organisations_products_and_headings():
    for text in (
        "Morgan Stanley upgraded the stock.",
        "Johnson & Johnson reported quarterly results.",
        "Tata Consultancy Services renewed the contract.",
        "Quarterly Business Review",
        "The new iPhone supports faster charging.",
        "Warren Buffett Letter Archive",
        "Status: Open\nPriority: High\nOwner: Unassigned",
    ):
        assert _found(text) == {}, text


def test_ambiguous_place_needs_a_cue():
    assert _found("Add this to the Reading list.") == {}
    assert _found("We met in Reading last week.") == {"Reading": "location"}


def test_lexicon_without_processing_layer_keeps_honorific_cue_and_surname_rules(monkeypatch):
    monkeypatch.setattr(ner_lexicon, "_graph", lambda: None)
    found = _found("Dear Dr. Venkatesh, Tanvir Ahmed and Meera Krishnan will join.")
    assert found == {"Venkatesh": "person", "Tanvir Ahmed": "person", "Meera Krishnan": "person"}


def test_lexicon_lowercase_chat_needs_a_cue():
    found = _found("hey farhan can u ask lakshmi to call back from kochi")
    assert found == {"farhan": "person", "lakshmi": "person", "kochi": "location"}
    assert _found("@harini did venkat send it?") == {"harini": "person", "venkat": "person"}
    assert _found("anil kumar called twice") == {"anil kumar": "person"}
    for text in (
        "may i know the status of my refund?",
        "grace period is over, mark the bill as paid",
        "will do, thanks",
        "can you bring the reading list tomorrow",
        "abhi call karo bhai, kal milte hai",
        "farhan",  # a lexicon name without a cue stays unmasked
    ):
        assert _found(text) == {}, text


def test_lexicon_key_value_fields_and_signatures():
    record = '{"first_name": "Sakura", "last_name": "Ito", "city": "Kyoto", "tier": "gold"}'
    assert _found(record) == {"Sakura": "person", "Ito": "person", "Kyoto": "location"}
    assert _found("cust_name=meera joshi; city=nagpur; status=active") == {
        "meera joshi": "person",
        "nagpur": "location",
    }
    assert _found("customer: Ifeoma Nwosu | origin: Enugu") == {
        "Ifeoma Nwosu": "person",
        "Enugu": "location",
    }
    assert _found("Owner: Unassigned\nStatus: Open\nusername: jdoe") == {}
    signed = _found("Warm regards,\nRafael Moreira\nRegional Head\nLisbon Office")
    assert signed == {"Rafael Moreira": "person", "Lisbon": "location"}


def test_lexicon_place_heads_streets_and_lone_names():
    assert _found("We landed at Netaji Subhas Chandra Bose International Airport.") == {
        "Netaji Subhas Chandra Bose International Airport": "location"
    }
    assert _found("She rented a flat in Rajouri Garden near Tilak Nagar.") == {
        "Rajouri Garden": "location",
        "Tilak Nagar": "location",
    }
    assert _found("The shop is on Brigade Road, Bengaluru.") == {"Bengaluru": "location"}
    assert _found("Hyun-woo Choi is based in Daegu.") == {
        "Hyun-woo Choi": "person",
        "Daegu": "location",
    }
    assert _found("Bhattacharya will share the numbers.") == {"Bhattacharya": "person"}
    assert _found("Please ask Joglekar to sign, then hand it to Tanvi.") == {
        "Joglekar": "person",
        "Tanvi": "person",
    }


def test_lexicon_vetoes_organisations_brands_and_nationalities():
    for text in (
        "Torrent Pharmaceuticals renewed the contract.",
        "Kirloskar Brothers shipped the pumps.",
        "Calvin Klein jeans are on sale.",
        "Marks & Spencer opened a store.",
        "The Bengali version of the brochure is ready.",
        "The Diwali Mela stall bookings are open.",
        "Your EMI is due on Monday.",
        "Hi Everyone, quick update.",
        "Ping DevOps on Slack.",
    ):
        assert _found(text) == {}, text


def test_lexicon_is_linear_and_safe_on_pathological_text():
    long_word = "a" * 40_000 + ":" + "b" * 40_000
    for text in (long_word, "ab:" * 30_000, "Ravi Kumar from Pune. " * 4000):
        started = time.perf_counter()
        ner.find_entities(text, backend="lexicon")
        assert time.perf_counter() - started < 2.0


def _score(data, backend):
    stats = {e: [0, 0, 0, 0] for e in ner.ENTITIES}  # pred, pred-hit, gold, gold-hit
    for text, gold in data:
        pred = [(s.start, s.end, s.entity) for s in ner.find_entities(text, backend=backend)]
        for entity, row in stats.items():
            g = [x for x in gold if x[2] == entity]
            p = [x for x in pred if x[2] == entity]
            row[0] += len(p)
            row[1] += sum(any(a < d and c < b for c, d, _ in g) for a, b, _ in p)
            row[2] += len(g)
            row[3] += sum(any(a < d and c < b for c, d, _ in p) for a, b, _ in g)
    return {e: (r[1] / max(r[0], 1), r[3] / max(r[2], 1)) for e, r in stats.items()}


def test_lexicon_accuracy_on_labelled_sentences():
    data = ner_samples.load()
    assert len(data) >= 200
    scores = _score(data, "lexicon")
    for entity, (precision, recall) in scores.items():
        assert precision >= 0.95 and recall >= 0.95, (entity, precision, recall)
    held = _score(ner_samples.load(ner_samples_heldout.HELD_OUT), "lexicon")
    assert held["person"][0] >= 0.75 and held["person"][1] >= 0.75, held
    assert held["location"][0] >= 0.9 and held["location"][1] >= 0.9, held


# --- spaCy backend, fallback and model loading ----------------------------------------


def test_missing_spacy_falls_back_without_raising(no_spacy, caplog):
    with caplog.at_level(logging.WARNING, logger=ner.__name__):
        assert ner.backend_in_use("auto") == "lexicon"
        assert ner.backend_in_use("spacy") == "lexicon"
        assert not ner.spacy_available()
        for backend in ("auto", "spacy"):
            assert _found("Hi Priya, the Pune office is ready.", backend) == {
                "Priya": "person",
                "Pune": "location",
            }
    assert sum("unavailable" in r.getMessage() for r in caplog.records) == 1  # logged once


def test_model_that_fails_to_load_falls_back(monkeypatch):
    def load(name, disable=()):
        raise OSError(f"[E050] Can't find model '{name}'")

    monkeypatch.setitem(sys.modules, "spacy", types.SimpleNamespace(load=load))
    ner.reset_models()
    try:
        assert ner.backend_in_use("auto", model="xx_missing") == "lexicon"
        assert _found("Priya Nair lives in Pune.", "auto") == {
            "Priya Nair": "person",
            "Pune": "location",
        }
    finally:
        ner.reset_models()


def test_spacy_labels_map_to_person_and_location(fake_spacy):
    text = "Asha flew from Pune over the Alps to the Gateway for Acme."
    assert ner.backend_in_use("auto") == "spacy"
    assert _found(text, "spacy") == {
        "Asha": "person",
        "Pune": "location",
        "Alps": "location",
        "Gateway": "location",
    }
    assert _found(text, "lexicon").get("Acme") is None
    only = ner.find_entities(text, {"PERSON"}, backend="auto")
    assert [(text[s.start : s.end], s.entity) for s in only] == [("Asha", "person")]


def test_model_name_from_argument_then_env_then_default(fake_spacy, monkeypatch):
    monkeypatch.delenv(ner.MODEL_ENV, raising=False)
    ner.find_entities("Asha", backend="spacy")
    monkeypatch.setenv(ner.MODEL_ENV, "en_core_web_md")
    ner.find_entities("Asha", backend="spacy")
    ner.find_entities("Asha", backend="spacy", model="en_core_web_lg")
    assert fake_spacy == ["en_core_web_sm", "en_core_web_md", "en_core_web_lg"]


def test_model_loads_once_across_threads(fake_spacy):
    barrier = threading.Barrier(8)

    def work():
        barrier.wait()
        ner.find_entities("Asha in Pune", backend="auto")

    threads = [threading.Thread(target=work) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert fake_spacy == ["en_core_web_sm"]


def test_unknown_backend_is_an_error():
    with pytest.raises(ValueError):
        ner.find_entities("Priya", backend="bert")


def test_real_spacy_model_when_installed():
    pytest.importorskip("spacy")
    ner.reset_models()
    if not ner.spacy_available():
        pytest.skip("spaCy model en_core_web_sm not installed")
    found = _found("Priya Sharma moved from Mumbai to London last year.", "spacy")
    assert found.get("Priya Sharma") == "person"
    assert found.get("London") == "location"


# --- spans, overlap and long text -----------------------------------------------------


def test_overlaps_keep_the_earlier_then_longer_span():
    spans = [PiiSpan(0, 5, "person"), PiiSpan(0, 11, "person"), PiiSpan(8, 14, "location")]
    assert ner.non_overlapping(spans) == [PiiSpan(0, 11, "person")]


def test_long_text_is_scanned_in_windows(fake_spacy):
    text = ("filler words here " * 200) + "Asha visited Pune."
    spans = ner.find_entities(text, backend="spacy", max_chars=1000)
    assert [text[s.start : s.end] for s in spans] == ["Asha", "Pune"]
    text = text.replace("Asha", "Priya Nair")
    lexicon = ner.find_entities(text, backend="lexicon", max_chars=1000)
    assert [s.entity for s in lexicon] == ["person", "location"]


def test_detect_pii_spans_with_named_entities_and_addresses():
    text = "Priya Nair (priya@example.com) lives at 221B Baker Street, London."
    spans = detect_pii_spans(text, entities=["email", "address", "person", "location"],
                             ner_backend="lexicon")
    assert [(text[s.start : s.end], s.entity) for s in spans] == [
        ("Priya Nair", "person"),
        ("priya@example.com", "email"),
        ("221B Baker Street", "address"),
        ("London", "location"),
    ]
    assert all(a.end <= b.start for a, b in pairwise(spans))
    assert mask_spans(text, spans) == "[PERSON] ([EMAIL]) lives at [ADDRESS], [LOCATION]."


def test_named_entities_never_overlap_pattern_spans(monkeypatch):
    text = "Contact Asha Pune at asha.pune@example.com"
    monkeypatch.setattr(
        ner, "find_entities", lambda *a, **k: [PiiSpan(21, 25, "person"), PiiSpan(8, 12, "person")]
    )
    spans = ner.add_entities(text, detect_pii_spans(text, entities=["email"]), ["person"])
    assert [(s.start, s.end, s.entity) for s in spans] == [(8, 12, "person"), (21, 42, "email")]


def test_mask_pii_with_person_detector():
    config = PiiConfig(detectors=["email", "person", "location"])
    masked = mask_pii("Dear Ms. Fernandes, write to a@b.co from Goa.", config)
    assert masked == "Dear Ms. [PERSON], write to [EMAIL] from [LOCATION]."


# --- packaging guarantees -------------------------------------------------------------


def test_ner_modules_are_stdlib_only_and_small():
    allowed = set(sys.stdlib_module_names) | {"nexus", "nexus_guardrails", "nexus_processing"}
    names = ("ner", "ner_lexicon", "ner_rules", "ner_words", "ner_data", "ner_lowercase")
    data = ("ner_names_south_asia", "ner_names_world", "ner_surnames", "ner_places")
    for name in (*names, *data, "pii"):
        source = (SRC / f"{name}.py").read_text()
        assert source.count("\n") < 500, name
        for node in ast.parse(source).body:  # top level only: spaCy is imported lazily
            if isinstance(node, ast.Import):
                roots = {a.name.split(".")[0] for a in node.names}
            elif isinstance(node, ast.ImportFrom) and node.level == 0:
                roots = {(node.module or "").split(".")[0]}
            else:
                continue
            assert roots <= allowed, (name, roots)
    assert "import spacy" in (SRC / "ner.py").read_text()  # only inside _load_spacy
