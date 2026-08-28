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
