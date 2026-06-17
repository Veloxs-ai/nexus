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
from pathlib import Path

from nexus_experience.auth import Authorizer
from nexus_experience.config import load_config
from nexus_experience.gateway import build_gateway
from nexus_experience.models import AskRequest
from nexus_experience.service import ExperienceService

CONFIG_ENV_VAR = "NEXUS_EXPERIENCE_CONFIG"


def _resolve_config_path(config_path: Path | None) -> Path:
    if config_path is not None:
        return config_path
    from_env = os.environ.get(CONFIG_ENV_VAR)
    if not from_env:
        raise ValueError(
            f"config_path is required; pass an explicit Path or set ${CONFIG_ENV_VAR}."
        )
    return Path(from_env)


def create_service(
    config_path: Path | None = None,
    authorizer: Authorizer | None = None,
) -> ExperienceService:
    path = _resolve_config_path(config_path)
    config = load_config(path)
    return ExperienceService(config, build_gateway(config, path.parent.parent), authorizer)


def create_app(config_path: Path | None = None, authorizer: Authorizer | None = None):
    try:
        from fastapi import Depends, FastAPI, Header, HTTPException
    except ImportError as exc:
        raise RuntimeError("Install API dependencies with: pip install -e '.[api]'") from exc

    from nexus_experience.auth import AuthError, verify_api_key

    service = create_service(config_path, authorizer)
    header_name = service.config.auth.header_name
    app = FastAPI(title=service.config.api.title, version=service.config.api.version)

    def get_principal(api_key: str | None = Header(default=None, alias=header_name)):
        try:
            return verify_api_key(service.config, api_key)
        except AuthError as exc:
            raise HTTPException(status_code=401, detail=str(exc)) from exc

    @app.get("/health")
    def health():
        return service.health()

    @app.post("/v1/ask")
    def ask(request: AskRequest, principal=Depends(get_principal)):
        try:
            return service.ask(principal, request)
        except AuthError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="session not found") from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/v1/sessions")
    def start_session(channel: str = "assistant", principal=Depends(get_principal)):
        try:
            return service.start_session(principal, channel=channel)
        except AuthError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    return app
