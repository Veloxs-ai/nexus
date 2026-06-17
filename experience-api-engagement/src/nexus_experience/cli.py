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

from pathlib import Path

import typer

from nexus_experience.auth import anonymous_principal
from nexus_experience.config import load_config
from nexus_experience.gateway import build_gateway
from nexus_experience.models import AskRequest
from nexus_experience.service import ExperienceService

app = typer.Typer(help="Experience API and engagement control plane.")


def _build_service(config_path: Path) -> ExperienceService:
    config = load_config(config_path)
    return ExperienceService(config, build_gateway(config, config_path.parent.parent))


@app.command()
def validate_config(config_path: Path) -> None:
    config = load_config(config_path)
    enabled = [name for name, channel in config.channels.items() if channel.enabled]
    typer.echo(f"Loaded {len(enabled)} channels for tenant {config.tenant.id}.")


@app.command()
def ask(config_path: Path, query: str, channel: str = "assistant") -> None:
    service = _build_service(config_path)
    principal = anonymous_principal(service.config)
    response = service.ask(principal, AskRequest(query=query, channel=channel))
    typer.echo(f"decision: {response.decision}")
    typer.echo(f"channel: {response.channel}")
    typer.echo(f"answer: {response.answer}")
    for citation in response.citations:
        typer.echo(f"citation: {citation.collection}:{citation.source_id}:{citation.score:.3f}")


@app.command()
def start_session(config_path: Path, channel: str = "assistant") -> None:
    service = _build_service(config_path)
    principal = anonymous_principal(service.config)
    session = service.start_session(principal, channel=channel)
    typer.echo(f"session_id: {session.session_id}")
    typer.echo(f"greeting: {session.greeting}")


if __name__ == "__main__":
    app()
