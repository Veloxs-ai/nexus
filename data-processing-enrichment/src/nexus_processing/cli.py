from __future__ import annotations

from pathlib import Path

import typer

from nexus_processing.config import load_config
from nexus_processing.pipeline import hydrate_job_defaults, run_all as run_all_jobs
from nexus_processing.pipeline import run_job as run_single_job

app = typer.Typer(help="Data processing and enrichment control plane.")


@app.command()
def validate_config(config_path: Path) -> None:
    config = hydrate_job_defaults(load_config(config_path))
    typer.echo(f"Loaded {len(config.jobs)} processing jobs.")


@app.command()
def run_job(config_path: Path, job: str) -> None:
    config = hydrate_job_defaults(load_config(config_path))
    count = run_single_job(config, job, config_path.parent.parent)
    typer.echo(f"Processed {count} outputs for {job}.")


@app.command()
def run_all(config_path: Path) -> None:
    config = hydrate_job_defaults(load_config(config_path))
    counts = run_all_jobs(config, config_path.parent.parent)
    for job, count in counts.items():
        typer.echo(f"Processed {count} outputs for {job}.")


if __name__ == "__main__":
    app()

