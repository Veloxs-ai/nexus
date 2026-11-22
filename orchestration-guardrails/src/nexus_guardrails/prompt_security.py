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

from __future__ import annotations

import re

from .config import PromptSecurityConfig
from .models import Finding
from .normalization import normalize_text


def inspect_prompt(
    prompt: str, config: PromptSecurityConfig, *, include_leakage: bool = True
) -> list[Finding]:
    """Blocked prompt patterns and, unless ``include_leakage`` is False, leakage terms.

    Leakage terms describe what a *user* must not ask for ("password", "api key"). Retrieved
    documents may legitimately mention them (a password policy), so the re-screen of composed
    answers checks only the blocked patterns (injected instructions).
    """
    normalized = normalize_text(prompt).lower()
    findings: list[Finding] = []
    for pattern in config.blocked_patterns:
        if pattern.lower() in normalized:
            findings.append(
                Finding(
                    category="prompt_security",
                    message=f"Blocked prompt pattern: {pattern}",
                    severity="block",
                )
            )
    for term in config.leakage_terms if include_leakage else ():
        if term.lower() in normalized:
            findings.append(
                Finding(
                    category="data_leakage",
                    message=f"Potential leakage request: {term}",
                    severity="block",
                )
            )
    return findings


# Instruction-like text inside documents or user input (indirect prompt injection). The
# rule names are stable: callers show them to a model as the reason a passage is untrusted.
INJECTION_RULES: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "override_instructions",
        re.compile(
            r"\b(ignore|disregard|forget|override|bypass|skip)\b.{0,40}"
            r"\b(previous|prior|above|earlier|all|any|your|the|system)\b.{0,30}\b(instructions?|rules?|prompts?|guidelines?|polic(?:y|ies)"
            r"|guardrails?|constraints?)\b",
            re.I | re.S,
        ),
    ),
    (
        "prompt_exfiltration",
        re.compile(
            r"\b(reveal|show|print|output|repeat|display|leak|tell me|what (?:is|are))\b.{0,40}"
            r"\b(system|initial|hidden|original|developer|secret)\s+"
            r"(prompt|instructions?|message|rules)\b",
            re.I | re.S,
        ),
    ),
    (
        "persona_jailbreak",
        re.compile(
            r"\b(you are now|act as|pretend (?:to be|you are)|roleplay as|from now on you)\b.{0,60}"
            r"\b(unfiltered|uncensored|unrestricted|jailbroken"
            r"|no (?:rules|restrictions|limits|filters)|evil|dan)\b",
            re.I | re.S,
        ),
    ),
    (
        "jailbreak_mode",
        re.compile(
            r"\b(dan mode|developer mode|jailbreak(?:ed)? mode|god mode|do anything now)\b", re.I
        ),
    ),
    (
        "fake_system_turn",
        # Linear time: a line-anchored turn label and possessive spaces inside "<...>" (the
        # former ``(^|\n)\s*`` / ``<\s*/?\s*`` forms were quadratic on long blank runs).
        re.compile(
            r"(?m)^[^\S\n]*(system|assistant)\s*:"
            r"|<\s*+(?:/\s*+)?(system|im_start|im_end)\s*>|\[/?INST\]",
            re.I,
        ),
    ),
)


def detect_injection(text: str) -> list[str]:
    """Names of the injection rules ``text`` matches (empty when clean).

    Runs on the normalised text (NFKC, invisible characters removed) and, when that
    differs, on the text as written, so neither look-alike characters nor a rule that
    needs the original line breaks can hide an instruction.
    """
    raw = (text or "").strip()
    if not raw:
        return []
    views = [raw]
    normalized = normalize_text(raw)
    if normalized != raw:
        views.append(normalized)
    return [name for name, pattern in INJECTION_RULES if any(pattern.search(v) for v in views)]
