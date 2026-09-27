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

"""Embedding and retrieval intelligence package."""

from .embeddings import cosine_similarity
from .engine import RetrievalEngine
from .semantic import create_reranker, create_text_embedder, embedder_for

__all__ = [
    "RetrievalEngine",
    "__version__",
    "cosine_similarity",
    "create_reranker",
    "create_text_embedder",
    "embedder_for",
]

__version__ = "0.1.0"
