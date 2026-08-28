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

from .auth import anonymous_principal
from .config import load_config
from .gateway import build_gateway
from .models import AskRequest
from .service import ExperienceService


def _build_service(config_path: Path) -> ExperienceService:
    config = load_config(config_path)
    return ExperienceService(config, build_gateway(config, config_path.parent.parent))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="experience", description="Experience API and engagement control plane."
    )
    commands = parser.add_subparsers(dest="command", required=True)

    validate_config = commands.add_parser(
        "validate-config", help="Load and validate an engagement config."
    )
    validate_config.add_argument("config_path", type=Path)

    ask = commands.add_parser("ask", help="Ask a question through the engagement service.")
    ask.add_argument("config_path", type=Path)
    ask.add_argument("query")
    ask.add_argument("--channel", default="assistant")

    start_session = commands.add_parser("start-session", help="Start an assistant session.")
    start_session.add_argument("config_path", type=Path)
    start_session.add_argument("--channel", default="assistant")

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if args.command == "validate-config":
        config = load_config(args.config_path)
        enabled = [name for name, channel in config.channels.items() if channel.enabled]
        print(f"Loaded {len(enabled)} channels for tenant {config.tenant.id}.")
    elif args.command == "ask":
        service = _build_service(args.config_path)
        principal = anonymous_principal(service.config)
        response = service.ask(principal, AskRequest(query=args.query, channel=args.channel))
        print(f"decision: {response.decision}")
        print(f"channel: {response.channel}")
        print(f"answer: {response.answer}")
        for citation in response.citations:
            print(f"citation: {citation.collection}:{citation.source_id}:{citation.score:.3f}")
    elif args.command == "start-session":
        service = _build_service(args.config_path)
        principal = anonymous_principal(service.config)
        session = service.start_session(principal, channel=args.channel)
        print(f"session_id: {session.session_id}")
        print(f"greeting: {session.greeting}")
    return 0


def app() -> None:
    """Console-script entry point (kept for the `nexus_experience.cli:app` script target)."""
    raise SystemExit(main())


if __name__ == "__main__":
    raise SystemExit(main())
