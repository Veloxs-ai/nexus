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

"""Labelled sentences for person/location detection (all names and places are fictional
combinations; any resemblance to a real person is accidental).

One sentence per line; ``{text|P}`` marks a person, ``{text|L}`` a location. Honorifics stay
outside the person span. Lines without marks are negatives (products, companies, headings).
``\\n`` inside a line stands for a line break. ``load()`` returns (text, [(start, end, label)]).
"""

from __future__ import annotations

import re

EMAILS = r"""
Hi {Priya|P}, please send the signed contract to our {Pune|L} office by Friday.
Dear Mr. {Sharma|P},\nThank you for your application.
Regards,\n{Rahul Verma|P}\nSenior Analyst
Thanks,\n{Ananya Iyer|P}
Hello {David|P}, the shipment left {Rotterdam|L} on Monday and reaches {Chennai|L} next week.
Please cc {Meera Krishnan|P} and {Arjun Nair|P} on the next update.
Dear Dr. {Venkatesh|P}, your appointment is confirmed for Tuesday.
My name is {Sunita Reddy|P} and I am writing about invoice 4471.
Kind regards,\n{Emily Clarke|P}\nAccount Manager, {London|L}
We will open a new branch in {Hyderabad|L} this quarter.
{Karthik|P} mentioned that the {Bengaluru|L} team is short-staffed.
The audit was signed off by {Neha Gupta|P} on 12 March.
Please forward this to {Michael Thompson|P} in {Chicago|L}.
Best,\n{Sarah O'Connor|P}
Hi team, the offsite will be held in {Goa|L} from 4 to 6 June.
Dear Ms. {Fernandes|P}, we have received your request.
{Vikram Singh|P} will join the call from {Delhi|L}.
Contact {Rohan Mehta|P} for any questions about onboarding.
Smt. {Lakshmi Devi|P} has submitted the KYC documents.
Shri {Ramesh Chandra|P} visited the {Lucknow|L} branch yesterday.
Our warehouse in {Nagpur|L} will be closed for maintenance.
I spoke with {Jennifer Lopez|P} about the renewal terms.
The customer, {Amit Kumar|P}, has requested a refund.
Please call {Sneha|P} if the courier does not arrive.
Signed: {Thomas Müller|P}
Forwarded message from {Pooja Desai|P}
{Daniel Kim|P} from the {Seoul|L} office approved the budget.
The team in {Toronto|L} reported a spike in tickets.
Dear {Anjali|P},\nYour order has shipped.
Our CFO {Suresh Raman|P} will present the results.
Kindly ask {Deepak Joshi|P} to share the updated forecast.
We are relocating the support desk from {Kolkata|L} to {Bhubaneswar|L}.
Regards,\n{Kavya Subramanian|P}\nHR Business Partner
I have attached the minutes from the meeting with {Laura Bennett|P}.
Hi {Siddharth|P}, can you confirm the delivery address?
The vendor in {Shenzhen|L} shipped the replacement parts.
Mrs. {Patel|P} called about her pension statement.
Prof. {Alan Turner|P} will chair the session.
{Harpreet Kaur|P} joined the {Mumbai|L} sales team in April.
Please welcome {Mohammed Ali|P}, our new engineer in {Dubai|L}.
"""

TICKETS = r"""
Customer {Ravi Shankar|P} reports that the app crashes on login.
Assigned to {Nikhil Bansal|P}; reported by {Swati Mishra|P}.
User from {Jaipur|L} cannot reset password.
Escalated to {Arun Prakash|P} after two failed attempts.
Caller {Gita Rao|P} says the router keeps rebooting.
The outage affected users in {Germany|L}, {France|L} and {Spain|L}.
Issue raised by {Mark Wilson|P}: VPN drops every hour.
Resolved by {Pallavi|P}. Root cause: expired certificate.
Requester: {Sanjay Kulkarni|P}\nLocation: {Ahmedabad|L}
Ticket owner {Divya Menon|P} will follow up tomorrow.
Field technician {Manoj Tiwari|P} visited the site in {Indore|L}.
The customer lives in {Kochi|L} and wants a home visit.
Complaint from {Rekha Pillai|P} about a double charge.
Agent {Kevin Brown|P} closed the ticket without a reply.
{Abhishek Yadav|P} could not access the portal from {Patna|L}.
Please contact the customer at her {Noida|L} address.
Shipment stuck in customs at {Singapore|L}.
Reporter: {Olivia Martin|P}. Priority: high.
Device registered to {Farhan Qureshi|P} was flagged as lost.
The engineer, {Prakash Hegde|P}, replaced the battery.
Our {Coimbatore|L} plant reported a conveyor fault.
Escalation contact: {Ritu Malhotra|P}
The call was transferred to {Joseph Mathew|P} in billing.
Return requested by {Isabella Rossi|P} from {Milan|L}.
{Gaurav|P} says the invoice total is wrong.
Account holder {Nandini Bhat|P} disputes the late fee.
Delivery failed in {Thane|L} because the gate was locked.
{Tanvir Ahmed|P} needs a replacement card sent to {Dhaka|L}.
Installation scheduled with {Ramesh|P} for Thursday.
Customer moved from {Texas|L} to {California|L} and needs a new plan.
"""

CHAT = r"""
hey {Rahul|P} are you joining the standup?
{Aisha|P}: the build is green now
{Vivek|P} can you review my PR?
lunch with {Shreya|P} and {Manish|P} at 1?
I'm in {Bangalore|L} till Friday
just landed in {Frankfurt|L}
{Neha|P} said the demo went well
ping {Kiran|P} about the release notes
ok {Arjun|P}, merging now
{Pradeep|P} is out sick today
anyone from {Chennai|L} going to the meetup?
{Tom|P} and {Jessica|P} are presenting tomorrow
can someone ask {Varun|P} for the logs?
moving to {Berlin|L} next month!
{Rajesh|P} pls check the dashboard
thanks {Ishaan|P}!
heading to {Mysore|L} for the weekend
{Lisa|P} approved the design
does {Ankit|P} have access to prod?
the client in {Sydney|L} wants a call at 9
{Fatima|P} is covering for me
{Sameer|P} fixed the flaky test
greetings from {Kathmandu|L}
my name is {Rohit Sharma|P} and I need help with my account
this is {Anita|P} from accounts
{Nisha|P} and I will handle the {Delhi|L} rollout
{Chris|P} shared the slides in the channel
remote from {Lisbon|L} this week
{Yuki Tanaka|P} joined from {Tokyo|L}
{Carlos|P} said the {Madrid|L} office is closed
"""

NEGATIVES = r"""
Quarterly Business Review
Action Items and Next Steps
The new iPhone supports faster charging.
Please update the Excel template before Monday.
Salesforce sync failed for three accounts.
Microsoft Teams will be down for maintenance.
Infosys and Wipro both submitted bids.
Tata Consultancy Services renewed the contract.
Project Phoenix kicked off in January.
Release Notes: Version 4.2
Customer Satisfaction Survey Results
Amazon Web Services billing increased this month.
The Data Processing Addendum was updated.
Google Drive integration is now available.
Annual General Meeting Agenda
Reliance Industries posted strong earnings.
The Jira board shows twelve open bugs.
Use Slack for urgent questions.
Executive Summary
Terms and Conditions apply.
HDFC Bank approved the loan.
The Galaxy tablet ships with Android.
Kubernetes cluster upgraded to the latest version.
Risk Assessment Framework
Zoom meetings are limited to forty minutes.
Oracle Database migration is scheduled for Q3.
Board of Directors
The Platinum Plan includes priority support.
Python scripts run nightly.
Incident Report Summary
Accenture and Deloitte attended the workshop.
The Sales Dashboard is refreshed hourly.
Monthly Active Users grew by ten percent.
Customer Success Team
The Express Delivery option costs extra.
Purchase Order Approval Workflow
Visa and Mastercard payments are supported.
Power BI reports are shared weekly.
Service Level Agreement
The Premium Support package was renewed.
"""


_MARK = re.compile(r"\{([^{}|]+)\|([PL])\}")
LABELS = {"P": "person", "L": "location"}


def _parse(line: str) -> tuple[str, list[tuple[int, int, str]]]:
    line = line.replace("\\n", "\n")
    text, spans, last = [], [], 0
    pos = 0
    for match in _MARK.finditer(line):
        text.append(line[last : match.start()])
        pos += match.start() - last
        surface = match.group(1)
        spans.append((pos, pos + len(surface), LABELS[match.group(2)]))
        text.append(surface)
        pos += len(surface)
        last = match.end()
    text.append(line[last:])
    return "".join(text), spans


def load(*blocks: str) -> list[tuple[str, list[tuple[int, int, str]]]]:
    from ner_samples_more import BLOCKS as MORE

    chosen = blocks or (EMAILS, TICKETS, CHAT, NEGATIVES, *MORE)
    return [_parse(line) for block in chosen for line in block.strip().splitlines() if line]
