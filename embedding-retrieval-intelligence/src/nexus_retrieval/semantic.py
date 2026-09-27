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

"""Semantic text embeddings and cross-encoder re-ranking.

Backed by FastEmbed (ONNX Runtime, CPU-friendly, no torch dependency). Models are
downloaded once and cached; loading is lazy and process-wide so every NexusClient
shares one model instance.

Configuration (environment):
    NEXUS_EMBEDDING_PROVIDER   fastembed | openai                   (default: fastembed)
    NEXUS_EMBEDDING_MODEL      FastEmbed model id              (default: BAAI/bge-small-en-v1.5)
    NEXUS_RERANK_MODEL         FastEmbed cross-encoder id      (default: Xenova/ms-marco-MiniLM-L-6-v2)
    NEXUS_MODEL_CACHE_DIR      Model cache directory           (default: FastEmbed default)

``openai`` calls the OpenAI embeddings API (OPENAI_API_KEY; model via
NEXUS_OPENAI_EMBEDDING_MODEL, default text-embedding-3-small) with
NEXUS_EMBEDDING_DIMENSIONS (default 384) so it can replace the local model without a
schema change — ~100x faster ingestion than CPU inference, at API cost. Switching
provider changes the vector space: re-index stored chunks afterwards.

"""

from __future__ import annotations

import logging
import math
import os
import threading
from typing import Any, Protocol


logger = logging.getLogger(__name__)

DEFAULT_EMBEDDING_MODEL = "BAAI/bge-small-en-v1.5"
DEFAULT_RERANK_MODEL = "Xenova/ms-marco-MiniLM-L-6-v2"

_lock = threading.Lock()
_embedders: dict[str, Any] = {}
_rerankers: dict[str, Any] = {}


class TextEmbedder(Protocol):
    provider: str
    model_name: str
    dimensions: int

    def embed(self, text: str) -> list[float]: ...

    def embed_query(self, text: str) -> list[float]: ...

    def embed_batch(self, texts: list[str]) -> list[list[float]]: ...


class SemanticEmbedder:
    """Dense semantic embedder (FastEmbed / ONNX).

    Passages and queries are embedded asymmetrically (``passage_embed`` /
    ``query_embed``) which is what BGE/E5-style retrieval models are trained for.
    Vectors are L2-normalised, so cosine distance == 1 - dot product.
    """

    provider = "fastembed"

    def __init__(self, model_name: str | None = None, batch_size: int = 64) -> None:
        from fastembed import TextEmbedding

        self.model_name = model_name or os.environ.get("NEXUS_EMBEDDING_MODEL") or DEFAULT_EMBEDDING_MODEL
        self.batch_size = batch_size
        kwargs: dict[str, Any] = {"model_name": self.model_name}
        cache_dir = os.environ.get("NEXUS_MODEL_CACHE_DIR")
        if cache_dir:
            kwargs["cache_dir"] = cache_dir
        self._model = TextEmbedding(**kwargs)
        self._infer_lock = threading.Lock()
        self.dimensions = len(self.embed_query("dimension probe"))

    @staticmethod
    def _to_list(vec: Any) -> list[float]:
        return [float(x) for x in vec]

    def embed(self, text: str) -> list[float]:
        return self.embed_batch([text])[0]

    def embed_query(self, text: str) -> list[float]:
        with self._infer_lock:
            return self._to_list(next(iter(self._model.query_embed([text or " "]))))

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        clean = [t if (t and t.strip()) else " " for t in texts]
        with self._infer_lock:
            return [self._to_list(v) for v in self._model.passage_embed(clean, batch_size=self.batch_size)]


class OpenAIEmbedder:
    """OpenAI embeddings API (text-embedding-3-*), truncated to the configured dimensions."""

    provider = "openai"
    batch_size = 256

    def __init__(self, model_name: str | None = None, dimensions: int | None = None, api_key: str | None = None) -> None:
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY") or ""
        if not self.api_key:
            raise RuntimeError("OPENAI_API_KEY is not set")
        self.base_model = model_name or os.environ.get("NEXUS_OPENAI_EMBEDDING_MODEL") or "text-embedding-3-small"
        self.dimensions = int(dimensions or os.environ.get("NEXUS_EMBEDDING_DIMENSIONS") or 384)
        self.model_name = f"openai/{self.base_model}@{self.dimensions}"

    def _request(self, texts: list[str]) -> list[list[float]]:
        import json
        import urllib.request

        body = json.dumps({"model": self.base_model, "input": texts, "dimensions": self.dimensions}).encode("utf-8")
        req = urllib.request.Request(
            "https://api.openai.com/v1/embeddings",
            data=body,
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {self.api_key}"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read().decode("utf-8"))["data"]
        return [item["embedding"] for item in sorted(data, key=lambda d: d["index"])]

    def embed(self, text: str) -> list[float]:
        return self.embed_batch([text])[0]

    def embed_query(self, text: str) -> list[float]:
        return self.embed(text)

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        clean = [t if (t and t.strip()) else " " for t in texts]
        out: list[list[float]] = []
        for start in range(0, len(clean), self.batch_size):
            out.extend(self._request([t[:24000] for t in clean[start : start + self.batch_size]]))
        return out


def create_text_embedder(provider: str | None = None, model_name: str | None = None) -> TextEmbedder:
    """Process-wide cached semantic text embedder (fastembed | openai)."""
    choice = (provider or os.environ.get("NEXUS_EMBEDDING_PROVIDER") or "fastembed").strip().lower()
    if choice == "auto":  # historical default: the local model
        choice = "fastembed"
    if choice == "openai":
        key = f"openai:{model_name or os.environ.get('NEXUS_OPENAI_EMBEDDING_MODEL') or ''}"
        factory = lambda: OpenAIEmbedder(model_name=model_name)  # noqa: E731
    elif choice == "fastembed":
        model = model_name or os.environ.get("NEXUS_EMBEDDING_MODEL") or DEFAULT_EMBEDDING_MODEL
        key = f"fastembed:{model}"
        factory = lambda: SemanticEmbedder(model_name=model)  # noqa: E731
    else:
        raise ValueError(f"unsupported embedding provider '{choice}' (use 'fastembed' or 'openai')")
    with _lock:
        if key not in _embedders:
            _embedders[key] = factory()
        return _embedders[key]


def embedder_for(config) -> TextEmbedder:
    """Embedder described by a retrieval EmbeddingConfig."""
    return create_text_embedder(provider=config.provider, model_name=config.model)


class CrossEncoderReranker:
    """Cross-encoder re-ranker: scores (query, passage) pairs jointly.

    Far more precise than bi-encoder similarity, so it is applied to a small
    candidate pool (typically 30-100) produced by hybrid first-stage retrieval.
    """

    provider = "fastembed"

    def __init__(self, model_name: str | None = None) -> None:
        from fastembed.rerank.cross_encoder import TextCrossEncoder

        self.model_name = model_name or os.environ.get("NEXUS_RERANK_MODEL") or DEFAULT_RERANK_MODEL
        kwargs: dict[str, Any] = {"model_name": self.model_name}
        cache_dir = os.environ.get("NEXUS_MODEL_CACHE_DIR")
        if cache_dir:
            kwargs["cache_dir"] = cache_dir
        self._model = TextCrossEncoder(**kwargs)
        self._infer_lock = threading.Lock()

    def score(self, query: str, passages: list[str]) -> list[float]:
        if not passages:
            return []
        with self._infer_lock:
            raw = [float(s) for s in self._model.rerank(query, passages, batch_size=32)]
        # Logits -> (0, 1) so callers can apply absolute relevance thresholds.
        return [1.0 / (1.0 + math.exp(-s)) for s in raw]


def create_reranker(model_name: str | None = None) -> CrossEncoderReranker:
    """Process-wide cached cross-encoder re-ranker."""
    model = model_name or os.environ.get("NEXUS_RERANK_MODEL") or DEFAULT_RERANK_MODEL
    with _lock:
        if model not in _rerankers:
            _rerankers[model] = CrossEncoderReranker(model_name=model)
        return _rerankers[model]
