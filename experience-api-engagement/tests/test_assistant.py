from nexus_experience.assistant import AssistantSessionStore


def test_start_session_uses_configured_greeting(sample_config):
    store = AssistantSessionStore(sample_config)

    session = store.start_session(user_id="u1")

    assert session.user_id == "u1"
    assert session.greeting == "Hello"


def test_append_message_trims_history(sample_config):
    store = AssistantSessionStore(sample_config)
    session = store.start_session()

    store.append_message(session.session_id, "user", "one")
    store.append_message(session.session_id, "assistant", "two")
    store.append_message(session.session_id, "user", "three")

    assert [message["content"] for message in store.get(session.session_id).history] == ["two", "three"]

