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
needs on top: surnames, surname endings, and the role labels that precede a name in records
and tickets ("Customer Ravi Shankar", "Patient John Matthews").
"""

from __future__ import annotations

# Surnames that are not ordinary English words: a capitalised word before one of these is
# taken as a given name ("Tanvir Ahmed"). Indian, English, European, African and East Asian.
SURNAMES = """
sharma verma gupta singh kumar patel shah mehta desai joshi kulkarni deshpande deshmukh pawar
jadhav patil gaikwad shinde chavan iyer iyengar nair menon pillai reddy rao naidu raju
krishnan raman subramanian narayanan venkatesan srinivasan raghavan ramachandran swaminathan
chauhan agarwal aggarwal agrawal bansal goel goyal jain mittal malhotra kapoor khanna arora
chopra bhatia sethi ahuja gill sandhu grewal dhillon sidhu kaur mishra tiwari pandey dubey
trivedi chaturvedi shukla tripathi yadav prasad sinha jha thakur chatterjee banerjee mukherjee
ghosh bose sengupta dasgupta dutta chakraborty bhattacharya saha mitra hegde shetty bhat
kamath shenoy fernandes dsouza d'souza rodrigues pereira varghese kurian chacko qureshi
sheikh khan ahmed ahmad hussain hussein ansari siddiqui mirza rizvi saxena srivastava mathur
bhatt parekh thakkar chandra kohli bajaj tandon sahni saini rawat negi bisht chaudhary
choudhary chowdhury naik gowda shankar krishnamurthy narayan venkataraman sundaram
balasubramanian natarajan rajan murthy moorthy pillay naidoo mahajan bhardwaj dixit awasthi
upadhyay bhagat soni lal devi rani sengar rathore rajput solanki parmar vaghela jhunjhunwala
bhatnagar khurana luthra wadhwa sachdeva oberoi kakkar talwar puri anand sood
mohan krishna gopal hassan ibrahim mohammed mohammad rahman chowdhury begum akhtar
smith johnson williams jones miller davis garcia rodriguez wilson martinez anderson taylor
thomas hernandez thompson lopez gonzalez harris lewis robinson walker perez sanchez
campbell mitchell roberts phillips evans torres parker collins edwards stewart flores morris
nguyen murphy rivera price rogers peterson cooper bailey kelly howard richardson watson
bennett reyes cruz hughes myers sanders morales powell sullivan russell ortiz jenkins
gutierrez perry butler barnes fisher henderson coleman simmons patterson reynolds
gonzales ramos wallace griffin hayes chavez gibson bryant ellis stevens murray marshall owens
mcdonald harrison ruiz kennedy alvarez mendoza castillo olson tucker vasquez snyder
simpson crawford jimenez wagner romero hicks dixon robertson holmes meyer boyd ferguson
nichols herrera medina fernandez weaver daniels stephens gardner payne kelley pierce hawkins
hansen castro hoffman elliott cunningham bradley matthews clarke o'connor o'brien o'neill
mccarthy fitzgerald gallagher doherty schmidt schneider fischer weber becker schulz koch
richter neumann zimmermann krause hartmann lange werner krüger müller mueller schäfer dubois
lefebvre moreau laurent leroy fontaine rossi russo ferrari esposito bianchi romano colombo
ricci marino greco bruno gallo conti rinaldi novak kowalski nowak wiśniewski wisniewski
lewandowski kowalczyk petrov ivanov smirnov popov kuznetsov sokolov popescu ionescu
horvat dvořák nagy kovács papadopoulos andersson johansson nilsson larsson eriksson jansen
janssen visser dekker hendriks tanaka sato suzuki takahashi watanabe yamamoto nakamura
kobayashi kato yoshida yamada sasaki matsumoto inoue kimura hayashi wang zhang liu chen yang
huang zhao zhou xu zhu tran pham hoang huynh vo silva santos oliveira souza costa almeida
ferreira lima carvalho gomes ribeiro adeyemi okafor okonkwo mwangi otieno kamau njoroge
mensah owusu boateng adebayo oyelaran nkosi dlamini
"""

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

