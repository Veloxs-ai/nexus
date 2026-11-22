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


def _words(text: str) -> frozenset[str]:
    return frozenset(w.replace("_", " ") for w in text.split())


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
CONNECTORS = _words("of and & de van von der da la le du del di y")

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
HONORIFICS = _words("mr mrs ms miss dr prof professor sir madam shri smt sri kumari mx")

GIVEN_NAMES = _words("""
aaron abigail adam adrian aisha alan albert alex alexander alice alicia alison amanda amber
amelia amit amy ana andrea andrew angela anil anita ankit ann anna anne anthony anuj anupam
arjun arnav arthur arun asha ashish ashok ava barbara ben benjamin beth betty bhavna bill
bob bonnie brandon brenda brian bruce bryan carl carlos carol caroline catherine charles
charlie charlotte cheryl chloe chris christian christina christine christopher cindy claire
clara colin connor craig crystal cynthia dan daniel danielle david dawn deborah deepa deepak
denise dennis derek diana diane dinesh divya dominic donald donna doris dorothy douglas
dylan edward elaine eleanor elena elizabeth ella ellen emily emma eric erica erin ethan
eugene eva evelyn fatima fiona frances francis frank gabriel gary gaurav gavin george
gerald gina gloria grace greg gregory hannah harish harold harry harsh heather helen henry
hiro hiroshi howard ian irene isaac isabella jack jacob jacqueline james jamie jane janet
janice jason jay jean jeff jeffrey jennifer jeremy jerry jessica jill jim joan joe joel john
johnny jonathan jordan jose joseph joshua joyce juan judith judy julia julie justin karan
karen kate katherine kathleen kathryn katie kavita keith kelly ken kenneth kevin kim
kimberly kiran kumar kyle laura lauren lawrence leah lee leo liam lily linda lisa lori
louis louise lucas lucy luis madhu mahesh manish manoj margaret maria marie mark martha
martin mary mason matthew maya megan meera melissa michael michelle mike mohammed mohan
monica nancy naomi naresh natalie nathan neha neil nicholas nicole nikhil nina noah norma
olivia omar oscar pamela patricia patrick paul paula peter philip pooja prakash pranav
priya priyanka rachel rahul raj rajesh rakesh ralph ram ramesh randy ravi raymond rebecca
rekha richard rita robert robin rohan rohit roger ronald rose ross roy ruby russell ruth
ryan sachin sakura sam samantha samuel sandeep sandra sanjay sara sarah satish scott sean
shalini sharon shirley shreya simon sneha sofia sonia sophia stephanie stephen steve steven
sudha suman sunil sunita suresh susan swati tanvi tara teresa terry thomas tiffany tim
timothy tina todd tom tony tracy tyler uma usha valerie varun vanessa veronica vicky victor
victoria vijay vikram vinay vincent virginia vivek walter wayne wei william xin yan yash
yuki yusuf zachary zara zoe zhang li wang chen liu ahmed ali hassan hussein ibrahim yasmin
lars sven ingrid hans klaus jurgen stefan anke heike pierre jean-pierre francois marc
camille louis-philippe giulia marco luca giovanni francesca alessandro sofia matteo pablo
javier miguel carmen lucia diego mateo ana-maria joao pedro rafael gabriela fernanda
olga ivan dmitri sergei natalia elena-maria takeshi kenji haruto ji-woo min-jun seo-yeon
""")

PLACES = _words("""
afghanistan albania algeria andorra angola argentina armenia australia austria azerbaijan
bahamas bahrain bangladesh barbados belarus belgium belize benin bhutan bolivia bosnia
botswana brazil brunei bulgaria burundi cambodia cameroon canada chad chile china colombia
congo croatia cuba cyprus czechia czech_republic denmark djibouti dominica ecuador egypt
el_salvador eritrea estonia eswatini ethiopia fiji finland france gabon gambia georgia
germany ghana greece grenada guatemala guinea guyana haiti honduras hungary iceland india
indonesia iran iraq ireland israel italy jamaica japan jordan kazakhstan kenya kiribati
kosovo kuwait kyrgyzstan laos latvia lebanon lesotho liberia libya liechtenstein lithuania
luxembourg madagascar malawi malaysia maldives mali malta mauritania mauritius mexico
moldova monaco mongolia montenegro morocco mozambique myanmar namibia nauru nepal
netherlands new_zealand nicaragua niger nigeria north_korea norway oman pakistan palau
panama paraguay peru philippines poland portugal qatar romania russia rwanda samoa
san_marino saudi_arabia senegal serbia seychelles sierra_leone singapore slovakia slovenia
somalia south_africa south_korea spain sri_lanka sudan suriname sweden switzerland syria
taiwan tajikistan tanzania thailand togo tonga trinidad tunisia turkey turkmenistan tuvalu
uganda ukraine united_arab_emirates uae united_kingdom uk united_states usa us uruguay
uzbekistan vanuatu vietnam yemen zambia zimbabwe england scotland wales europe asia africa
north_america south_america latin_america middle_east apac emea americas
mumbai delhi new_delhi bengaluru bangalore chennai hyderabad kolkata pune ahmedabad jaipur
surat lucknow kanpur nagpur indore thane bhopal visakhapatnam patna vadodara ghaziabad
ludhiana agra nashik faridabad meerut rajkot varanasi srinagar aurangabad amritsar
allahabad ranchi coimbatore jabalpur gwalior vijayawada jodhpur madurai raipur kota
guwahati chandigarh mysore mysuru noida gurgaon gurugram kochi thiruvananthapuram goa
london manchester birmingham glasgow edinburgh liverpool leeds bristol dublin belfast cardiff
paris lyon marseille berlin munich hamburg frankfurt cologne stuttgart vienna zurich geneva
basel amsterdam rotterdam brussels antwerp madrid barcelona valencia seville lisbon porto
rome milan naples turin florence venice athens istanbul ankara moscow saint_petersburg
warsaw krakow prague budapest bucharest sofia belgrade zagreb copenhagen stockholm oslo
helsinki reykjavik tallinn riga vilnius kyiv kiev minsk
new_york los_angeles chicago houston phoenix philadelphia san_antonio san_diego dallas
san_jose austin jacksonville san_francisco seattle denver boston washington nashville
detroit portland las_vegas atlanta miami minneapolis cleveland pittsburgh baltimore
toronto montreal vancouver calgary ottawa edmonton mexico_city guadalajara monterrey
sao_paulo rio_de_janeiro buenos_aires lima bogota santiago caracas quito montevideo
tokyo osaka kyoto yokohama nagoya seoul busan beijing shanghai shenzhen guangzhou chengdu
hong_kong macau taipei bangkok hanoi ho_chi_minh_city kuala_lumpur jakarta manila
singapore_city dhaka karachi lahore islamabad kathmandu colombo dubai abu_dhabi doha riyadh
jeddah muscat kuwait_city tehran baghdad tel_aviv jerusalem amman beirut cairo alexandria
lagos abuja nairobi addis_ababa johannesburg cape_town durban casablanca tunis accra
sydney melbourne brisbane perth adelaide canberra auckland wellington
california texas florida new_jersey massachusetts ontario quebec bavaria catalonia
maharashtra karnataka tamil_nadu kerala gujarat rajasthan punjab bihar telangana
west_bengal uttar_pradesh madhya_pradesh andhra_pradesh haryana odisha assam
""")

# Job titles and roles: a span that names a role is not an entity ("Chief Risk Officer").
ROLE_HEADS = _words("""
officer president director manager head chair chairman chairperson chairwoman lead secretary
treasurer counsel controller administrator coordinator specialist analyst engineer architect
consultant executive vp svp evp ceo cfo cto coo cio ciso cmo dpo partner associate intern
""")
ROLE_FIRST = _words("chief head vice deputy assistant associate senior junior acting interim")

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
    [
        "AKA",
        "AM",
        "AND",
        "API",
        "AS",
        "ASAP",
        "AT",
        "BCC",
        "BY",
        "CC",
        "CRM",
        "CSV",
        "EOD",
        "ERP",
        "ETA",
        "ETC",
        "EUR",
        "FAQ",
        "FOR",
        "FW",
        "FYI",
        "GBP",
        "GMT",
        "HR",
        "ID",
        "II",
        "III",
        "IN",
        "INR",
        "IS",
        "IST",
        "IT",
        "IV",
        "JPY",
        "KPI",
        "MFA",
        "MOU",
        "MTD",
        "N/A",
        "NA",
        "NDA",
        "NO",
        "NOTE",
        "OF",
        "OK",
        "ON",
        "OR",
        "PDF",
        "PM",
        "PO",
        "PS",
        "QA",
        "QTD",
        "RE",
        "RFP",
        "RFQ",
        "SKU",
        "SLA",
        "SOW",
        "SSO",
        "TBD",
        "THE",
        "TO",
        "TODO",
        "UI",
        "URL",
        "USD",
        "UTC",
        "UX",
        "VPN",
        "VS",
        "YES",
        "YTD",
    ]
)

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
