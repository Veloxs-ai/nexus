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

from nexus_retrieval.config import load_config
from nexus_retrieval.hybrid import search as run_search
from nexus_retrieval.indexing import build_indexes

app = typer.Typer(help="Embedding and retrieval intelligence control plane.")


@app.command()
def validate_config(config_path: Path) -> None:
    config = load_config(config_path)
    typer.echo(f"Loaded {len(config.collections)} retrieval collections.")


@app.command()
def build_index(config_path: Path) -> None:
    config = load_config(config_path)
    count = build_indexes(config, config_path.parent.parent)
    typer.echo(f"Indexed {count} documents.")


@app.command()
def search(config_path: Path, query: str, limit: int = 5) -> None:
    config = load_config(config_path)
    results = run_search(config, query, config_path.parent.parent, limit=limit)
    for result in results:
        typer.echo(
            f"{result.score:.3f}\t{result.collection}\t{result.id}\t{result.text[:120]}"
        )


if __name__ == "__main__":
    app()

