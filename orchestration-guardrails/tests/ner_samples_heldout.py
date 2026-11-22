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

"""Held-out labelled sentences (same format as ``ner_samples``), written after the lexicon
rules were tuned and never used to tune them: rarer names, small towns, lowercase chat and
ambiguous words. The accuracy test reports these separately."""

from __future__ import annotations

HELD_OUT = r"""
Hi {Thiagarajan Balakumar|P}, the courier will reach {Tiruppur|L} on Wednesday.
Regards,\n{Siobhan Keane|P}\nOperations, {Dublin|L}
{Nkechi Obi|P} raised a ticket about the {Abuja|L} invoice.
Dear Mrs. {Wainwright|P}, your claim has been approved.
{Zubin Irani|P} will take over the {Hosur|L} account.
Please loop in {Bartholomew Finch|P} before Friday.
The rider picked up the parcel in {Kakinada|L}.
{Lakshmanan|P} asked whether the {Madurai|L} warehouse is open.
Spoke with {Ines Carvalho|P} about the {Porto|L} contract.
hey priya can you check the build
{Dmitri Volkov|P} approved the change from {Saint Petersburg|L}.
Escalated by {Parvathy Menon|P}.
{Joaquín Herrera|P} moved to {Monterrey|L} last year.
Ticket reporter: {Yusuf Demir|P}, {Ankara|L}
{Ngozi Eze|P} and {Chidi Okeke|P} reviewed the draft.
Assigned to {Hemant Sonawane|P}
The {Vizag|L} team needs two more laptops.
Thanks,\n{Rukmini|P}
{Anushka Bhosale|P} called from {Kolhapur|L}.
Please send the samples to {Mangalore|L} by courier.
{Callum Fraser|P} works out of our {Glasgow|L} office.
Meeting notes from {Wojciech Zielinski|P}
{Leilani Kahale|P} is the new contact in {Honolulu|L}.
{Shanthi|P} said the {Trichy|L} branch is short of forms.
Patient {Gurmeet Bajwa|P} was discharged on Monday.
Dr. {Achterberg|P} will review the scan.
{Mateus Rocha|P} visited {Curitiba|L} and {Recife|L}.
{Tenzin Norbu|P} lives near {Dharamshala|L}.
Return label sent to {Aoife Brennan|P} in {Galway|L}.
{Somnath Ganguly|P} cleared the {Durgapur|L} backlog.
Grant Thornton finished the audit.
The Phoenix release is delayed.
Add this to the Reading list.
Victoria Secret ads ran all week.
Jordan sneakers are back in stock.
The Lincoln Navigator was recalled.
Mobile App Store Listing
Chase Bank flagged the payment.
Nice work on the Apple Store launch.
Paris Agreement targets were discussed.
Washington Post subscription renewed.
Ruby on Rails upgrade is complete.
Georgia Pacific shipped the paper.
Raymond suits are on sale.
Haldiram snacks were served.
Amul butter prices went up.
Godrej Interio delivered the chairs.
Bajaj Auto launched a new scooter.
"""
