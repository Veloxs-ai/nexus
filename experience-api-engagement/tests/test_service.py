from nexus_experience.models import AskRequest


def test_health_returns_tenant(sample_service):
    assert sample_service.health() == {"status": "ok", "tenant": "test"}


def test_ask_returns_standardized_response(sample_service):
    response = sample_service.ask(AskRequest(query="What is MFA?", channel="assistant"))

    assert response.decision == "allowed"
    assert response.channel == "assistant"
    assert response.tenant_id == "test"
    assert response.citations[0].source_id == "mock-source"


def test_ask_updates_assistant_session_history(sample_service):
    session = sample_service.start_session(user_id="u1", channel="assistant")

    response = sample_service.ask(
        AskRequest(query="What is MFA?", channel="assistant", session_id=session.session_id)
    )

    assert response.session_id == session.session_id
    assert len(sample_service.sessions.get(session.session_id).history) == 2


def test_ask_rejects_channel_without_capability(sample_service):
    try:
        sample_service.ask(AskRequest(query="hello", channel="disabled"))
    except ValueError as exc:
        assert "disabled" in str(exc)
    else:
        raise AssertionError("Expected ValueError")

