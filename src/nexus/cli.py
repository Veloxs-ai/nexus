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

from nexus.platform import NexusPlatform


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="nexus",
        description=(
            "Nexus — Enterprise Intelligence Framework. Single entry point for the framework."
        ),
    )
    commands = parser.add_subparsers(dest="command", required=True)

    validate_config = commands.add_parser(
        "validate-config", help="Load and validate a platform config."
    )
    validate_config.add_argument("config_path", type=Path)

    layers = commands.add_parser("layers", help="List configured layers.")
    layers.add_argument("config_path", type=Path)

    validate_platform = commands.add_parser(
        "validate-platform", help="Check that every layer is ready."
    )
    validate_platform.add_argument("config_path", type=Path)

    prepare_demo = commands.add_parser(
        "prepare-demo", help="Run processing and index builds for the demo."
    )
    prepare_demo.add_argument("config_path", type=Path)

    ask = commands.add_parser("ask", help="Ask a question through the experience layer.")
    ask.add_argument("config_path", type=Path)
    ask.add_argument("query")
    ask.add_argument("--channel", default="assistant")

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    platform = NexusPlatform.from_config(args.config_path)

    if args.command == "validate-config":
        print(f"Loaded {len(platform.config.layers)} layers.")
    elif args.command == "layers":
        for name, layer in platform.config.layers.items():
            print(f"{name}\t{layer.project_path}\t{layer.responsibility}")
    elif args.command == "validate-platform":
        for status in platform.layer_statuses():
            state = "ready" if status.ready else "missing"
            print(f"{status.name}: {state}")
        print(f"platform_ready: {str(platform.validate()).lower()}")
    elif args.command == "prepare-demo":
        for output in platform.prepare_demo():
            print(output.rstrip())
    elif args.command == "ask":
        print(platform.ask(args.query, args.channel).rstrip())
    return 0


def app() -> None:
    """Console-script entry point (kept for the `nexus.cli:app` script target)."""
    raise SystemExit(main())


if __name__ == "__main__":
    raise SystemExit(main())
