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

from .auth import anonymous_principal
from .models import AskRequest, AskResponse, Principal
from .service import ExperienceService


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
