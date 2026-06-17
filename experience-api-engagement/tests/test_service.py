# Copyright 2026 Veloxs AI Inc. All rights reserved.
#
# This file is part of Nexus, proprietary and confidential software of
# Veloxs AI Inc. Use is subject to the Nexus Proprietary Software License;
# see the LICENSE file in the project root. Unauthorized copying,
# distribution, or modification of this file, via any medium, is strictly
# prohibited.
#
# SPDX-License-Identifier: LicenseRef-Veloxs-AI-Proprietary

import pytest

from nexus_experience.auth import AuthError, anonymous_principal
from nexus_experience.models import AskRequest, Principal


def test_health_returns_tenant(sample_service):
    assert sample_service.health() == {"status": "ok", "tenant": "test"}


def test_ask_returns_standardized_response(sample_service):
    principal = anonymous_principal(sample_service.config)
    response = sample_service.ask(principal, AskRequest(query="What is MFA?", channel="assistant"))

    assert response.decision == "allowed"
    assert response.channel == "assistant"
    assert response.tenant_id == "test"
    assert response.citations[0].source_id == "mock-source"


def test_ask_updates_assistant_session_history(sample_service):
    principal = anonymous_principal(sample_service.config)
    session = sample_service.start_session(principal, channel="assistant")

    response = sample_service.ask(
        principal,
        AskRequest(query="What is MFA?", channel="assistant", session_id=session.session_id),
    )

    assert response.session_id == session.session_id
    assert len(sample_service.sessions.get(session.session_id).history) == 2


def test_ask_rejects_channel_without_capability(sample_service):
    principal = anonymous_principal(sample_service.config)
    with pytest.raises(ValueError) as exc:
        sample_service.ask(principal, AskRequest(query="hello", channel="disabled"))
    assert "disabled" in str(exc.value)


def test_ask_rejects_session_owned_by_other_principal(sample_service):
    owner = anonymous_principal(sample_service.config)
    session = sample_service.start_session(owner, channel="assistant")

    intruder = Principal(user_id="someone-else", tenant_id="test", role="anonymous")
    with pytest.raises(AuthError):
        sample_service.ask(
            intruder,
            AskRequest(query="hi", channel="assistant", session_id=session.session_id),
        )


def test_ask_enforces_max_query_chars(sample_service):
    sample_service.config.auth.max_query_chars = 10
    principal = anonymous_principal(sample_service.config)

    with pytest.raises(AuthError):
        sample_service.ask(principal, AskRequest(query="x" * 11, channel="assistant"))


def test_authorizer_denies_when_required_capability_missing(sample_config):
    from nexus_experience.gateway import MockGuardrailsGateway
    from nexus_experience.service import ExperienceService

    sample_config.auth.enabled = True
    service = ExperienceService(sample_config, MockGuardrailsGateway())
    principal = Principal(
        user_id="u1",
        tenant_id="test",
        role="reader",
        permissions=["session"],
    )

    with pytest.raises(AuthError):
        service.ask(principal, AskRequest(query="hi", channel="assistant"))
