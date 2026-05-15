from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer

from nexus_experience.config import load_config
from nexus_experience.gateway import build_gateway
from nexus_experience.models import AskRequest
from nexus_experience.service import ExperienceService

app = typer.Typer(help="Experience API and engagement control plane.")


@app.command()
def validate_config(config_path: Path) -> None:
    config = load_config(config_path)
    enabled = [name for name, channel in config.channels.items() if channel.enabled]
    typer.echo(f"Loaded {len(enabled)} channels for tenant {config.tenant.id}.")


@app.command()
def ask(config_path: Path, query: str, channel: str = "assistant") -> None:
    config = load_config(config_path)
    service = ExperienceService(config, build_gateway(config, config_path.parent.parent))
    response = service.ask(AskRequest(query=query, channel=channel))
    typer.echo(f"decision: {response.decision}")
    typer.echo(f"channel: {response.channel}")
    typer.echo(f"answer: {response.answer}")
    for citation in response.citations:
        typer.echo(f"citation: {citation.collection}:{citation.source_id}:{citation.score:.3f}")


@app.command()
def start_session(config_path: Path, user_id: Optional[str] = None, channel: str = "assistant") -> None:
    config = load_config(config_path)
    service = ExperienceService(config, build_gateway(config, config_path.parent.parent))
    session = service.start_session(user_id=user_id, channel=channel)
    typer.echo(f"session_id: {session.session_id}")
    typer.echo(f"greeting: {session.greeting}")


if __name__ == "__main__":
    app()
