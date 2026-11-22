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

"""Word lists for the lexicon person/location detector (data only, casefolded, packed).

Given names, places, honorifics and organisation words are shared with the knowledge-graph
entity typing (``nexus.processing.graph_lexicon``); this module adds only what PII detection
needs on top: surname endings, cue words and the role labels that precede a name in records
and tickets ("Customer Ravi Shankar", "Patient John Matthews").
"""

from __future__ import annotations

# Endings that mark a surname in many naming traditions ("Bondarenko", "Kowalczyk").
SURNAME_ENDINGS = (
    "enko", "chuk", "czyk", "wicz", "ski", "ska", "sky", "ova", "eva", "ovich", "evich", "escu",
    "poulos", "opoulos", "akis", "idis", "oglu", "sson", "ssen", "yan", "ian", "dze", "shvili",
    "berg", "stein", "mann", "baum", "appa", "amma", "swamy", "swami", "murthy", "nathan",
    "raman", "esan", "wala", "walla",
)

# Capitalised role and record labels that precede a name without being part of it.
ROLE_LABELS = """
customer customers caller agent patient employee student driver candidate applicant
policyholder beneficiary nominee guardian tenant owner requester reporter assignee
consultant engineer technician manager director officer executive rep representative
user member client vendor witness spouse mother father son daughter author reviewer
approver contact contacts name attendee attendees speaker host hosts team ticket
escalation account holder sales field born signed regards thanks best dear hi hello hey
cc attn to from by with and for welcome kindly please ask call email ping thank
"""

# Compass words that join a place into a region ("South India", "Northern Ireland").
COMPASS = """
north south east west central northern southern eastern western northeast northwest
southeast southwest north-east north-west south-east south-west upper lower greater
"""

# Words that, right before a capitalised name, say it is a person ("my name is ...").
PERSON_CUES = (
    "my name is", "name is", "this is", "i am", "i'm", "signed by", "assigned to",
    "reported by", "raised by", "requested by", "approved by", "prepared by", "reviewed by",
    "hosted by", "escalated to", "contact", "spoke with", "spoke to", "met with", "call with",
    "meeting with", "attn", "dear", "hi", "hello", "hey", "thanks", "thank you", "regards",
)

# Verbs that follow a person far more often than an organisation, product or place
# ("Somnath Ganguly said ...", "Mateus Rocha visited ...").
PERSON_VERBS = """
said says asked asks told tells wrote writes replied replies mentioned mentions explained
called calls visited visits joined joins lives lived emailed messaged texted phoned
complained complains promised informed thinks thought feels felt wants wanted prefers
cleared reviewed agreed shared presented spoke speaks met meets travelled traveled
"""

