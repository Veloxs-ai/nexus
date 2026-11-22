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

"""More labelled sentences (see ``ner_samples``): records, notes, harder negatives and
informal text (lowercase chat, key/value fields, signatures, landmarks, world names)."""

from __future__ import annotations

RECORDS = r"""
Name: {Aditi Chauhan|P}\nCity: {Pune|L}\nState: {Maharashtra|L}
Patient {John Matthews|P}, 54, was admitted on 3 May.
Employee {Shalini Agarwal|P} transferred from {Gurgaon|L} to {Hyderabad|L}.
Beneficiary: {Mohan Lal|P}, {Varanasi|L}, {Uttar Pradesh|L}
The applicant, {Elizabeth Turner|P}, resides in {Manchester|L}.
Witness statement by {Robert Hughes|P} taken in {Leeds|L}.
Policyholder {Sushma Iyengar|P} renewed her policy online.
{Arvind Krishnamurthy|P} was appointed as the nominee.
Interview notes: {Jessica Wong|P} prefers to work from {Vancouver|L}.
Guardian name: {Rajendra Prasad|P}
The tenant {Anil Kapoor|P} paid rent for the flat in {Andheri|L}.
Student {Aarav Gupta|P} scored 92 in the final exam.
Driver {Sukhwinder Singh|P} delivered the order to {Ludhiana|L}.
Nominee: {Kamala Narayanan|P} (spouse)
Prepared by {Hannah Schmidt|P}, reviewed by {Peter Novak|P}.
Born in {Kerala|L}, {Sreeja Nair|P} moved to {Dubai|L} in 2015.
{Matthew Garcia|P} relocated from {Denver|L} to {Seattle|L}.
Emergency contact: {Usha Rani|P}, mother.
The loan was co-signed by {Bharat Joshi|P} and {Kiran Joshi|P}.
Sales rep {Brian Cooper|P} covers {Ohio|L} and {Michigan|L}.
{Chloe Dubois|P} from {Paris|L} requested the French invoice.
Account opened by {Imran Sheikh|P} at the {Bhopal|L} branch.
{Rebecca Adams|P} signed the lease in {Boston|L}.
Field visit to {Nashik|L} by {Sachin Pawar|P} and {Vaishali More|P}.
Candidate {Oluwaseun Adeyemi|P} is based in {Lagos|L}.
{Ivan Petrov|P} manages the {Warsaw|L} delivery centre.
Owner: {Grace Liu|P}; site: {Taipei|L}
Consultant {Natalia Kowalski|P} visited our {Krakow|L} office.
Applicant {Pranav Deshmukh|P} lives in {Aurangabad|L}.
{Zoe Williams|P} will cover {Scotland|L} and {Wales|L}.
"""

NOTES = r"""
Met with {Anand Rao|P} and {Shweta Saxena|P} to discuss the {Kolkata|L} expansion.
{Jonathan Price|P} raised concerns about the {Brazil|L} launch.
The partner in {Nairobi|L} wants a revised quote.
Call with {Esther Mwangi|P} from {Kenya|L} went well.
Our {Singapore|L} entity will invoice the {Australia|L} customer.
Follow up with {Raghav|P} on the {Ireland|L} tax filing.
{Mei Ling|P} confirmed the {Shanghai|L} supplier can deliver.
{Sophie Martin|P} and {Lucas Bernard|P} will visit {Lyon|L}.
Flights booked to {New Delhi|L} for {Ajay Mehra|P}.
{Vandana Shiva|P} spoke at the {Bengaluru|L} conference.
We lost the {Netherlands|L} deal to a competitor.
{Hiroshi Sato|P} prefers meetings after 10 am {Tokyo|L} time.
The {Tamil Nadu|L} distributor missed two shipments.
{Gopal Krishnan|P} handles collections for {South India|L}.
{Andrew Miller|P} and {Priyanka Chopra|P} co-authored the report.
Visa appointment in {Chennai|L} for {Lavanya|P} is on Friday.
{Sunil Gavaskar|P} reviewed the {Mumbai|L} pipeline.
The pilot in {Rajasthan|L} covered 40 villages.
{Ahmed Hassan|P} is travelling to {Cairo|L} next week.
{Kateryna Bondarenko|P} leads the {Kyiv|L} engineering team.
Team dinner in {Gurugram|L} hosted by {Ritesh Arora|P}.
{Benjamin Clark|P} said {Canada|L} sales were flat.
{Pooja|P} will present the {Gujarat|L} numbers.
Visit {Jaipur|L} and {Udaipur|L} with {Manoj|P} in December.
{Elena Popescu|P} asked for the {Romania|L} price list.
{Venkat Raghavan|P} approved the {Hyderabad|L} hiring plan.
The {United States|L} team will lead the rollout.
{Sarah|P} from legal reviewed the clause.
{Rakesh Jhunjhunwala|P} was mentioned in the press note.
{Amrita Sengupta|P} joined from {Kolkata|L}.
"""

HARD_NEGATIVES = r"""
Johnson & Johnson reported quarterly results.
Ford Motor Company recalled several vehicles.
Morgan Stanley upgraded the stock.
Mahindra Finance extended the credit line.
Bank of America declined the transfer.
The Washington Post covered the story.
Warren Buffett Letter Archive
Mercedes-Benz dealers reported strong demand.
The Marriott Rewards programme changed its tiers.
Kotak Mahindra Bank opened new branches.
Dell laptops are standard issue.
The Ganesh Chaturthi holiday is on Thursday.
Status: Open\nPriority: High\nOwner: Unassigned
Monday Standup Notes
Section 4: Payment Terms
Click Save and then Submit.
The Diwali sale starts next week.
Adobe Acrobat could not open the file.
Click Accept to continue.
Our Platinum Card members get lounge access.
"""

INFORMAL = r"""
hey {farhan|P} can u ask {lakshmi|P} to send the docs from {kochi|L}
ping {gaurav|P} once u land in {ahmedabad|L}
thanks {meghna|P}, will check with {venkat|P}
@{harini|P} did u get the invoice?
{tanvir|P} said he is stuck near {whitefield|L}
can you ask the team to review it by eod
may i know when the refund will be processed?
grace period is over, please mark the bill as paid
will do, thanks
{"first_name": "{Sakura|P}", "last_name": "{Ito|P}", "city": "{Kyoto|L}"}
cust_name={meera joshi|P}; city={nagpur|L}; status=active
customer: {Ifeoma Nwosu|P} | origin: {Enugu|L} | plan: silver
Warm regards,\n{Rafael Moreira|P}\nRegional Head\n{Lisbon|L}
Thanks,\n{Anupama Hegde|P}
{Bhattacharya|P} will share the numbers tomorrow.
Please ask {Joglekar|P} to sign the form.
{Lindiwe Zulu|P} drove from {Pretoria|L} to {Polokwane|L}.
{Hyun-woo Choi|P} is based in {Daegu|L}.
{Gabriela Rojas|P} works from our {Santiago|L} office.
We landed at {Netaji Subhas Chandra Bose International Airport|L} after midnight.
The team dinner is at {Hiranandani Gardens|L} on Friday.
She rented a flat in {Rajouri Garden|L}.
The office is on Brigade Road, {Bengaluru|L}.
Kirloskar Brothers shipped the pumps.
Torrent Pharmaceuticals renewed the contract.
The Bengali version of the brochure is ready.
The Diwali Mela stall bookings are open.
"""

BLOCKS = (RECORDS, NOTES, HARD_NEGATIVES, INFORMAL)
