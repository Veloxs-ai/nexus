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

"""Nexus — Enterprise Intelligence Framework.

An open-source framework for building secure, governed AI applications,
retrieval systems, agents, and intelligent workflows.
"""

from __future__ import annotations

import sys

try:
    from nexus import pipeline
except (ImportError, ModuleNotFoundError):
    try:
        import nexus_pipeline as pipeline
    except (ImportError, ModuleNotFoundError):
        pipeline = None

try:
    from nexus import processing
except (ImportError, ModuleNotFoundError):
    try:
        import nexus_processing as processing
    except (ImportError, ModuleNotFoundError):
        processing = None

try:
    from nexus import retrieval
except (ImportError, ModuleNotFoundError):
    try:
        import nexus_retrieval as retrieval
    except (ImportError, ModuleNotFoundError):
        retrieval = None

try:
    from nexus import guardrails
except (ImportError, ModuleNotFoundError):
    try:
        import nexus_guardrails as guardrails
    except (ImportError, ModuleNotFoundError):
        guardrails = None

try:
    from nexus import experience
except (ImportError, ModuleNotFoundError):
    try:
        import nexus_experience as experience
    except (ImportError, ModuleNotFoundError):
        experience = None

try:
    from nexus import security
except (ImportError, ModuleNotFoundError):
    try:
        import nexus_security as security
    except (ImportError, ModuleNotFoundError):
        security = None

try:
    from nexus import observability
except (ImportError, ModuleNotFoundError):
    try:
        import nexus_observability as observability
    except (ImportError, ModuleNotFoundError):
        observability = None

for mod, name in [
    (pipeline, "nexus_pipeline"),
    (processing, "nexus_processing"),
    (retrieval, "nexus_retrieval"),
    (guardrails, "nexus_guardrails"),
    (experience, "nexus_experience"),
    (security, "nexus_security"),
    (observability, "nexus_observability"),
]:
    if mod is not None:
        sys.modules.setdefault(name, mod)

# Keep the module namespace to the public API: the loop variables above would
# otherwise show up in `dir(nexus)` alongside the real exports.
del mod, name, sys

# These imports must run *after* the sys.modules aliases are registered above,
# because the modules they pull in resolve the layer packages by name.
from nexus.client import NexusClient  # noqa: E402
from nexus.config import load_config  # noqa: E402
from nexus.database import PGVECTOR_DDL_SCHEMA, get_pgvector_column_type  # noqa: E402
from nexus.models import (  # noqa: E402
    LayerStatus,
    NexusConfig,
    ProcessedChunk,
    ProcessedDocumentPayload,
    ProcessingStageTrace,
)
from nexus.platform import NexusPlatform  # noqa: E402

__all__ = [
    "PGVECTOR_DDL_SCHEMA",
    "LayerStatus",
    "NexusClient",
    "NexusConfig",
    "NexusPlatform",
    "ProcessedChunk",
    "ProcessedDocumentPayload",
    "ProcessingStageTrace",
    "__version__",
    "experience",
    "get_pgvector_column_type",
    "guardrails",
    "load_config",
    "observability",
    "pipeline",
    "processing",
    "retrieval",
    "security",
]

__version__ = "3.0.1"
