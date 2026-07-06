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

from nexus_processing.config import load_config
from nexus_processing.pipeline import hydrate_job_defaults, run_all as run_all_jobs
from nexus_processing.pipeline import run_job as run_single_job


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="processing", description="Data processing and enrichment control plane."
    )
    commands = parser.add_subparsers(dest="command", required=True)

    validate_config = commands.add_parser("validate-config", help="Load and validate a processing config.")
    validate_config.add_argument("config_path", type=Path)

    run_job = commands.add_parser("run-job", help="Run a single processing job.")
    run_job.add_argument("config_path", type=Path)
    run_job.add_argument("job")

    run_all = commands.add_parser("run-all", help="Run every processing job.")
    run_all.add_argument("config_path", type=Path)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    config = hydrate_job_defaults(load_config(args.config_path))

    if args.command == "validate-config":
        print(f"Loaded {len(config.jobs)} processing jobs.")
    elif args.command == "run-job":
        count = run_single_job(config, args.job, args.config_path.parent.parent)
        print(f"Processed {count} outputs for {args.job}.")
    elif args.command == "run-all":
        counts = run_all_jobs(config, args.config_path.parent.parent)
        for job, count in counts.items():
            print(f"Processed {count} outputs for {job}.")
    return 0


def app() -> None:
    """Console-script entry point (kept for the `nexus_processing.cli:app` script target)."""
    raise SystemExit(main())


if __name__ == "__main__":
    raise SystemExit(main())
