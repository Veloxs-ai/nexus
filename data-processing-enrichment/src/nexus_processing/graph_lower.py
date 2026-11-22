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

"""Lowercase mentions of known names in chat-style text ("grafana shows 500s", "ping priya").

``lowercase_pass`` runs after the capitalised pass on one chunk and only looks at lowercase
tokens that capitalisation rules cannot see. A token is a mention only when it is:

* a known organisation or product of the lexicon (``graph_orgs``) that is not also an English
  word ("datadog", "infosys", "pagerduty"); a known name that is also a word ("slack",
  "stripe", "react") needs a version number or a product cue after it ("react 17",
  "stripe webhooks");
* a given name that is not also a word or a place, next to a person cue: a speaker label
  ("priya: ..."), a greeting or request before it ("hey", "ping", "ask", "cc", "@"), a verb
  or possessive after it ("deepa can you", "rahul's on it", "sunil from infosys said"), or
  parentheses ("on-call (ana)").

Confidence 0.7, method ``lower``. Linear: one set lookup per lowercase token.
"""

from __future__ import annotations

import re
from typing import Any

from .graph_lexicon import (
    COMMON_WORDS,
    STOPWORDS,
    VERBS,
    ambiguous_names,
    ambiguous_places,
    given_names,
    lower_stop,
    places,
)
from .graph_resolve import normalise_name
from .graph_tokens import JOIN, START, Tokens
from .graph_typing import lexicon

__all__ = ["lowercase_pass"]


def _set(text: str) -> frozenset[str]:
    return frozenset(text.split())


# Known organisations and products that are also English words or names: lowercase, they
# need a version number or a cue word after them.
_WORD_BRANDS = _set("""
slack notion zoom intercom tableau looker snowflake redshift spark airflow excel outlook
telegram chrome safari windows pixel azure concur acrobat illustrator loom copilot gemini
bard eclipse postman swagger sentry bamboo vault consul nomad segment amplitude stitch
basecamp greenhouse lever gusto rippling ramp tally gong outreach apollo workday cassandra
kafka prometheus docker meta apple amazon oracle shell sony canon ford tata wise visa stripe
ikea puma merck continental snap grab lyft disney bloomberg reddit twitter emirates react
angular swift rust ruby pandas spring rails flask java python go dart julia elixir mint
square
""")
_VERSION = re.compile(r"^v?\d+(?:\.\d+)*[a-z]?$")
_BEFORE = _set("""
hey hi hello thanks thank thx ty ping pinged ask asked tell told cc remind call called
message messaged dm email emailed meet met with and or by for to via
""")
_AFTER = _set("""
said says will would can could is was has had wants wanted needs needed asked told replied
mentioned confirmed thinks agreed shared sent from and or
""")
_CHAT_STOP = _set("""
u ur pls plz tmrw lol btw omg idk brb ok okay yes no hey yeah yep nope bro dude guys team
all everyone folks sir madam boss prod dev qa ops
""")
_TABLE: list[dict[str, str]] = []


def _table() -> dict[str, str]:
    """fold -> "org" / "product" / "brand:<type>" (needs a cue) / "person"."""
    if _TABLE:
        return _TABLE[0]
    lex = lexicon()
    words = COMMON_WORDS | STOPWORDS | VERBS | _CHAT_STOP
    stop = lower_stop()
    out: dict[str, str] = {}
    amb_names, amb_places, all_places = ambiguous_names(), ambiguous_places(), places()
    for fold in given_names():
        if len(fold) > 2 and fold not in amb_names and fold not in words and fold not in all_places:
            out[fold] = "name?" if fold in stop else "person"  # "ana", "will": a strong cue
    for etype, names in (("product", lex.known_products), ("org", lex.known_orgs)):
        for fold in names:
            if " " in fold or len(fold) < 4 or not fold.replace("-", "").replace(".", "").isalnum():
                continue
            ambiguous = fold in _WORD_BRANDS or fold in words or fold in stop or fold in amb_places
            out[fold] = f"brand:{etype}" if ambiguous or fold in out else etype
    for fold, kind in list(out.items()):  # possessives: "rahul's on it"
        out[fold + "'s"] = out[fold + "’s"] = kind
    _TABLE.append(out)
    return out


def lowercase_pass(tk: Tokens, covered: bytearray, hits: list, acc: Any) -> None:
    """Typed mentions of lowercase known names (module doc); marks their tokens covered."""
    table = _table()
    if table.keys().isdisjoint(tk.toks):  # lowercase tokens only: table keys are lowercase
        return
    toks, folds, flags, text, n = tk.toks, tk.folds, tk.flags, tk.text, len(tk)
    blocked = tk.blocked
    cues = lexicon().next_cues
    for i in [i for i, t in enumerate(toks) if t in table]:
        tok = toks[i]
        if covered[i] or not tok[0].islower() or i in blocked:
            continue
        fold = folds[i]
        owner = fold[:-2] if fold.endswith(("'s", "’s")) else fold
        kind = table[fold]
        nxt = i + 1 < n and bool(flags[i + 1] & JOIN)
        after = folds[i + 1] if nxt else ""
        if kind == "person" or kind == "name?":
            if not _person_cue(tk, i, owner != fold, after, kind == "person"):
                continue
            etype = "person"
        elif kind.startswith("brand:"):
            if not (nxt and (_VERSION.match(after) or cues.get(after) in ("product", "org"))):
                continue
            etype = kind[6:]
        else:
            etype = kind
        s = tk.starts[i]
        e = s + len(owner)
        if etype == "product" and nxt and _VERSION.match(after) and after[:1].isdigit():
            e = tk.ends[i + 1]  # "react 17", "java 21": the versioned name
            covered[i + 1] = 1
        surface = text[s:e]
        key = normalise_name(surface, entity_type=etype)
        if not key:
            continue
        covered[i] = 1
        acc.entity(etype, key, surface.title() if etype == "person" else surface)
        hits.append((i, etype, key, s, e, "lower", 0.7))


def _person_cue(tk: Tokens, i: int, possessive: bool, after: str, weak_ok: bool) -> bool:
    if weak_ok and (possessive or after in _AFTER):
        return True
    text, s, e = tk.text, tk.starts[i], tk.ends[i]
    if text[e : e + 1] == ":" and (i == 0 or tk.flags[i] & START):
        return True  # a speaker label: "priya: did anyone hear back"
    if text[s - 1 : s] == "@" or (text[s - 1 : s] == "(" and text[e : e + 1] == ")"):
        return True  # "@priya", "on-call (ana)"
    if not weak_ok:
        return False
    if i and tk.flags[i] & JOIN and tk.folds[i - 1] in _BEFORE:
        return True  # "ping priya", "thanks rahul"
    return text[e : e + 1] == "," and (i == 0 or bool(tk.flags[i] & START))  # "deepa, can you"
