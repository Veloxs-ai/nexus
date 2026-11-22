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

"""Context rules of the lexicon detector that do not need capitalisation (standard library).

* lowercase chat ("hey priya can u ask ramesh to call back from pune"): a lowercase word is a
  name only when it is a given name that is not also an English or chat word and a cue sits
  next to it ("hey", "ask", "tell", "@", "said", "will"); a lowercase place needs a place cue
  ("from", "in", "to", "office");
* key/value fields (``name: Ravi``, ``customer_name=ravi kumar``, ``"city": "Pune"``): the key
  says which type the value is;
* signature blocks: the name line after "Regards," / "Thanks," / "Cheers," and a place that
  starts one of the next two lines ("Dublin Office").

Every rule scans the text once with bounded patterns (linear in its length).
"""

from __future__ import annotations

import re
from collections.abc import Callable

from . import ner_words as W

Span = tuple[int, int, str]

_WORD = re.compile(r"[^\W\d_]+(?:['’](?!s\b)[^\W\d_]+)*")
_words = W._words

NAME_BEFORE = _words("""
hey hi hello hii hiii helo heya hiya yo dear thanks thank thx tnx ty ask asked asking tell told
telling call called calling ping pinged message messaged msg text texted remind reminded inform
informed cc with meet met contact by to for and or is am via did does do can could will
would should has have was
""")
NAME_AFTER = _words("""
said says will is was has had can could would should called calls asked told wants wanted
needs needed here sir ji bhai da garu madam maam mam sent replied mentioned and or
""")
PLACE_BEFORE = _words("""
from in to at near via visiting reach reached reaching towards toward around outside inside
into based shifted moved relocating relocated back left leaving landed land flying fly lives
live living stay staying stays
""")
PLACE_AFTER = _words("office branch side airport station city area team hub warehouse plant")
# Chat words, Hinglish words and kinship terms that are also listed as given names or places.
CHAT_STOP = _words("""
u ur pls plz tmrw tmr asap lol btw omg idk brb ok okay yes no hey abhi kal aaj bas haan nahi
acha accha theek yaar bhai didi ji sab kaam ghar chal chalo kya kyu kaise hai ho tha toh bhi
aur par pe mein se ko ka ki ke wala wali sir madam maam bro dude guys team all everyone sona
raja rani beta baba mama papa mummy mom dad aunty uncle nana nani dada dadi chacha mausi bhaiya
bhaiyya anna akka amma appa thambi guru babu bhabhi jiju sahab saab boss
""")


def _gap_ok(text: str, a: int, b: int) -> bool:
    """Words at a..b are in one clause: only spaces, commas or '@' between them."""
    gap = text[a:b]
    return len(gap) <= 3 and gap.strip(" \t,@") == ""


def _place_at(
    toks: list, i: int, text: str, places: frozenset, amb: frozenset, stop: frozenset
) -> int:
    """End index (exclusive) of the longest lowercase place of 1-3 words at ``i``, else 0."""
    for k in (3, 2, 1):
        seq = toks[i : i + k]
        if len(seq) < k or any(not t[3].islower() for t in seq):
            continue
        if any(text[seq[j][1] : seq[j + 1][0]] != " " for j in range(k - 1)):
            continue
        name = " ".join(t[2] for t in seq)
        if name in places and name not in amb and (k > 1 or name not in stop):
            return i + k
    return 0


def lowercase_spans(text: str, common: frozenset[str]) -> list[Span]:
    """Names and places written in lowercase, typed only next to a cue (module doc)."""
    if not any(c.islower() for c in text):
        return []
    given, places, amb_places = W.given_names(), W.places(), W.ambiguous_places()
    surnames, stop = W.surnames(), W.lower_stop()
    toks = [(m.start(), m.end(), m.group().casefold(), m.group()) for m in _WORD.finditer(text)]
    n = len(toks)

    def word(j: int) -> str:  # token j's fold when it is in the same clause as token j-1/j+1
        return toks[j][2] if 0 <= j < n else ""

    def near(a: int, b: int) -> bool:  # tokens a < b adjacent within one clause
        return a >= 0 and b < n and _gap_ok(text, toks[a][1], toks[b][0])

    out: list[Span] = []
    last_end, last_type = -10, ""
    i = 0
    while i < n:
        s, _, fold, raw = toks[i]
        if not raw.islower() or fold in common or fold in CHAT_STOP:
            i += 1
            continue
        prev = word(i - 1) if near(i - 1, i) else ""
        between = text[last_end:s] if 0 <= s - last_end <= 6 else "x"
        chained = between.strip(" ,") in ("and", "or", "&", "")
        place_end = _place_at(toks, i, text, places, amb_places, stop)
        if place_end:
            nxt = word(place_end) if near(place_end - 1, place_end) else ""
            if prev in PLACE_BEFORE or nxt in PLACE_AFTER or (chained and last_type == "location"):
                last_end, last_type = toks[place_end - 1][1], "location"
                out.append((s, last_end, "location"))
                i = place_end
                continue
        if len(fold) > 2 and fold in given and fold not in stop and not place_end:
            j = i + 1  # surname / second name: "anil kumar"
            while j < n and j <= i + 2 and toks[j][3].islower() and near(j - 1, j):
                f = toks[j][2]
                if f in stop or f in common or f in CHAT_STOP or not (f in surnames or f in given):
                    break
                j += 1
            end = toks[j - 1][1]
            nxt = word(j) if near(j - 1, j) else ""
            vocative = (i == 0 or "\n" in text[toks[i - 1][1] : s]) and text[end : end + 1] in ",:"
            cued = (
                (s > 0 and text[s - 1] == "@")
                or prev in NAME_BEFORE
                or nxt in NAME_AFTER
                or text[end : end + 2] in ("'s", "’s")
                or (chained and last_type == "person")
            )
            if cued or (vocative and end < len(text)):
                out.append((s, end, "person"))
                last_end, last_type = end, "person"
                i = j
                continue
        i += 1
    return out


# --- key/value fields ------------------------------------------------------------------

_FIELD = re.compile(
    r"(?<![A-Za-z])([A-Za-z]{1,30}(?:[ _.-][A-Za-z]{1,20}){0,2})[\"']?[ \t]*[:=][ \t]*[\"']?"
    r"([^\n\"',;|{}\[\]<>:=()0-9]{1,60})"
)
NAME_KEYS = _words("""
name full_name fullname first_name firstname last_name lastname given_name surname family_name
middle_name customer_name contact_name client_name patient_name employee_name person_name
applicant_name holder_name account_holder nominee_name guardian_name father_name mother_name
spouse_name emp_name cust_name student_name candidate_name driver_name owner_name agent_name
""")
ROLE_KEYS = _words("""
customer client contact patient employee applicant beneficiary nominee guardian father mother
spouse husband wife son daughter witness sender recipient requester requestor approver driver
doctor physician technician author owner assignee reporter agent caller attn signed_by
prepared_by reviewed_by approved_by raised_by reported_by assigned_to from to cc
""")
NOT_NAME_KEYS = _words("""
user_name username host_name hostname file_name filename company_name org_name business_name
product_name project_name account_name vendor_name merchant_name store_name team_name app_name
device_name plan_name brand_name item_name street_name building_name bank_name branch_name
city_name place_name display_name domain_name table_name column_name field_name
""")
PLACE_KEYS = _words("""
city town village location place origin destination hometown birthplace place_of_birth
district state region country area locality neighbourhood neighborhood branch site venue
airport pickup drop pickup_location drop_location address_city city_name state_name
location_name base based_in residence native_place from_city to_city current_city
""")
EMPTY_VALUES = _words("""
unknown unassigned none null nil na tbd pending self admin system support team all any other
n/a not_available yes no true false open closed active inactive default main head
""")


def field_spans(
    text: str, common: frozenset[str], is_org: Callable[[list[str]], bool]
) -> list[Span]:
    """Values of name and place fields (``name: Ravi Kumar``, ``"city": "Pune"``)."""
    if ":" not in text and "=" not in text:
        return []
    given, surnames, places = W.given_names(), W.surnames(), W.places()
    out: list[Span] = []
    for m in _FIELD.finditer(text):
        key = re.sub(r"[ .-]", "_", m.group(1).casefold())
        if key in NOT_NAME_KEYS:
            continue
        named = key in NAME_KEYS or (key.endswith("_name") and key not in NOT_NAME_KEYS)
        role, placed = key in ROLE_KEYS, key in PLACE_KEYS
        if not (named or role or placed):
            continue
        raw = m.group(2)
        vs = m.start(2) + len(raw) - len(raw.lstrip())
        cut = re.search(r"\s(?:-|–|—)\s|\s{2,}|\.\s|\s(?:and|or|from|at|in)\s", raw.strip())
        value = raw.strip()[: cut.start()] if cut else raw.strip()
        value = value.rstrip(" .")
        words = _WORD.findall(value)
        folds = [w.casefold() for w in words]
        if not 1 <= len(words) <= 4 or len(value) < 2 or " ".join(folds) in EMPTY_VALUES:
            continue
        if all(f in common or f in EMPTY_VALUES for f in folds) or is_org(folds):
            continue
        ve = vs + len(value)
        if placed:
            if any(f in W.STREET_HEADS for f in folds) or folds[-1] in W.NATIONALITIES:
                continue
            if " ".join(folds) in places or all(w[0].isupper() for w in words):
                out.append((vs, ve, "location"))
            continue
        evidence = any(f in given or f in surnames for f in folds)
        caps = all(w[0].isupper() for w in words)
        loose = named and (evidence or caps or len(words) <= 3)
        strict = role and (evidence or (caps and len(words) >= 2))
        if loose or (strict and not any(f in common for f in folds)):
            out.append((vs, ve, "person"))
    return out


# --- signature blocks --------------------------------------------------------------------

_CLOSING = re.compile(
    r"(?im)^[ \t]*(?:(?:best|kind|warm|warmest|many)[ \t]+(?:regards|wishes|thanks)|regards|"
    r"thanks(?:[ \t]+(?:and|&)[ \t]+regards)?|thank[ \t]+you|cheers|sincerely|"
    r"yours[ \t]+(?:sincerely|truly|faithfully)|best|br|rgds|thx|warmly|respectfully|--|—)"
    r"[ \t]*[,.!]?[ \t]*\n"
)
_LINE = re.compile(r"[ \t]*([^\n]*)\n?")


def signature_spans(
    text: str, common: frozenset[str], is_org: Callable[[list[str]], bool]
) -> list[Span]:
    """The name line after a closing ("Regards,") and a place starting one of the next two."""
    out: list[Span] = []
    places, amb = W.places(), W.ambiguous_places()
    for m in _CLOSING.finditer(text):
        pos, lines = m.end(), []
        while pos < len(text) and len(lines) < 3:
            line = _LINE.match(text, pos)
            if line is None or line.end() == pos:
                break
            if line.group(1).strip():
                lines.append((line.start(1), line.group(1)))
            pos = line.end()
        if not lines:
            continue
        start, body = lines[0]
        head = re.split(r"\s[|,–—-]\s|,|\|", body, maxsplit=1)[0].rstrip()
        words = _WORD.findall(head)
        folds = [w.casefold() for w in words]
        if (
            1 <= len(words) <= 4
            and all(ch.isalpha() or ch in " .'’-" for ch in head)
            and all(w[0].isupper() for w in words)
            and not any(f in common or f in W.ORG_TAILS for f in folds)
            and not is_org(folds)
            and not (len(words) == 1 and folds[0] in places)
        ):
            out.append((start, start + len(head), "person"))
        for ls, body in lines[1:]:
            words = _WORD.findall(body)[:3]
            for k in (3, 2, 1):
                name = " ".join(w.casefold() for w in words[:k])
                if len(words) >= k and name in places and name not in amb:
                    if body.startswith(" ".join(words[:k])) and words[0][0].isupper():
                        out.append((ls, ls + len(" ".join(words[:k])), "location"))
                    break
    return out
