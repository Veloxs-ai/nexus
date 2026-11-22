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

"""Organisation, department, product and context-cue words for text entity typing.

Data only (casefolded, packed; ``_`` stands for a space), turned into sets on first use by
``graph_lexicon``. Cue words are what surrounds a name: "the customer X", "X migration",
"joined X", "the X office".
"""

from __future__ import annotations

# Last word of a multi-word name that makes it an organisation ("Tidewater Logistics").
ORG_FINALS = """
traders trading hotels hotel resorts resort hospitality air airways airline aviation aerospace
health healthcare clinics clinic hospitals medical medicals pharmacy pharmacies diagnostics
therapeutics biotech biosciences biologics pharma labs laboratories textiles mills garments
apparel fashion footwear paper papers packaging plastics rubber glass ceramics chemicals
paints coatings steel steels metals mining minerals cement construction builders developers
realty properties estates housing homes utilities power energy renewables solar petroleum
oil gas water freight shipping logistics transport transportation express couriers cargo
lines maritime marine rail railways railroad transit motors automotive auto autos cars
trucks trucking tyres tires bancorp bancshares bank banks savings lending loans mutual
finance financial capital investments securities assurance insurance reinsurance fund funds
trust trusts holdings group groups industries enterprises corporation international global
worldwide brands foods food beverages breweries brewery brewing dairy farms agro agritech
agriculture seeds fertilizers sweets bakery bakeries confectionery restaurants foodservice
supermarkets supermarket stores mart markets retail retailers outfitters furniture interiors
cosmetics jewellers jewelers optical opticals toys electric electrical electronics
semiconductors instruments robotics automation networks communications telecom telecoms
wireless broadcasting media pictures films studios publishing publishers press records
music entertainment games gaming interactive sports academy school schools college
university institute foundation charity alliance federation association society union
partners partnership associates advisors advisers advisory consultants consulting
attorneys solicitors accountants auditors staffing recruitment workforce outsourcing
technologies technology tech software systems solutions digital analytics labs dynamics
industries manufacturing manufacturers fabrication engineering engineers contractors
security defence defense aeronautics shipyards shipbuilding tours travel cruises
agency agencies ventures equity commodities exports imports distributors distribution
supply supplies wholesale wholesalers services
"""

# Departments and internal functions: an organisation (unit) when capitalised, including at
# the start of a sentence ("Legal will review ...").
DEPARTMENTS = """
legal finance hr procurement purchasing sales marketing engineering operations ops security
support it facilities treasury compliance audit accounting payroll administration admin
infosec devops sre helpdesk recruiting recruitment talent communications comms
partnerships r&d logistics fulfilment fulfillment underwriting
human_resources people_operations people_ops internal_audit customer_success customer_support
customer_service customer_care technical_support tech_support it_support it_operations
service_desk help_desk deal_desk sales_operations revenue_operations revops salesops
business_development corporate_development investor_relations public_relations
supply_chain quality_assurance field_service field_services accounts_payable
accounts_receivable general_counsel legal_and_compliance risk_management
information_security data_protection product_management program_management
programme_management project_management_office pmo executive_committee steering_committee
audit_committee risk_committee works_council board_of_directors finance_team legal_team
sales_team support_team the_board site_reliability platform_engineering data_engineering
customer_experience inside_sales global_sales corporate_finance financial_planning fp&a
tax internal_controls corporate_communications brand_marketing growth_marketing
"""

# Last word of a multi-word unit name ("Vendor Management Office", "Safety Committee").
UNIT_FINALS = """
desk office committee council department division unit centre center board panel taskforce
task_force directorate secretariat bureau ministry commission authority agency squad
"""

# Well-known organisations (typing only: they still need the capitalised-span evidence).
KNOWN_ORGS = """
google alphabet microsoft apple amazon meta facebook ibm oracle sap salesforce intel amd nvidia
qualcomm broadcom cisco dell hp hpe lenovo asus acer samsung sony lg panasonic siemens bosch
philips toshiba hitachi fujitsu nec canon nikon ricoh xerox ericsson nokia huawei xiaomi oppo
vivo tencent alibaba baidu bytedance jd.com infosys wipro tcs tata_consultancy_services
hcl hcltech tech_mahindra accenture deloitte kpmg pwc pricewaterhousecoopers ey ernst_&_young
capgemini cognizant mckinsey bcg bain gartner forrester idc tesla ford gm general_motors
toyota honda nissan bmw volkswagen vw audi porsche mercedes mercedes-benz daimler stellantis
renault peugeot fiat volvo hyundai kia tata mahindra maruti reliance adani airtel jio
vodafone verizon at&t t-mobile comcast charter bt telefonica deutsche_telekom swisscom
singtel telstra jpmorgan jp_morgan jpmorgan_chase citi citibank citigroup hsbc barclays
lloyds natwest santander bbva ubs credit_suisse deutsche_bank commerzbank bnp_paribas
societe_generale ing rabobank abn_amro goldman_sachs morgan_stanley wells_fargo
bank_of_america blackrock vanguard fidelity schwab charles_schwab state_street visa mastercard
amex american_express paypal stripe adyen klarna revolut monzo wise transferwise razorpay
paytm phonepe hdfc icici sbi axis_bank kotak walmart costco tesco sainsbury's asda aldi
lidl carrefour ikea h&m inditex nike adidas puma unilever nestle procter_&_gamble p&g
pepsico coca-cola danone kraft_heinz heinz mondelez kellogg's diageo ab_inbev heineken
pfizer moderna novartis roche sanofi gsk glaxosmithkline astrazeneca merck bayer abbvie
amgen gilead johnson_&_johnson j&j eli_lilly novo_nordisk takeda teva cipla sun_pharma
exxon exxonmobil chevron totalenergies aramco saudi_aramco petrobras equinor conocophillips
emirates lufthansa ryanair easyjet qantas british_airways air_india air_france klm
singapore_airlines cathay_pacific dhl fedex ups maersk db_schenker kuehne+nagel
clifford_chance linklaters allen_&_overy freshfields baker_mckenzie latham_&_watkins
netflix disney spotify bbc cnn reuters bloomberg nielsen uber lyft airbnb booking.com expedia
doordash instacart grab gojek ola swiggy zomato flipkart nykaa shopify ebay etsy
twitter linkedin pinterest snap reddit openai anthropic deepmind mistral cohere
boeing airbus lockheed_martin raytheon rolls-royce bae_systems general_electric ge
honeywell abb schneider_electric 3m caterpillar john_deere komatsu thyssenkrupp arcelormittal
basf dow dupont bridgestone michelin continental zf bosch_rexroth valeo denso
european_union united_nations nato world_bank imf international_monetary_fund
world_health_organization wto world_trade_organization oecd european_commission
european_parliament european_central_bank ecb federal_reserve the_fed sec
financial_conduct_authority fca reserve_bank_of_india rbi sebi bank_of_england
nhs irs hmrc fda ema unicef unesco red_cross who_collaborating_centre
"""

# Well-known products, platforms and tools (typing only).
KNOWN_PRODUCTS = """
slack confluence jira trello asana notion figma github gitlab bitbucket jenkins docker
kubernetes terraform ansible elasticsearch opensearch kibana logstash grafana prometheus
datadog splunk new_relic pagerduty opsgenie servicenow zendesk freshdesk freshservice
intercom hubspot marketo mailchimp pardot tableau power_bi powerbi looker qlik metabase
snowflake databricks bigquery redshift postgres postgresql mysql mariadb mongodb redis
cassandra kafka spark hadoop airflow dbt excel powerpoint outlook sharepoint onedrive
dropbox google_drive gmail google_docs google_sheets google_workspace g_suite zoom webex
skype whatsapp telegram microsoft_teams ms_teams chrome firefox safari windows macos linux
ubuntu debian centos rhel android ios iphone ipad macbook imac pixel chromebook azure aws
gcp google_cloud office_365 microsoft_365 m365 dynamics_365 s/4hana sap_s/4hana workday
okta auth0 onelogin quickbooks xero netsuite concur coupa ariba docusign acrobat photoshop
illustrator canva miro loom calendly chatgpt gpt-4 copilot github_copilot gemini bard
llama claude_code vscode visual_studio intellij pycharm eclipse xcode postman swagger
sentry circleci travis_ci bamboo artifactory nexus_repository sonarqube vault consul
nomad cloudflare akamai fastly heroku vercel netlify firebase supabase twilio sendgrid
segment amplitude mixpanel optimizely hotjar qualtrics surveymonkey typeform smartsheet
monday.com clickup basecamp airtable zapier workato mulesoft boomi informatica talend
fivetran stitch alteryx sas spss stata matlab sap_hana sap_erp oracle_erp peoplesoft
jd_edwards successfactors taleo greenhouse lever bamboohr gusto adp rippling deel
expensify ramp brex bill.com tally zoho zoho_crm freshworks pipedrive gong outreach
salesloft linkedin_sales_navigator apollo zoominfo clearbit 6sense gainsight totango
"""

# Last word of a multi-word product name ("Learning Portal", "Insights Studio").
PRODUCT_FINALS = """
portal app apps suite studio cloud os edition pro max plus mini ultra lite premium
platform dashboard console workspace toolkit sdk api engine browser reader player editor
assistant copilot bot analytics_suite
"""

# Last word of a multi-word document name: a concept ("Data Processing Addendum").
CONCEPT_FINALS = """
agreement addendum policy policies regulation regulations directive standard standards
protocol framework charter guideline guidelines terms clause covenant code act bill
procedure handbook playbook manual principles statement
"""

# The lowercase word right after a name, or a near one in its noun phrase, and the type it
# suggests ("the Halcyon upgrade", "the Falcon migration", "calling Blue Sun support").
NEXT_CUES = {
    "product": """
plan plans dashboard dashboards platform app apps application tool tools tab module modules
api apis sdk release releases upgrade upgrades version versions roadmap router routers
tablet tablets laptop laptops phone phones handset server servers controller controllers
device devices sensor sensors lamp lamps printer printers licence license licences
licenses subscription subscriptions instance instances plugin plugins extension
extensions widget widgets edition console workspace firmware software appliance appliances
engine headset headsets charger chargers adapter adapters camera cameras drone drones
pallets pallet units model models series kit kits integration connector connectors cartridge
cartridges sku skus feature features build builds portal user users login account
""",
    "project": """
project projects migration migrations programme program initiative initiatives pilot pilots
rollout rollouts replacement implementation transformation workstream workstreams epic
epics cutover go-live golive launch revamp overhaul rewrite consolidation
""",
    "org": """
support employees staff headquarters hq shareholders spokesperson spokeswoman spokesman ceo
cfo cto coo cio founder founders subsidiary subsidiaries acquisition merger board
executives management leadership workforce customers' auditors invoice invoices account
manager representative representatives rep reps contract contracts
""",
    "place": """
office offices branch branches campus site sites plant plants warehouse warehouses depot
depots hub hubs region area airport port facility facilities factory factories
data_centre data_center datacenter store stores showroom harbour harbor district
headquarters_building metro suburb
""",
}

# The lowercase word(s) right before a name and the type they suggest, with a weight
# (2 = strong: "the customer X", "joined X"; 1 = weak: "in X", "at X").
PREV_CUES = {
    "org": (
        2,
        """
customer client vendor supplier partner carrier bank firm company competitor insurer
lender distributor reseller auditor auditors contractor subcontractor provider manufacturer
employer agency startup start-up joined join joining acquired acquiring acquire merged
subsidiary rival brand retailer wholesaler shipper broker underwriter
""",
    ),
    "place": (
        2,
        """
city town village county province state capital suburb near outside downtown across
throughout via
""",
    ),
    "person": (
        2,
        """
mr mrs ms dr prof sir madam dear hi hello hey thanks cc attn attention colleague
manager ceo cfo cto coo founder engineer analyst director
""",
    ),
}
WEAK_PREV = {"in": "place", "at": "org", "from": "org", "with": "org", "by": "org"}

# A capitalised subject followed by one of these is an organisation when nothing else types
# it ("Gringotts requested a copy").
ORG_VERBS = """
requested announced signed acquired disputes disputed reported filed hired launched
confirmed agreed approved rejected declined invoiced shipped terminated renewed
cancelled canceled sued posted raised reported partnered
"""

# Verbs and auxiliaries that let a department word open a sentence ("Legal will review").
SUBJECT_VERBS = """
will would has have had can could should must shall wants needs asked approved opened owns
owned signed reviewed requested confirmed flagged
expects expected reported rejected declined launched moved runs ran handles handled
"""

# Words that never take a model number ("Phase 2", "Room 101", "Section 4").
MODEL_STOP = """
phase sprint room gate building floor ward unit lot batch week day wave stage round tier grade
track lane block sector zone area line row column chapter section table figure page step item
appendix annex exhibit clause article rule part version release build patch iteration
milestone cohort group team class year quarter terminal hall bay dock door pier route
highway interstate level category type option plan suite apartment flat house street road
platform channel ticket order invoice case incident request issue bug task story point
grade score rank number no top under over age size slide question answer exercise test
lesson module session episode season volume issue edition
"""
