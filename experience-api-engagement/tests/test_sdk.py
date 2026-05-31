from nexus_experience.sdk import ExperienceClient


def test_sdk_client_ask_uses_service(sample_service):
    client = ExperienceClient(sample_service)

    response = client.ask("What is MFA?", channel="sdk")

    assert response.decision == "allowed"
    assert response.channel == "sdk"


def test_sdk_client_starts_session(sample_service):
    client = ExperienceClient(sample_service)

    session = client.start_session(channel="sdk")

    assert session.user_id == "anonymous"
    assert session.tenant_id == "test"
    assert session.channel == "sdk"
