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

from .assistant import AssistantSessionStore
from .auth import AuthError, Authorizer, default_authorizer
from .channels import validate_channel
from .config import EngagementConfig
from .gateway import AiGateway
from .models import AskRequest, AskResponse, Principal


class ExperienceService:
    def __init__(
        self,
        config: EngagementConfig,
        gateway: AiGateway,
        authorizer: Authorizer | None = None,
    ) -> None:
        self.config = config
        self.gateway = gateway
        self.sessions = AssistantSessionStore(config)
        self.authorizer = authorizer or default_authorizer

    def health(self) -> dict[str, str]:
        return {"status": "ok", "tenant": self.config.tenant.id}

    def start_session(self, principal: Principal, channel: str = "assistant"):
        validate_channel(self.config, channel, "session")
        if self.config.auth.enabled:
            self.authorizer(principal, "session", self.config.tenant.id)
        return self.sessions.start_session(
            user_id=principal.user_id,
            tenant_id=principal.tenant_id,
            channel=channel,
        )

    def ask(self, principal: Principal, request: AskRequest) -> AskResponse:
        validate_channel(self.config, request.channel, "ask")
        if self.config.auth.enabled:
            self.authorizer(principal, "ask", self.config.tenant.id)

        max_chars = self.config.auth.max_query_chars
        if max_chars > 0 and len(request.query) > max_chars:
            raise AuthError(f"query exceeds maximum length of {max_chars} characters")

        if request.session_id:
            session = self.sessions.get(request.session_id)
            if session.user_id != principal.user_id or session.tenant_id != principal.tenant_id:
                raise AuthError("session does not belong to this principal")
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
