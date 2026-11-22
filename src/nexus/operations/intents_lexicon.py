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

"""The default weighted lexicon of ``nexus.operations.intents``.

Per intent, ``(regex, weight)`` pairs for payment-reminder replies in English, Hinglish,
Hindi (Devanagari) and Marathi. Pass your own ``Lexicon`` to ``IntentClassifier`` to replace
or extend it.
"""

from __future__ import annotations

__all__ = ["DEFAULT_LEXICON", "Lexicon"]

# (pattern, weight). Patterns are matched case-insensitively on the whole message.
Lexicon = dict[str, list[tuple[str, float]]]
DEFAULT_LEXICON: Lexicon = {
    "promise_to_pay": [
        (r"\b(will|shall|i'?ll|going to|gonna)\s+(pay|clear|deposit|transfer|send)", 0.75),
        (r"\bpay(ing)?\s+(it\s+)?(by|on|before|till|until|next|tomorrow|today)\b", 0.7),
        (r"\b(by|before|on)\s+the\s+\d{1,2}(st|nd|rd|th)?\b", 0.45),
        (
            r"\b(salary|payment)\s+(is\s+|got\s+|has\s+been\s+)?"
            r"(late|delayed|pending|not credited)",
            0.4,
        ),
        (
            r"\b(kar|bhej|de|bhar|jama\s+kar)\s*(dunga|dungi|denge|doonga|dungaa|dege|deta|deti)\b",
            0.8,
        ),
        (r"\b(pay|payment)\s+kar\s*(dunga|dungi|denge|doonga)\b", 0.85),
        (r"\btak\s+(pay|payment|bhej|jama|kar|de)", 0.55),
        (r"\b\d{1,2}\s*(tareekh|tarikh|tarik|taarikh)\b", 0.5),
        (r"\bsalary\s+(aane|aate)\s+(par|pe|hi)\b", 0.6),
        (r"\b(next week|agle\s+hafte|agle\s+hafta|pudhchya\s+aathvad\w*)\b", 0.4),
        (r"\b(bharto|bharen|bharin|bharun\s+deto|bharun\s+denar)\b", 0.8),
        (r"(भर दूंगा|भर दूँगा|भेज दूंगा|भेज दूँगा|कर दूंगा|कर दूँगा|जमा कर दूंगा|दे दूंगा)", 0.8),
        (r"(भरतो|भरेन|भरून देतो)", 0.8),
    ],
    "hardship": [
        (r"\b(lost|losing)\s+(my\s+)?(job|employment|income)\b", 0.9),
        (r"\b(job|naukri|naukari|kaam)\s+(chali|chala|chhut|chhoot|gayi|gaya|geli|gela|nahi)", 0.9),
        (r"\b(hospital|hospitali[sz]ed|surgery|accident|medical|illness|bimar|beemar|ill)\b", 0.6),
        (r"\b(emi\s+holiday|moratorium|restructur\w*|reschedul\w*|extension|relief)\b", 0.75),
        (r"\b(\d+|few|some|couple of)\s+(months?|mahine|mahina|mahinon|mahinyan?)\b", 0.45),
        (r"\b(time|samay|mohlat|waqt|vel)\s+(chahiye|chaiye|do|de\s*do|dya|dijiye|milega)", 0.5),
        (r"\b(business|dhandha|dukaan|shop)\s+(band|closed|loss|ghata|nuksan)", 0.85),
        (r"\b(cannot|can'?t|unable to|not able to)\s+(pay|afford)", 0.7),
        (r"\b(death|passed away|expired|guzar|nidhan)\b", 0.7),
        (r"(नौकरी चली|नौकरी छूट|समय चाहिए|मोहलत|बीमार|अस्पताल|नोकरी गेली|वेळ द्या)", 0.85),
    ],
    "already_paid": [
        (r"\b(already|just)\s+(paid|pay|transferred|deposited|cleared)", 0.9),
        (r"\b(i\s+)?(have\s+|had\s+)?(paid|transferred|deposited)\b", 0.55),
        (
            r"\b(payment|paisa|paise|emi)\s+(ho\s*gaya|ho\s*gayi|kar\s*diya|kar\s*diye|bhej\s*diya|"
            r"jama\s*kar\s*diya|bhar\s*diya|zala|jhala)",
            0.9,
        ),
        (
            r"\b(utr|rrn|txn|transaction|ref(erence)?)\s*(no\.?|number|id)?\s*[:#-]?\s*[a-z0-9]{8,}",
            0.6,
        ),
        (r"\b(bharle|bharla|bharli)\b", 0.85),
        (r"(भुगतान कर दिया|पेमेंट हो गया|पैसे भेज दिए|जमा कर दिया|भरले|भरला)", 0.9),
    ],
    "dispute": [
        (
            r"\b(wrong|incorrect|excess|extra|double)\s+(charge|amount|deduction|debit|emi|penalty)",
            0.8,
        ),
        (r"\b(charge|penalty|fine|amount|emi)\s+(is\s+)?(wrong|incorrect|not correct|unfair)", 0.8),
        (r"\bwhy\s+(is|was|has)\s+(my\s+)?(emi|amount|charge|penalty|interest)", 0.6),
        (r"\b(had|have|there was)\s+(sufficient\s+|enough\s+)?balance\b", 0.6),
        (r"\b(complaint|dispute|ombudsman|grievance)\b", 0.7),
        (r"\b(galat|jyada|zyada)\s+(charge|paisa|amount|kata|kaat)", 0.75),
    ],
    "mandate_issue": [
        (
            r"\b(cancel+ed|stopped|revoked|closed)\s+(the\s+|my\s+)?(auto[- ]?debit|mandate|nach|"
            r"e-?mandate|si|standing instruction|autopay)",
            0.9,
        ),
        (r"\b(auto[- ]?debit|mandate|nach|e-?mandate|autopay)\b", 0.45),
        (r"\b(account|khata|a/c)\s+(band|closed|close|changed|badal)", 0.75),
        (r"\b(new|naya|nayi|change)\s+(bank\s+)?(account|mandate|khata)", 0.6),
    ],
    "stop_contact": [
        (r"^\s*stop\s*$", 0.95),
        (r"\b(unsubscribe|opt[- ]?out)\b", 0.9),
        (
            r"\b(stop|don'?t|do not|never)\s+(calling|call|messaging|message|texting|contacting|"
            r"contact)\s*(me)?\b",
            0.85,
        ),
        (r"\b(call|phone|message|msg|sms)\s+(mat|na|nako)\s*(karo|kare|kijiye|kara)?\b", 0.8),
        (r"\b(harass\w*|pareshan)\b", 0.6),
        (r"(कॉल मत करो|फोन मत करो|मैसेज मत करो|परेशान)", 0.8),
    ],
    "wrong_number": [
        (r"\bwrong\s+(number|person|no\.?)\b", 0.95),
        (r"\b(don'?t|do not)\s+have\s+(any|a)\s+loan\b", 0.85),
        (r"\bnot\s+(my|mine)\s+(loan|number)\b", 0.8),
        (r"\b(galat|ghalat)\s+(number|no)\b", 0.95),
        (r"\b(mera|meri)\s+(koi\s+)?loan\s+nahi\b", 0.85),
        (r"(गलत नंबर|चुकीचा नंबर)", 0.95),
    ],
    "callback_request": [
        (r"\b(call|phone)\s+(me\s+)?(back|later|tomorrow|after|in the evening)\b", 0.7),
        (r"\b(please|pls|plz)\s+call\b(?!\s+(mat|na|nako|mut)\b)", 0.55),
        (r"\b(baat|talk|speak)\s+(karni|karna|karo|to)\b", 0.5),
    ],
}
