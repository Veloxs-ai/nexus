from __future__ import annotations

from nexus_experience.config import EngagementConfig
from nexus_experience.models import AssistantSession


class AssistantSessionStore:
    def __init__(self, config: EngagementConfig) -> None:
        self.config = config
        self.sessions: dict[str, AssistantSession] = {}

    def start_session(
        self,
        user_id: str | None = None,
        tenant_id: str | None = None,
        channel: str = "assistant",
    ) -> AssistantSession:
        session = AssistantSession(
            user_id=user_id,
            tenant_id=tenant_id,
            channel=channel,
            greeting=self.config.assistant.greeting,
        )
        self.sessions[session.session_id] = session
        return session

    def append_message(self, session_id: str, role: str, content: str) -> None:
        session = self.sessions[session_id]
        session.history.append({"role": role, "content": content})
        max_messages = self.config.assistant.max_history_messages
        if len(session.history) > max_messages:
            session.history = session.history[-max_messages:]

    def get(self, session_id: str) -> AssistantSession:
        return self.sessions[session_id]

