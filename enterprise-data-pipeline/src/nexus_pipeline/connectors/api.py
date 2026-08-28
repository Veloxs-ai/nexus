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

import json
import os
import urllib.request
from collections.abc import Iterable
from typing import Any
from urllib.parse import urlencode, urljoin, urlparse

from ..connectors.base import Connector

_TIMEOUT_SECONDS = 30


class ConnectorSecurityError(Exception):
    """Raised when an upstream response would cause an unsafe request."""


class _RefuseRedirects(urllib.request.HTTPRedirectHandler):
    """Fail closed on any HTTP redirect — a redirect can silently change origin."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ConnectorSecurityError(f"refusing to follow HTTP redirect to {newurl!r}")


def _same_origin(base_url: str, target: str) -> bool:
    base = urlparse(base_url)
    parsed = urlparse(target)
    if parsed.scheme and parsed.scheme not in {"http", "https"}:
        return False
    if not parsed.netloc:
        return not parsed.scheme
    return (parsed.scheme, parsed.netloc) == (base.scheme, base.netloc)


def _fetch_json(url: str, headers: dict[str, str]) -> Any:
    """GET a URL with stdlib urllib; redirects are refused, HTTP >= 400 raises."""
    request = urllib.request.Request(url, headers=headers, method="GET")
    opener = urllib.request.build_opener(_RefuseRedirects())
    with opener.open(request, timeout=_TIMEOUT_SECONDS) as response:
        return json.loads(response.read().decode("utf-8"))


class RestApiConnector(Connector):
    def read(self, checkpoint: str | None = None) -> Iterable[dict[str, Any]]:
        connection = self.source.connection
        base_url = connection["base_url"]
        if urlparse(base_url).scheme not in {"http", "https"}:
            raise ConnectorSecurityError(f"base_url must be http(s), got: {base_url!r}")
        token = os.getenv(connection["auth_env"], "")
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        params: dict[str, Any] = {"limit": connection.get("page_size", 500)}
        if checkpoint:
            params["updated_after"] = checkpoint

        next_path: str | None = connection["endpoint"]
        while next_path:
            if not _same_origin(base_url, next_path):
                raise ConnectorSecurityError(
                    f"refusing to follow cross-origin next link: {next_path!r}"
                )
            url = urljoin(
                base_url.rstrip("/") + "/",
                next_path.lstrip("/") if not urlparse(next_path).netloc else next_path,
            )
            if not _same_origin(base_url, url):
                raise ConnectorSecurityError(f"refusing to request cross-origin URL: {url!r}")
            if params:
                url = url + ("&" if urlparse(url).query else "?") + urlencode(params)
            body = _fetch_json(url, headers)
            yield from body.get("data", [])
            next_path = body.get("next")
            params = {}
