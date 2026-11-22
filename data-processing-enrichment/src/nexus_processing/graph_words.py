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

"""Generic words for the text extractor's span vetoes (data only, casefolded, packed).

Turned into sets by ``graph_lexicon``. None of these is an entity on its own; a capitalised
span made only of them (and ``COMMON_WORDS``) is a heading, a label or a phrase written in
title case ("Economy Class", "Large Conference Room", "Have a Great Weekend").
"""

from __future__ import annotations

# Nationalities, demonyms and languages ("the Kenyan rollout", "an update in English").
DEMONYM_WORDS = """
american british english french german spanish italian portuguese dutch swedish norwegian
danish finnish polish russian ukrainian greek turkish arabic arab persian hebrew chinese
mandarin cantonese japanese korean vietnamese thai indonesian malay filipino tagalog indian
hindi urdu bengali bangla tamil telugu kannada malayalam marathi gujarati punjabi odia
nepali sinhala sinhalese pakistani bangladeshi african nigerian kenyan ghanaian ethiopian
egyptian moroccan swahili zulu xhosa yoruba igbo hausa amharic mexican brazilian argentine
argentinian colombian chilean peruvian canadian australian irish scottish welsh european
asian latin latino hispanic swiss austrian belgian czech hungarian romanian serbian croatian
bulgarian israeli iranian iraqi saudi emirati qatari omani kuwaiti singaporean malaysian
lebanese jordanian syrian afghan tanzanian ugandan rwandan south_african new_zealander
"""

# Adjectives, quantities and generic nouns written in title case in headings, signs and
# greetings. Not departments, products or places on their own.
GENERIC_SPAN_WORDS = """
great good best better nice happy merry warm kind lovely wonderful amazing awesome big small
large little huge medium main major minor full half early late annual quarterly daily
upcoming recent latest long short top bottom upper lower special premium economy basic
regular extra free paid weekend weekends holiday holidays vacation break room rooms class
classes conference lounge hall seat seats meal meals ticket tickets purchase alert
alerts reminder reminders announcement announcements recap highlights highlight agenda
takeaways takeaway kickoff kick-off welcome congratulations wishes greetings regards
lunch dinner breakfast coffee party celebration day night morning afternoon evening
order orders receipt receipts invoice statement estimate quote quotation proposal
action next steps step out office leave sick parental maternity paternity
yoy qoq mom wow ytd poc saas paas iaas wi-fi wifi e-mail email
"""

# Parties named by their role in a contract or a form ("the Licensor", "the Licensee").
CONTRACT_ROLES = """
licensor licensee lessor lessee landlord tenant buyer seller purchaser borrower lender
guarantor assignor assignee discloser recipient contractor subcontractor consultant
employer employee grantor grantee transferor transferee mortgagor mortgagee insurer
insured policyholder beneficiary claimant respondent appellant plaintiff defendant
"""

# Generic business and technical acronyms: never an entity on their own ("NPS", "SIM").
GENERIC_ACRONYMS = """
nps csat ces arr mrr acv tcv roi roas cac ltv okr okrs kpis slo slos sli rca rto rpo mttr
mtbf eta etd sim esim mpls wan lan vlan dns cdn ssl tls cpu gpu ram ssd hdd usb otp pin atm
gst vat tds emi poc mvp sop sops b2b b2c d2c saas paas iaas pii phi faq faqs
asap eod eow cob ooo wfh pto hq ceo cfo cto coo cio ciso cmo cpo vp svp evp avp md
aob tba tbc nb fyi imo
"""

# Fields of a ministry or department name: "Ministry of Electronics and Information
# Technology", "Department of Science and Technology" stay one name across "and".
SECTOR_WORDS = """
science sciences technology technologies information electronics health welfare family
affairs development education research culture tourism trade industry industries commerce
finance justice environment energy defence defense transport transportation agriculture
labour labor employment law economics economy arts medicine planning housing communications
broadcasting telecommunications mines mining water resources power urban rural forests
forestry fisheries youth sports women children social security home external foreign
internal revenue customs statistics innovation skills training aviation shipping railways
petroleum gas chemicals fertilizers textiles food consumer public works infrastructure
climate change digital data
"""

# Last word of a label naming the kind of the record id after it ("Purchase Order PO-55102",
# "Security Advisory SA-2024-017", "Change Request CR-5521").
RECORD_KIND_WORDS = """
order advisory request ticket incident invoice case change problem report notice bulletin
amendment contract policy claim bug story epic task release record requisition memo
quotation quote estimate shipment consignment delivery booking reservation application
permit licence license certificate approval note waybill receipt statement account
"""
