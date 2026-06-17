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

from nexus_experience.config import EngagementConfig


def validate_channel(config: EngagementConfig, channel_name: str, capability: str) -> None:
    channel = config.channels.get(channel_name)
    if channel is None:
        raise ValueError(f"Unknown channel: {channel_name}")
    if not channel.enabled:
        raise ValueError(f"Channel is disabled: {channel_name}")
    if capability not in channel.allowed_capabilities:
        raise ValueError(f"Channel {channel_name} does not allow capability: {capability}")


def enabled_channels(config: EngagementConfig) -> list[str]:
    return sorted(name for name, channel in config.channels.items() if channel.enabled)

