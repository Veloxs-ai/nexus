from __future__ import annotations

from pathlib import Path

import typer

from nexus.platform import NexusPlatform

app = typer.Typer(help="Single entry point for the Nexus enterprise AI platform.")


@app.command()
def validate_config(config_path: Path) -> None:
    platform = NexusPlatform.from_config(config_path)
    typer.echo(f"Loaded {len(platform.config.layers)} layers.")


@app.command()
def layers(config_path: Path) -> None:
    platform = NexusPlatform.from_config(config_path)
    for name, layer in platform.config.layers.items():
        typer.echo(f"{name}\t{layer.project_path}\t{layer.responsibility}")


@app.command()
def validate_platform(config_path: Path) -> None:
    platform = NexusPlatform.from_config(config_path)
    for status in platform.layer_statuses():
        state = "ready" if status.ready else "missing"
        typer.echo(f"{status.name}: {state}")
    typer.echo(f"platform_ready: {str(platform.validate()).lower()}")


@app.command()
def prepare_demo(config_path: Path) -> None:
    platform = NexusPlatform.from_config(config_path)
    for output in platform.prepare_demo():
        typer.echo(output.rstrip())


@app.command()
def ask(config_path: Path, query: str, channel: str = "assistant") -> None:
    platform = NexusPlatform.from_config(config_path)
    typer.echo(platform.ask(query, channel).rstrip())


if __name__ == "__main__":
    app()
