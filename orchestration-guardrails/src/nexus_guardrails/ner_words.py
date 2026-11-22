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

"""The lexicons of the lexicon person/location detector, built lazily once per process.

Given names and places are the knowledge-graph lexicons (``nexus.processing.graph_lexicon``,
when the processing layer is installed) plus the PII extensions in this package
(``ner_names_south_asia``, ``ner_names_world``, ``ner_places``); surnames and the lowercase
stop list are PII-only (``ner_surnames``, ``ner_lowercase``). The functions mirror the
graph lexicon's (``given_names()``, ``ambiguous_names()``, ``places()``,
``ambiguous_places()``) so the detector can use this module in its place.

Also small closed word lists: place heads ("Airport", "Nagar"), street heads, organisation
tails, nationalities and languages, person-named brands.
"""

from __future__ import annotations

import threading
from typing import Any

_LAZY: dict[str, frozenset[str]] = {}
_lock = threading.RLock()  # re-entrant: one list is built from another


def _words(text: str) -> frozenset[str]:
    return frozenset(w.replace("_", " ") for w in text.split())


def graph_lexicon() -> Any:
    """The processing layer's ``graph_lexicon`` module, or ``None`` when not installed."""
    try:
        from ..processing import graph_lexicon as lex  # type: ignore
    except ImportError:
        try:
            from nexus_processing import graph_lexicon as lex  # type: ignore
        except ImportError:
            return None
    return lex


def _build(key: str) -> frozenset[str]:
    from . import ner_lowercase, ner_names_south_asia, ner_names_world, ner_places, ner_surnames

    lex = graph_lexicon()
    graph = {
        "given": lex.given_names() if lex else frozenset(),
        "given_ambiguous": lex.ambiguous_names() if lex else frozenset(),
        "places": lex.places() if lex else frozenset(),
        "places_ambiguous": lex.ambiguous_places() if lex else frozenset(),
    }
    own = {
        "given": ner_names_south_asia.PACKED + ner_names_world.PACKED,
        "given_ambiguous": ner_names_world.AMBIGUOUS,
        "places": ner_places.PACKED + ner_places.AMBIGUOUS,
        "places_ambiguous": ner_places.AMBIGUOUS,
        "surnames": ner_surnames.PACKED,
        "surnames_weak": ner_surnames.WEAK,
        "lower_stop": ner_lowercase.STOP,
    }
    built = _words(own[key]) | graph.get(key, frozenset())
    if key == "given":  # ambiguous names never type a lone word
        built = built - _build_cached("given_ambiguous")
    return frozenset(built)


def _build_cached(key: str) -> frozenset[str]:
    found = _LAZY.get(key)
    if found is None:
        with _lock:
            found = _LAZY.get(key)
            if found is None:
                found = _LAZY[key] = _build(key)
    return found


def given_names() -> frozenset[str]:
    """Casefolded given names that type a lone capitalised word (about 10,000)."""
    return _build_cached("given")


def ambiguous_names() -> frozenset[str]:
    """Given names that are also ordinary words ("Grace", "Jade"): multi-word names only."""
    return _build_cached("given_ambiguous")


def places() -> frozenset[str]:
    """Casefolded places, ambiguous ones included (about 7,000)."""
    return _build_cached("places")


def ambiguous_places() -> frozenset[str]:
    """Places that are also words, names or brands ("Reading"): need a place cue."""
    return _build_cached("places_ambiguous")


def surnames() -> frozenset[str]:
    """Surnames that are not ordinary words: complete a name after any capitalised word."""
    return _build_cached("surnames")


def weak_surnames() -> frozenset[str]:
    """Surnames that are also words ("Stone"): complete a name only after a given name."""
    return _build_cached("surnames_weak")


def lower_stop() -> frozenset[str]:
    """Names and places that are also English words: never typed in lowercase text."""
    return _build_cached("lower_stop")


# Last word of a capitalised place name ("Kempegowda International Airport", "Lajpat Nagar").
PLACE_HEADS = _words("""
airport airfield station terminus terminal junction cantonment cantt beach fort lake lakes palace
bridge hills valley nagar colony layout vihar enclave puram bagh chowk market park island
islands bay falls temple mandir mosque masjid church cathedral basilica gurudwara gurdwara
monastery square gate mahal minar memorial gardens garden dam ghat ghats peak mountain mountains
river sea ocean desert canyon harbour harbor pier wharf quay creek extension township city
village district county province peninsula coast strait glacier volcano reservoir sanctuary
reserve forest wildlife
""")
# Words before a place head that make the span generic or an organisation ("Police Station").
PLACE_HEAD_VETO = _words("""
police fire gas petrol power service base work charging docking radio tv space weather tech
technology business industrial science software it theme amusement car ball water trailer
office corporate data stock capital money labour labor job flea black super bus metro
""")
# Last word of a street (streets are not locations for PII: "Baker Street", "MG Road").
STREET_HEADS = _words("""
road rd street st lane ln marg avenue ave highway hwy expressway boulevard blvd salai drive
way crescent close terrace parkway row
""")
# Words that make a preceding capitalised name an organisation ("Reddy's Laboratories").
ORG_TAILS = _words("""
bank banks ltd limited inc incorporated llc llp plc corp corporation company co pvt motors
laboratories labs pharma pharmaceuticals industries group holdings hospital hospitals clinic
school schools college university institute academy foundation trust society associates
partners consulting consultants solutions systems technologies technology software services
enterprises ventures capital securities insurance finance financial airlines airways
pictures studios films records media foods beverages textiles steels steel cement chemicals
electronics electricals constructions builders developers realty properties hotels hotel
resorts restaurants cafe store stores mart traders exports imports logistics transport
travels tours agency agencies brothers bros sons indians kings knights warriors united fc
controls apartments towers residency residences heights villas homes plaza complex mall
""")
# Nationalities, demonyms and languages: never a location on their own ("in Spanish").
NATIONALITIES = _words("""
american british english french german spanish italian portuguese dutch swedish norwegian
danish finnish polish russian ukrainian greek turkish arabic arab persian hebrew chinese
mandarin cantonese japanese korean vietnamese thai indonesian malay filipino tagalog indian
hindi urdu bengali bangla tamil telugu kannada malayalam marathi gujarati punjabi odia oriya
assamese konkani sindhi kashmiri nepali sinhala sinhalese pakistani bangladeshi sri_lankan
african nigerian kenyan ghanaian ethiopian egyptian moroccan swahili zulu xhosa yoruba igbo
hausa amharic mexican brazilian argentine argentinian colombian chilean peruvian canadian
australian irish scottish welsh european asian latin latino hispanic swiss austrian belgian
czech hungarian romanian serbian croatian bulgarian israeli iranian iraqi saudi emirati
""")
# Brands and firms named after people: never a person ("Jack Daniel's", "Ernst & Young").
PERSON_BRANDS = _words("""
jack_daniel jack_daniels johnnie_walker jim_beam tommy_hilfiger calvin_klein ralph_lauren
louis_vuitton giorgio_armani hugo_boss coco_chanel estee_lauder mary_kay betty_crocker
dr_pepper ronald_mcdonald tim_hortons kate_spade michael_kors tory_burch vera_wang anne_klein
john_deere harley_davidson walt_disney charles_schwab morgan_stanley goldman_sachs
merrill_lynch wells_fargo dow_jones arthur_andersen sherwin_williams rolls_royce aston_martin
mercedes_benz hewlett_packard william_grant ashok_leyland marks_spencer ernst_young
procter_gamble johnson_johnson ben_jerry dolce_gabbana victoria_secret paul_smith ted_baker
tom_ford alexander_mcqueen stella_mccartney oscar_de_la_renta jimmy_choo christian_dior
christian_louboutin yves_saint_laurent max_factor ray_ban kenneth_cole steve_madden
""")
# Festival and holiday words: a span holding one is not a person ("Ganesh Chaturthi").
FESTIVALS = _words("""
diwali deepavali holi eid ramadan ramzan christmas xmas easter navratri navaratri dussehra
dasara durga_puja lakshmi_puja saraswati_puja kali_puja onam pongal sankranti lohri baisakhi
vaisakhi bandhan rakhi janmashtami
chaturthi ganeshotsav chauth chhath ugadi padwa bihu thanksgiving hanukkah passover jayanti
purnima amavasya ekadashi shivratri mahashivratri muharram navroz nowruz vesak halloween
""")
# Group and desk words that follow a greeting or cue without naming a person ("Hi Everyone").
GROUP_WORDS = _words("""
everyone everybody anyone anybody someone somebody all team teams folks guys people friends
colleagues reception receptionist helpdesk desk frontdesk devops sre ops admin admins finance
accounts payroll legal marketing procurement security housekeeping facilities management
""")
