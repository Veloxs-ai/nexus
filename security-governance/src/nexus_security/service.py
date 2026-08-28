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

from pathlib import Path

from .audit import AuditLogger
from .config import SecurityConfig
from .encryption import decrypt_text, encrypt_text, validate_tls
from .models import AccessDecision, AccessRequest, AuditEvent, Decision
from .observability import ObservabilityRecorder
from .rbac import authorize


class SecurityGovernanceService:
    def __init__(self, config: SecurityConfig, base_dir: Path) -> None:
        self.config = config
        self.audit = AuditLogger(config.audit, base_dir)
        self.observability = ObservabilityRecorder(config.observability, base_dir)

    def check_access(self, request: AccessRequest) -> AccessDecision:
        decision = authorize(self.config, request)
        self.audit.record(
            AuditEvent(
                event_type="access.check",
                actor_id=request.subject_id or request.role,
                tenant_id=request.user_tenant,
                decision=decision.decision,
                details={"permission": request.permission, "reason": decision.reason},
            )
        )
        self.observability.emit(
            "access_check",
            1,
            {"decision": decision.decision.value, "permission": request.permission},
        )
        return decision

    def encrypt(self, plaintext: str) -> str:
        return encrypt_text(plaintext, self.config.encryption)

    def decrypt(self, ciphertext: str) -> str:
        return decrypt_text(ciphertext, self.config.encryption)

    def tls_allowed(self, tls_version: str | None) -> bool:
        return validate_tls(self.config.encryption, tls_version)

    def record_event(
        self, event_type: str, actor_id: str, tenant_id: str, decision: Decision
    ) -> None:
        self.audit.record(
            AuditEvent(
                event_type=event_type,
                actor_id=actor_id,
                tenant_id=tenant_id,
                decision=decision,
            )
        )
