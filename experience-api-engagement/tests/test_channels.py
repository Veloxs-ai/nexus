from nexus_experience.channels import enabled_channels, validate_channel


def test_validate_channel_allows_enabled_capability(sample_config):
    validate_channel(sample_config, "assistant", "ask")


def test_validate_channel_rejects_unknown_channel(sample_config):
    try:
        validate_channel(sample_config, "unknown", "ask")
    except ValueError as exc:
        assert "Unknown channel" in str(exc)
    else:
        raise AssertionError("Expected ValueError")


def test_validate_channel_rejects_disabled_channel(sample_config):
    try:
        validate_channel(sample_config, "disabled", "ask")
    except ValueError as exc:
        assert "disabled" in str(exc)
    else:
        raise AssertionError("Expected ValueError")


def test_enabled_channels_returns_only_enabled(sample_config):
    assert enabled_channels(sample_config) == ["assistant", "sdk"]

