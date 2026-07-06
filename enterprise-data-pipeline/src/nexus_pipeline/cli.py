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
import sys
from pathlib import Path

from nexus_pipeline.batch import run_batch as run_batch_job
from nexus_pipeline.cdc import run_cdc as run_cdc_job
from nexus_pipeline.config import load_config
from nexus_pipeline.connectors.api import RestApiConnector
from nexus_pipeline.integrity import CheckpointStore, latest_checkpoint, validate_records
from nexus_pipeline.models import IngestionMode
from nexus_pipeline.streaming import run_stream as run_stream_job


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="pipeline", description="Enterprise data pipeline control plane."
    )
    commands = parser.add_subparsers(dest="command", required=True)

    validate_config = commands.add_parser("validate-config", help="Load and validate a sources config.")
    validate_config.add_argument("config_path", type=Path)

    for name, help_text in (
        ("run-batch", "Ingest a batch source."),
        ("run-stream", "Ingest a streaming source."),
        ("run-cdc", "Ingest a CDC source."),
        ("run-api", "Ingest a REST API source."),
    ):
        sub = commands.add_parser(name, help=help_text)
        sub.add_argument("config_path", type=Path)
        sub.add_argument("source")

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    config = load_config(args.config_path)

    if args.command == "validate-config":
        print(f"Loaded {len(config.sources)} sources.")
    elif args.command == "run-batch":
        source_config = config.sources[args.source]
        checkpoint_store = CheckpointStore(config.platform.checkpoint_store)
        count = run_batch_job(args.source, source_config, checkpoint_store)
        print(f"Processed {count} batch records for {args.source}.")
    elif args.command == "run-stream":
        events = run_stream_job(args.source, config.sources[args.source])
        print(f"Processed {len(events)} streaming events for {args.source}.")
    elif args.command == "run-cdc":
        events = run_cdc_job(args.source, config.sources[args.source])
        print(f"Processed {len(events)} CDC events for {args.source}.")
    elif args.command == "run-api":
        source_config = config.sources[args.source]
        if source_config.mode != IngestionMode.API:
            print(f"error: {args.source} is configured as {source_config.mode}, not api.", file=sys.stderr)
            return 2
        checkpoint_store = CheckpointStore(config.platform.checkpoint_store)
        checkpoint = checkpoint_store.read(args.source)
        result = validate_records(
            args.source, source_config, RestApiConnector(source_config).read(checkpoint)
        )
        next_checkpoint = latest_checkpoint(result.valid)
        if next_checkpoint:
            checkpoint_store.write(args.source, next_checkpoint)
        print(f"Processed {len(result.valid)} API records for {args.source}.")
    return 0


def app() -> None:
    """Console-script entry point (kept for the `nexus_pipeline.cli:app` script target)."""
    raise SystemExit(main())


if __name__ == "__main__":
    raise SystemExit(main())
