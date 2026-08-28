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

from .config import EngagementConfig


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
