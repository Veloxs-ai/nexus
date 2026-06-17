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

import os
from typing import Any, Iterable
from urllib.parse import urlparse

import httpx

from nexus_pipeline.connectors.base import Connector


class ConnectorSecurityError(Exception):
    """Raised when an upstream response would cause an unsafe request."""


def _same_origin(base_url: str, target: str) -> bool:
    base = urlparse(base_url)
    parsed = urlparse(target)
    if parsed.scheme and parsed.scheme not in {"http", "https"}:
        return False
    if not parsed.netloc:
        return not parsed.scheme
    return (parsed.scheme, parsed.netloc) == (base.scheme, base.netloc)


class RestApiConnector(Connector):
    def read(self, checkpoint: str | None = None) -> Iterable[dict[str, Any]]:
        connection = self.source.connection
        base_url = connection["base_url"]
        token = os.getenv(connection["auth_env"], "")
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        params: dict[str, Any] = {"limit": connection.get("page_size", 500)}
        if checkpoint:
            params["updated_after"] = checkpoint

        with httpx.Client(base_url=base_url, timeout=30) as client:
            next_path: str | None = connection["endpoint"]
            while next_path:
                if not _same_origin(base_url, next_path):
                    raise ConnectorSecurityError(
                        f"refusing to follow cross-origin next link: {next_path!r}"
                    )
                response = client.get(next_path, headers=headers, params=params)
                response.raise_for_status()
                body = response.json()
                yield from body.get("data", [])
                next_path = body.get("next")
                params = {}
