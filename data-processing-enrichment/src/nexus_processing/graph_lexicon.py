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

"""Word lists for the knowledge-graph extractors (data only, all casefolded).

Kept as whitespace-separated strings so the module loads in well under a millisecond.
Multi-word places use ``_`` for spaces.
"""

from __future__ import annotations

import re

from .graph_words import (
    CONTRACT_ROLES,
    DEMONYM_WORDS,
    GENERIC_ACRONYMS,
    GENERIC_SPAN_WORDS,
    RECORD_KIND_WORDS,
    SECTOR_WORDS,
)


def _words(text: str) -> frozenset[str]:
    return frozenset(w.replace("_", " ") for w in text.split())


def _words_upper(text: str) -> list[str]:
    return [w.upper() for w in text.split()]


# Function words: never part of a noun phrase, trimmed from the edges of capitalised spans.
STOPWORDS = _words("""
a an the this that these those there here it its it's he she they them their theirs his her
hers him we us our ours you your yours i me my mine who whom whose which what when where why
how all any both each every few many more most other some such no nor not only own same so
than too very can will just should would could may might must shall of and or but if then
else for to from in on at by with about against between into through during before after
above below up down out off over under again further once also as is are was were be been
being have has had having do does did doing because until while per via etc ie eg vs one two
three four five six seven eight nine ten yes ok okay hi hello dear thanks thank please new
twice again already still now soon often never always
""")

# Ordinary English words that are not entities on their own when capitalised (headings,
# sentence starts, labels such as "Status:" or "Customer:").
COMMON_WORDS = STOPWORDS | _words("""
account accounts action actions agent agreement amount analysis answer application approval
approvals approved area article attachment audit available background balance billing board
budget business call calls case cases category change changes chapter check client clients
closed closing comment comments company compliance conclusion confidential contact content
contents contract contracts copy cost costs customer customers data date day days decision
default definition definitions delivery department description design details development
document documents draft due email employee employees end error event events example
exceptions expense expenses fact facts feature features figure file files final
form general goal goals group guide guidelines help high history id important incident
information input instructions introduction invoice invoices issue issues item items key
level limit list low manager meeting meetings member members message method middle minutes
model module monthly name names next note notes notice number objective objectives open
opening order orders organization organisation overview owner page pages part parties
party payment payments period plan plans point policy policies price priority problem
procedure procedures process product products project projects purpose quarter question
questions rate reason record records reference references region release report reports
request requests requirements resolution resolved response result results review risk role
roles rule rules sale sales scope section security service services session settings
severity shipped site size source start state statement status step steps subject summary
supplier support system systems table task tasks team teams term terms test tier time title
today topic total training type update updated user users value values vendor version
view warning week weekly work year yearly yes total subtotal unknown other misc
general standard internal external final initial current previous following above below
however therefore otherwise meanwhile moreover finally first second third last next
""")

# Nationalities, demonyms and languages ("Kenyan rollout", "in English"): never a name alone.
DEMONYMS = _words(DEMONYM_WORDS)
# Adjectives and generic nouns: a capitalised span made only of these and COMMON_WORDS is not
# a name ("Economy Class", "Large Conference Room", "Great Weekend").
GENERIC_WORDS = _words(GENERIC_SPAN_WORDS) | _words(CONTRACT_ROLES)
SECTORS = _words(SECTOR_WORDS)
RECORD_KINDS = _words(RECORD_KIND_WORDS)

MONTHS = _words("""
january february march april may june july august september october november december
jan feb mar apr jun jul aug sep sept oct nov dec
""")
WEEKDAYS = _words("""
monday tuesday wednesday thursday friday saturday sunday mon tue tues wed thu thur thurs fri sat sun
""")
HEADING_WORDS = _words("""
table figure fig page section note notes appendix chapter annex exhibit schedule part
item step slide image chart diagram attachment enclosure contents index summary
""")
# Never kept as a single-token span (beyond COMMON_WORDS): time words and the like.
SPAN_STOP = (
    MONTHS
    | WEEKDAYS
    | HEADING_WORDS
    | _words("""
am pm utc gmt ist est pst cet mr mrs ms dr shri smt sir madam miss prof
""")
)

# Lowercase words allowed inside a capitalised span ("Bank of India", "Johnson & Johnson").
CONNECTORS = _words("""
of and & de van von der da la le du del di y bin bint binti ibn al el dos das della ter ten zu
""")

# Legal suffixes: an org-type signal, and dropped from org keys by normalisation.
ORG_LEGAL_SUFFIXES = _words("""
inc incorporated ltd limited llc llp lp plc gmbh ag sa sas sarl bv nv oy ab as spa srl kk
co company corp corporation pvt private pte pty
""")
# Words that make a span an organisation when they end it (kept in the key).
ORG_HEAD_WORDS = _words("""
bank university hospital group holdings foundation institute college school trust
association society council ministry agency authority board bureau commission
laboratories labs systems solutions technologies technology logistics industries
partners ventures capital insurance airlines airways motors pharma pharmaceuticals
enterprises services consulting software analytics media telecom energy foods retail
""")
# "X of Y" stays one name after these words ("Bank of India", "University of Toronto").
OF_HEADS = _words("""
department office republic kingdom state city museum school church district county province
""")
HONORIFICS = _words("""
mr mrs ms miss dr prof professor sir madam shri smt sri kumari mx sheikh sheikha
""")

_LAZY: dict[str, frozenset[str]] = {}


def _packed(*texts: str) -> frozenset[str]:
    return frozenset(w.replace("_", " ") for text in texts for w in text.split())


def layer_data(module: str, *names: str) -> str:
    """Packed word lists of the guardrails layer's PII lexicons (``ner_names_world``,
    ``ner_places``, ...) when that layer is installed, else ``""``.

    Data only: the module file is executed on its own (it holds string constants), without
    importing the guardrails package or anything it depends on, so the graph extractor has
    no code dependency on a higher layer and works the same without it (smaller lists)."""
    key = f"layer:{module}"
    cached = _LAYER.get(key)
    if cached is None:
        cached = _LAYER[key] = _load_layer_module(module)
    return " ".join(str(cached.get(n, "")) for n in names)


_LAYER: dict[str, dict[str, object]] = {}


def _load_layer_module(module: str) -> dict[str, object]:
    import importlib.util
    import os

    for package in ("nexus.guardrails", "nexus_guardrails"):
        try:
            spec = importlib.util.find_spec(package)
        except (ImportError, ValueError):
            continue
        for folder in (spec.submodule_search_locations or []) if spec else []:
            path = os.path.join(folder, f"{module}.py")
            if not os.path.isfile(path):
                continue
            namespace: dict[str, object] = {"__name__": f"_nexus_graph_data_{module}"}
            try:
                with open(path, encoding="utf-8") as fh:
                    exec(compile(fh.read(), path, "exec"), namespace)
            except Exception:
                return {}
            return {k: v for k, v in namespace.items() if k.isupper() and isinstance(v, str)}
    return {}


def plain(fold: str) -> str:
    """``fold`` without diacritics ("josé" -> "jose") for lexicon lookups."""
    if fold.isascii():
        return fold
    import unicodedata

    return "".join(c for c in unicodedata.normalize("NFKD", fold) if not unicodedata.combining(c))


def given_names() -> frozenset[str]:
    """Casefolded given names: about 3,000 here (``graph_names``) plus about 7,000 more from
    the guardrails layer's PII lists when installed (``layer_data``); built on first use."""
    names = _LAZY.get("given")
    if names is None:
        from .graph_names import PACKED

        extra = layer_data("ner_names_south_asia", "PACKED")
        extra += " " + layer_data("ner_names_world", "PACKED")
        names = _LAZY["given"] = _packed(PACKED, extra)
    return names


def ambiguous_names() -> frozenset[str]:
    """Given names that are also ordinary words or places ("Grant", "Victoria")."""
    names = _LAZY.get("given_ambiguous")
    if names is None:
        from .graph_names import AMBIGUOUS

        extra = layer_data("ner_names_world", "AMBIGUOUS")
        names = _LAZY["given_ambiguous"] = _packed(AMBIGUOUS, extra)
    return names


def places() -> frozenset[str]:
    """Casefolded places: about 3,700 here (``graph_places``) plus the guardrails layer's
    place list when installed; built on first use."""
    found = _LAZY.get("places")
    if found is None:
        from .graph_places import CITIES, PACKED, TOWNS

        extra = layer_data("ner_places", "PACKED", "AMBIGUOUS")
        found = _LAZY["places"] = _packed(PACKED, CITIES, TOWNS, extra)
    return found


def ambiguous_places() -> frozenset[str]:
    """Places that are also words, names or brands ("Reading", "Phoenix"): need a cue."""
    found = _LAZY.get("places_ambiguous")
    if found is None:
        from .graph_places import AMBIGUOUS

        extra = layer_data("ner_places", "AMBIGUOUS")
        found = _LAZY["places_ambiguous"] = _packed(AMBIGUOUS, extra)
    return found


def surnames() -> frozenset[str]:
    """Casefolded surnames (strong ones only) from the guardrails layer when installed."""
    found = _LAZY.get("surnames")
    if found is None:
        weak = _packed(layer_data("ner_surnames", "WEAK"))
        found = _LAZY["surnames"] = _packed(layer_data("ner_surnames", "PACKED")) - weak
    return found


def lower_stop() -> frozenset[str]:
    """Names and places that are also English words (guardrails layer, when installed)."""
    found = _LAZY.get("lower_stop")
    if found is None:
        found = _LAZY["lower_stop"] = _packed(layer_data("ner_lowercase", "STOP"))
    return found


def __getattr__(name: str) -> frozenset[str]:  # GIVEN_NAMES / PLACES (3.3.0 names), lazily
    if name == "GIVEN_NAMES":
        return given_names()
    if name == "PLACES":
        return places()
    raise AttributeError(name)


# Job titles and roles: a span that names a role is not an entity ("Chief Risk Officer").
ROLE_HEADS = _words("""
officer president director manager head chair chairman chairperson chairwoman lead secretary
treasurer counsel controller administrator coordinator specialist analyst engineer architect
consultant executive vp svp evp ceo cfo cto coo cio ciso cmo dpo partner associate intern
""")
ROLE_FIRST = _words("""
chief head vice deputy assistant associate senior junior acting interim vp svp evp avp
""")

# Words that start a sentence without being part of the name after them ("Today Acme ...").
SENTENCE_LEAD = STOPWORDS | _words("""
additionally also anyway ask assigned attendees attn call cc check congratulations contact
currently date dear earlier email finally first fortunately from furthermore fw fwd fyi
hello hence here hi however important instead join last later meanwhile meet moreover next
no note now otherwise overall owner per please present re read recently regards reminder
review second see send sent still subject thank thanks then there therefore third thus today
tomorrow unfortunately update urgent use visit welcome yes yesterday yet
""")
# ALL-CAPS tokens that are not entities on their own (currencies, units, generic acronyms).
ACRONYM_STOP = frozenset(
    _words_upper("""
aka am and api as asap at bcc by cc crm csv eod erp eta etc eur faq for fw fyi gbp gmt hr id
ii iii in inr is ist it iv jpy kpi mfa mou mtd n/a na nda no note of ok on or pdf pm po ps
qa qtd re rfp rfq sku sla sow sso tbd the to todo ui url usd utc ux vpn vs yes ytd
""")
) | frozenset(_words_upper(GENERIC_ACRONYMS))

# Auxiliaries and frequent verbs: a noun phrase never contains one.
VERBS = _words("""
is are was were be been being am has have had do does did will would shall should can could
may might must get gets got make makes made take takes took give gives gave use uses used
see sees saw say says said go goes went come comes came know knows knew think thinks find
finds found want wants need needs needed include includes included provide provides
provided require requires required apply applies applied keep keeps kept agree agrees agreed
report reports reported confirm confirmed explain explains explained answer answered raise
raised review reviewed approve approves approved publish publishes published track tracked
""") | frozenset(
    w + s
    for w in _words("""
continue remain happen occur start stop follow help show mean seem become run set put ask try
move live believe hold bring write sit stand lose pay meet lead understand watch create spend
grow walk win offer remember consider appear buy wait serve send expect build stay fall reach
decide pull return hope develop reach carry break receive cause ensure contain describe allow
reduce increase decrease improve prevent manage cover choose affect arrive depend exist fail feel
""")
    for s in ("", "s")
)
NOUN_SUFFIXES = (
    "tion",
    "sion",
    "ment",
    "ity",
    "ance",
    "ence",
    "ness",
    "ship",
    "ism",
    "ist",
    "er",
    "or",
    "ing",
    "age",
    "ure",
    "cy",
    "ics",
    "ogy",
    "ory",
    "ant",
    "ent",
)
ADJ_SUFFIXES = ("ly", "ful", "ous", "ive", "able", "ible", "al", "ic", "less", "ish")

# Column / table name lexicon -> entity type (first match wins; tokens of the name are matched).
COLUMN_TYPES: tuple[tuple[re.Pattern[str], str], ...] = tuple(
    (re.compile(p), t)
    for p, t in (
        (
            r"^(assignee|owner|reporter|agent|author|manager|employee|contact|contact_name|"
            r"person|user_name|username|creator|requester|approver|lead|rep|salesperson|"
            r"technician|doctor|physician|teacher|student|staff|member|engineer|employees|"
            r"people|persons|users|contacts|staffs|members)$",
            "person",
        ),
        (
            r"^(customer|customers|account|accounts|company|companies|vendor|vendors|supplier|"
            r"suppliers|client|clients|org|orgs|organisation|organization|organisations|"
            r"organizations|partner|partners|merchant|merchants|employer|carrier|bank|brand|"
            r"manufacturer|distributor|tenant|payer|payee)$",
            "org",
        ),
        (
            r"^(city|cities|region|country|countries|warehouse|warehouses|site|sites|location|"
            r"locations|state|province|branch|office|store|stores|plant|facility|port|"
            r"district|zone|territory|address_city)$",
            "place",
        ),
        (
            r"^(product|products|sku_name|plan|plans|item_name|service|model|device|asset|"
            r"material|part_name|brand_name|app|application)$",
            "product",
        ),
        (
            r"^(project|projects|epic|epics|repo|repos|repository|space|program|programme|"
            r"initiative|campaign|board|component)$",
            "project",
        ),
        (r"^(department|team|division|unit|group|squad|function|business_unit)$", "org"),
    )
)
# Enum-like column names: low-cardinality values become attributes, not entities.
ENUM_COLUMN = re.compile(
    r"(^|_)(status|state|priority|type|stage|severity|kind|category|"
    r"tier|level|segment|flag|mode|phase|rating|grade|gender)($|_)"
)
# Name-or-title columns that name a row (row entities).
TITLE_COLUMN = re.compile(
    r"^(name|title|full_name|display_name|company_name|customer_name|"
    r"account_name|vendor_name|product_name|project_name|label|subject|"
    r"summary|[a-z]+_name)$"
)
# Columns whose values are personal data: never entity names, whatever the classifier says.
PII_COLUMN = re.compile(
    r"(^|_)(email|e_mail|phone|mobile|tel|telephone|fax|ssn|pan|aadhaar|"
    r"passport|license|licence|card|iban|swift|account_number|acct|dob|"
    r"birth|salary|password|secret|token|ip|address|street|zip|postcode|"
    r"postal)($|_)"
)
PII_KINDS = frozenset(
    {
        "email",
        "phone",
        "ssn",
        "government_id",
        "national_id",
        "passport",
        "card",
        "credit_card",
        "account",
        "account_number",
        "iban",
        "aadhaar",
        "pan",
        "address",
        "ip_address",
        "secret",
        "api_key",
        "jwt",
        "dob",
        "date_of_birth",
        "person_name",
    }
)


def column_type(name: str) -> str:
    """The entity type a column or table name suggests (``entity`` when none)."""
    folded = re.sub(r"[^a-z0-9]+", "_", name.casefold()).strip("_")
    candidates = [folded]
    parts = [p for p in folded.split("_") if p]
    if parts:
        candidates.append(parts[-1])
        if parts[-1] in ("id", "name", "code", "key", "no", "ref") and len(parts) > 1:
            candidates.append(parts[-2])
        candidates.append(parts[0])
    for candidate in candidates:
        for pattern, entity_type in COLUMN_TYPES:
            if pattern.match(candidate):
                return entity_type
    return "entity"
