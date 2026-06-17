# Copyright 2026 Veloxs AI Inc. All rights reserved.
#
# This file is part of Nexus, proprietary and confidential software of
# Veloxs AI Inc. Use is subject to the Nexus Proprietary Software License;
# see the LICENSE file in the project root. Unauthorized copying,
# distribution, or modification of this file, via any medium, is strictly
# prohibited.
#
# SPDX-License-Identifier: LicenseRef-Veloxs-AI-Proprietary

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

