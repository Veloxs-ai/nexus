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

from .config import EngagementConfig
from .models import AssistantSession


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
