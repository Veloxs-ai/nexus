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

from pathlib import Path

from nexus_security.audit import AuditLogger
from nexus_security.config import SecurityConfig
from nexus_security.encryption import decrypt_text, encrypt_text, validate_tls
from nexus_security.models import AccessDecision, AccessRequest, AuditEvent, Decision
from nexus_security.observability import ObservabilityRecorder
from nexus_security.rbac import authorize


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

    def record_event(self, event_type: str, actor_id: str, tenant_id: str, decision: Decision) -> None:
        self.audit.record(
            AuditEvent(
                event_type=event_type,
                actor_id=actor_id,
                tenant_id=tenant_id,
                decision=decision,
            )
        )

