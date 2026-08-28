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

from setuptools import setup

setup(
    name="veloxs-nexus",
    version="3.0.1",
    package_dir={
        "nexus": "src/nexus",
        "nexus.pipeline": "enterprise-data-pipeline/src/nexus_pipeline",
        "nexus.processing": "data-processing-enrichment/src/nexus_processing",
        "nexus.retrieval": "embedding-retrieval-intelligence/src/nexus_retrieval",
        "nexus.guardrails": "orchestration-guardrails/src/nexus_guardrails",
        "nexus.experience": "experience-api-engagement/src/nexus_experience",
        "nexus.security": "security-governance/src/nexus_security",
        "nexus.observability": "observability-monitoring/src/nexus_observability",
    },
    packages=[
        "nexus",
        "nexus.pipeline",
        "nexus.processing",
        "nexus.retrieval",
        "nexus.guardrails",
        "nexus.experience",
        "nexus.security",
        "nexus.observability",
    ],
    include_package_data=True,
)
