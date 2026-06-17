# Copyright 2026 Veloxs AI Inc. All rights reserved.
#
# This file is part of Nexus, proprietary and confidential software of
# Veloxs AI Inc. Use is subject to the Nexus Proprietary Software License;
# see the LICENSE file in the project root. Unauthorized copying,
# distribution, or modification of this file, via any medium, is strictly
# prohibited.
#
# SPDX-License-Identifier: LicenseRef-Veloxs-AI-Proprietary

"""Single entry point for the Nexus enterprise AI platform."""

from nexus.config import load_config
from nexus.platform import NexusPlatform

__all__ = ["NexusPlatform", "load_config"]

__version__ = "0.1.0"

