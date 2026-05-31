from __future__ import annotations

from nexus_experience.auth import anonymous_principal
from nexus_experience.models import AskRequest, AskResponse, Principal
from nexus_experience.service import ExperienceService


class ExperienceClient:
    def __init__(self, service: ExperienceService, principal: Principal | None = None) -> None:
        self.service = service
        self.principal = principal or anonymous_principal(service.config)

    def ask(
        self,
        query: str,
        *,
        channel: str = "sdk",
        session_id: str | None = None,
    ) -> AskResponse:
        return self.service.ask(
            self.principal,
            AskRequest(
                query=query,
                channel=channel,
                session_id=session_id,
            ),
        )

    def start_session(self, *, channel: str = "sdk"):
        return self.service.start_session(self.principal, channel=channel)
