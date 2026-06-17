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

from nexus_pipeline.batch import run_batch as run_batch_job
from nexus_pipeline.cdc import run_cdc as run_cdc_job
from nexus_pipeline.config import load_config
from nexus_pipeline.connectors.api import RestApiConnector
from nexus_pipeline.integrity import CheckpointStore, latest_checkpoint, validate_records
from nexus_pipeline.models import IngestionMode
from nexus_pipeline.streaming import run_stream as run_stream_job

app = typer.Typer(help="Enterprise data pipeline control plane.")


@app.command()
def validate_config(config_path: Path) -> None:
    config = load_config(config_path)
    typer.echo(f"Loaded {len(config.sources)} sources.")


@app.command()
def run_batch(config_path: Path, source: str) -> None:
    config = load_config(config_path)
    source_config = config.sources[source]
    checkpoint_store = CheckpointStore(config.platform.checkpoint_store)
    count = run_batch_job(source, source_config, checkpoint_store)
    typer.echo(f"Processed {count} batch records for {source}.")


@app.command()
def run_stream(config_path: Path, source: str) -> None:
    config = load_config(config_path)
    events = run_stream_job(source, config.sources[source])
    typer.echo(f"Processed {len(events)} streaming events for {source}.")


@app.command()
def run_cdc(config_path: Path, source: str) -> None:
    config = load_config(config_path)
    events = run_cdc_job(source, config.sources[source])
    typer.echo(f"Processed {len(events)} CDC events for {source}.")


@app.command()
def run_api(config_path: Path, source: str) -> None:
    config = load_config(config_path)
    source_config = config.sources[source]
    if source_config.mode != IngestionMode.API:
        raise typer.BadParameter(f"{source} is configured as {source_config.mode}, not api.")

    checkpoint_store = CheckpointStore(config.platform.checkpoint_store)
    checkpoint = checkpoint_store.read(source)
    result = validate_records(source, source_config, RestApiConnector(source_config).read(checkpoint))
    next_checkpoint = latest_checkpoint(result.valid)
    if next_checkpoint:
        checkpoint_store.write(source, next_checkpoint)
    typer.echo(f"Processed {len(result.valid)} API records for {source}.")


if __name__ == "__main__":
    app()

