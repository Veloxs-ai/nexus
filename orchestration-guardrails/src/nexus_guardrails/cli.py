# Copyright 2026 Veloxs AI Inc. All rights reserved.
#
# This file is part of Nexus, proprietary and confidential software of
# Veloxs AI Inc. Use is subject to the Nexus Proprietary Software License;
# see the LICENSE file in the project root. Unauthorized copying,
# distribution, or modification of this file, via any medium, is strictly
# prohibited.
#
# SPDX-License-Identifier: LicenseRef-Veloxs-AI-Proprietary

from __future__ import annotations

import argparse
from pathlib import Path

from nexus_guardrails.config import load_config
from nexus_guardrails.orchestrator import evaluate


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="guardrails", description="AI orchestration and guardrails control plane."
    )
    commands = parser.add_subparsers(dest="command", required=True)

    validate_config = commands.add_parser("validate-config", help="Load and validate a guardrails config.")
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
        print(f"Loaded guardrails for tenant {config.tenant.id} with {len(config.policies)} policies.")
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
