from __future__ import annotations

import os
from typing import Any, Iterable

import httpx

from nexus_pipeline.connectors.base import Connector


class RestApiConnector(Connector):
    def read(self, checkpoint: str | None = None) -> Iterable[dict[str, Any]]:
        connection = self.source.connection
        token = os.getenv(connection["auth_env"], "")
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        params: dict[str, Any] = {"limit": connection.get("page_size", 500)}
        if checkpoint:
            params["updated_after"] = checkpoint

        with httpx.Client(base_url=connection["base_url"], timeout=30) as client:
            next_path: str | None = connection["endpoint"]
            while next_path:
                response = client.get(next_path, headers=headers, params=params)
                response.raise_for_status()
                body = response.json()
                yield from body.get("data", [])
                next_path = body.get("next")
                params = {}

