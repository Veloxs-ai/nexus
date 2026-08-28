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

import argparse
from pathlib import Path

from .config import load_config
from .orchestrator import evaluate


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="guardrails", description="AI orchestration and guardrails control plane."
    )
    commands = parser.add_subparsers(dest="command", required=True)

    validate_config = commands.add_parser(
        "validate-config", help="Load and validate a guardrails config."
    )
    validate_config.add_argument("config_path", type=Path)

    check = commands.add_parser("check", help="Screen a query against the guardrail policies.")
    check.add_argument("config_path", type=Path)
    check.add_argument("query")

    ask = commands.add_parser("ask", help="Run the full grounded ask flow.")
    ask.add_argument("config_path", type=Path)
    ask.add_argument("query")

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    config = load_config(args.config_path)

    if args.command == "validate-config":
        print(
            f"Loaded guardrails for tenant {config.tenant.id} with {len(config.policies)} policies."
        )
    elif args.command == "check":
        response = evaluate(config, args.query, args.config_path.parent.parent)
        print(f"decision: {response.decision}")
        print(f"masked_query: {response.masked_query}")
        for finding in response.findings:
            print(f"{finding.severity}\t{finding.category}\t{finding.message}")
    elif args.command == "ask":
        response = evaluate(config, args.query, args.config_path.parent.parent)
        print(f"decision: {response.decision}")
        print(f"confidence: {response.confidence:.3f}")
        print(f"answer: {response.answer}")
        for citation in response.citations:
            print(f"citation: {citation.collection}:{citation.source_id}:{citation.score:.3f}")
        for finding in response.findings:
            print(f"finding: {finding.severity}:{finding.category}:{finding.message}")
    return 0


def app() -> None:
    """Console-script entry point (kept for the `nexus_guardrails.cli:app` script target)."""
    raise SystemExit(main())


if __name__ == "__main__":
    raise SystemExit(main())
