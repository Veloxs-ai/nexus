# Copyright 2026 Veloxs AI Inc. All rights reserved.
#
# This file is part of Nexus, proprietary and confidential software of
# Veloxs AI Inc. Use is subject to the Nexus Proprietary Software License;
# see the LICENSE file in the project root. Unauthorized copying,
# distribution, or modification of this file, via any medium, is strictly
# prohibited.
#
# SPDX-License-Identifier: LicenseRef-Veloxs-AI-Proprietary

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
