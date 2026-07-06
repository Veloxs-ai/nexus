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

from nexus_retrieval.config import load_config
from nexus_retrieval.hybrid import search as run_search
from nexus_retrieval.indexing import build_indexes


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="retrieval", description="Embedding and retrieval intelligence control plane."
    )
    commands = parser.add_subparsers(dest="command", required=True)

    validate_config = commands.add_parser("validate-config", help="Load and validate a retrieval config.")
    validate_config.add_argument("config_path", type=Path)

    build_index = commands.add_parser("build-index", help="Build vector, lexical, and graph indexes.")
    build_index.add_argument("config_path", type=Path)

    search = commands.add_parser("search", help="Run a hybrid search query.")
    search.add_argument("config_path", type=Path)
    search.add_argument("query")
    search.add_argument("--limit", type=int, default=5)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    config = load_config(args.config_path)

    if args.command == "validate-config":
        print(f"Loaded {len(config.collections)} retrieval collections.")
    elif args.command == "build-index":
        count = build_indexes(config, args.config_path.parent.parent)
        print(f"Indexed {count} documents.")
    elif args.command == "search":
        results = run_search(config, args.query, args.config_path.parent.parent, limit=args.limit)
        for result in results:
            print(f"{result.score:.3f}\t{result.collection}\t{result.id}\t{result.text[:120]}")
    return 0


def app() -> None:
    """Console-script entry point (kept for the `nexus_retrieval.cli:app` script target)."""
    raise SystemExit(main())


if __name__ == "__main__":
    raise SystemExit(main())
