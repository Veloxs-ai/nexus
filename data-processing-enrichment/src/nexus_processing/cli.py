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
from .pipeline import hydrate_job_defaults
from .pipeline import run_all as run_all_jobs
from .pipeline import run_job as run_single_job


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="processing", description="Data processing and enrichment control plane."
    )
    commands = parser.add_subparsers(dest="command", required=True)

    validate_config = commands.add_parser(
        "validate-config", help="Load and validate a processing config."
    )
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
