from __future__ import annotations

from nexus_experience.models import AskRequest, AskResponse
from nexus_experience.service import ExperienceService


class ExperienceClient:
    def __init__(self, service: ExperienceService) -> None:
        self.service = service

    def ask(
        self,
        query: str,
        *,
        channel: str = "sdk",
        user_id: str | None = None,
        session_id: str | None = None,
    ) -> AskResponse:
        return self.service.ask(
            AskRequest(
                query=query,
                channel=channel,
                user_id=user_id,
                session_id=session_id,
            )
        )

    def start_session(self, *, user_id: str | None = None, channel: str = "sdk"):
        return self.service.start_session(user_id=user_id, channel=channel)

