from __future__ import annotations

from pathlib import Path

from nexus_experience.config import load_config
from nexus_experience.gateway import build_gateway
from nexus_experience.models import AskRequest
from nexus_experience.service import ExperienceService


def create_service(config_path: Path | None = None) -> ExperienceService:
    path = config_path or Path("configs/engagement.yaml")
    config = load_config(path)
    return ExperienceService(config, build_gateway(config, path.parent.parent))


def create_app():
    try:
        from fastapi import FastAPI
    except ImportError as exc:
        raise RuntimeError("Install API dependencies with: pip install -e '.[api]'") from exc

    service = create_service()
    app = FastAPI(title=service.config.api.title, version=service.config.api.version)

    @app.get("/health")
    def health():
        return service.health()

    @app.post("/v1/ask")
    def ask(request: AskRequest):
        return service.ask(request)

    @app.post("/v1/sessions")
    def start_session(user_id: str | None = None, channel: str = "assistant"):
        return service.start_session(user_id=user_id, channel=channel)

    return app

