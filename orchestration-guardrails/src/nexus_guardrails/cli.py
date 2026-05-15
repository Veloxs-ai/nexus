from __future__ import annotations

from pathlib import Path

import typer

from nexus_guardrails.config import load_config
from nexus_guardrails.orchestrator import evaluate

app = typer.Typer(help="AI orchestration and guardrails control plane.")


@app.command()
def validate_config(config_path: Path) -> None:
    config = load_config(config_path)
    typer.echo(f"Loaded guardrails for tenant {config.tenant.id} with {len(config.policies)} policies.")


@app.command()
def check(config_path: Path, query: str) -> None:
    config = load_config(config_path)
    response = evaluate(config, query, config_path.parent.parent)
    typer.echo(f"decision: {response.decision}")
    typer.echo(f"masked_query: {response.masked_query}")
    for finding in response.findings:
        typer.echo(f"{finding.severity}\t{finding.category}\t{finding.message}")


@app.command()
def ask(config_path: Path, query: str) -> None:
    config = load_config(config_path)
    response = evaluate(config, query, config_path.parent.parent)
    typer.echo(f"decision: {response.decision}")
    typer.echo(f"confidence: {response.confidence:.3f}")
    typer.echo(f"answer: {response.answer}")
    for citation in response.citations:
        typer.echo(f"citation: {citation.collection}:{citation.source_id}:{citation.score:.3f}")
    for finding in response.findings:
        typer.echo(f"finding: {finding.severity}:{finding.category}:{finding.message}")


if __name__ == "__main__":
    app()

