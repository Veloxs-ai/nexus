from __future__ import annotations

from nexus_experience.assistant import AssistantSessionStore
from nexus_experience.channels import validate_channel
from nexus_experience.config import EngagementConfig
from nexus_experience.gateway import AiGateway
from nexus_experience.models import AskRequest, AskResponse


class ExperienceService:
    def __init__(self, config: EngagementConfig, gateway: AiGateway) -> None:
        self.config = config
        self.gateway = gateway
        self.sessions = AssistantSessionStore(config)

    def health(self) -> dict[str, str]:
        return {"status": "ok", "tenant": self.config.tenant.id}

    def start_session(self, user_id: str | None = None, channel: str = "assistant"):
        validate_channel(self.config, channel, "session")
        return self.sessions.start_session(user_id=user_id, channel=channel)

    def ask(self, request: AskRequest) -> AskResponse:
        validate_channel(self.config, request.channel, "ask")
        if request.session_id:
            self.sessions.append_message(request.session_id, "user", request.query)

        decision, answer, citations, metadata = self.gateway.ask(request.query)
        response = AskResponse(
            decision=decision,
            answer=answer,
            citations=citations,
            channel=request.channel,
            tenant_id=self.config.tenant.id,
            session_id=request.session_id,
            metadata=metadata,
        )
        if request.session_id:
            self.sessions.append_message(request.session_id, "assistant", response.answer)
        return response

