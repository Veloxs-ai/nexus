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

from nexus_security.audit import AuditLogger
from nexus_security.config import AuditConfig
from nexus_security.models import AuditEvent, Decision


def test_audit_logger_writes_jsonl(tmp_path):
    logger = AuditLogger(AuditConfig(output_uri="audit.jsonl"), tmp_path)

    logger.record(
        AuditEvent(
            event_type="user.login",
            actor_id="u1",
            tenant_id="tenant-a",
            decision=Decision.ALLOWED,
        )
    )

    records = logger.read_all()
    assert records[0]["event_type"] == "user.login"


def test_audit_logger_can_skip_denied_events(tmp_path):
    logger = AuditLogger(
        AuditConfig(output_uri="audit.jsonl", include_denied_events=False),
        tmp_path,
    )

    logger.record(
        AuditEvent(
            event_type="access.check",
            actor_id="u1",
            tenant_id="tenant-a",
            decision=Decision.DENIED,
        )
    )

    assert logger.read_all() == []
