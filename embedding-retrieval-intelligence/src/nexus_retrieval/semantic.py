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
shares one embedder.

Query-time inference never waits behind ingestion: a ``SemanticEmbedder`` keeps a
second, query-only model instance (``embed_query``) next to the passage instance
(``embed_batch``), and ``embed_batch`` takes its lock once per mini-batch, so
concurrent ingests interleave instead of queueing behind one another's whole batch.
The cross-encoder re-ranker likewise locks per mini-batch of pairs.

Configuration (environment):
    NEXUS_EMBEDDING_PROVIDER   fastembed | openai                   (default: fastembed)
    NEXUS_EMBEDDING_MODEL      FastEmbed model id              (default: BAAI/bge-small-en-v1.5)
    NEXUS_RERANK_MODEL         FastEmbed cross-encoder id      (default: Xenova/ms-marco-MiniLM-L-6-v2)
    NEXUS_MODEL_CACHE_DIR      Model cache directory           (default: FastEmbed default)
    NEXUS_QUERY_MODEL          separate | shared: query-only model instance (default: separate)
    NEXUS_ONNX_THREADS         ONNX intra-op threads of the passage model and re-ranker
                               (default: half the CPUs)
    NEXUS_ONNX_QUERY_THREADS   ONNX intra-op threads of the query-only model (default: 2)
    NEXUS_TOKENIZER_THREADS    threads of the batched token counter (Rust ``tokenizers``
                               pool; default: all CPUs). Read before the first batched count;
                               RAYON_NUM_THREADS, when set, wins. Lower it on hosts that run
                               several workers.

The ONNX defaults keep the query session from competing with passage ingest for every
core: queries stay fast while a pipeline embeds.

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
_key_locks: dict[str, threading.Lock] = {}


class TextEmbedder(Protocol):
    provider: str
    model_name: str
    dimensions: int
    max_tokens: int

    def embed(self, text: str) -> list[float]: ...

    def embed_query(self, text: str) -> list[float]: ...

    def embed_batch(self, texts: list[str]) -> list[list[float]]: ...

    def count_tokens(self, text: str) -> int: ...


# Share of the model's input window a stored chunk may use. The rest is headroom for the
# special tokens and for a short prefix callers add at embedding time (a document name):
# 512-token models -> 450 tokens per chunk.
CHUNK_WINDOW_SHARE = 0.88


def max_chunk_tokens(window: int) -> int:
    """Largest chunk (in tokens) a model with a ``window``-token input can embed whole."""
    return max(16, int(window * CHUNK_WINDOW_SHARE))


def estimate_tokens(text: str) -> int:
    """Upper-bound token estimate for models without a local tokenizer (~3 chars/token)."""
    return max(1, -(-len(text or "") // 3))


def _whitespace_additive(counter: Any) -> bool:
    """True when ``counter`` (a ``tokenizers.Tokenizer``) counts a text as the sum of its
    whitespace-separated words: BERT normalisation and pre-tokenisation (bge, MiniLM, e5)."""
    if counter is None:
        return False
    normalizer = type(getattr(counter, "normalizer", None)).__name__
    pre = type(getattr(counter, "pre_tokenizer", None)).__name__
    return pre == "BertPreTokenizer" and normalizer in ("BertNormalizer", "NoneType")


def _env_threads(name: str) -> int | None:
    raw = (os.environ.get(name) or "").strip()
    return int(raw) if raw.isdigit() and int(raw) > 0 else None


def _half_cpus() -> int:
    return max(1, (os.cpu_count() or 2) // 2)


def _onnx_threads(query: bool = False) -> int:
    """Intra-op threads for one ONNX session: passage model / re-ranker, or the query model."""
    if query:
        return _env_threads("NEXUS_ONNX_QUERY_THREADS") or min(2, _onnx_threads())
    return _env_threads("NEXUS_ONNX_THREADS") or _half_cpus()


def _budget_tokenizer_threads() -> None:
    """Size the Rust tokenizer pool (Rayon reads RAYON_NUM_THREADS once, at first use)."""
    threads = _env_threads("NEXUS_TOKENIZER_THREADS")
    if threads and not os.environ.get("RAYON_NUM_THREADS"):
        os.environ["RAYON_NUM_THREADS"] = str(threads)


def _fastembed_kwargs(model_name: str, query: bool = False) -> dict[str, Any]:
    kwargs: dict[str, Any] = {"model_name": model_name}
    cache_dir = os.environ.get("NEXUS_MODEL_CACHE_DIR")
    if cache_dir:
        kwargs["cache_dir"] = cache_dir
    kwargs["threads"] = _onnx_threads(query)
    return kwargs


class SemanticEmbedder:
    """Dense semantic embedder (FastEmbed / ONNX).

    Passages and queries are embedded asymmetrically (``passage_embed`` /
    ``query_embed``) which is what BGE/E5-style retrieval models are trained for.
    Vectors are L2-normalised, so cosine distance == 1 - dot product.

    Two model instances serve the two paths: ``embed_query`` runs on a query-only
    instance with its own lock, so a user's question is answered in milliseconds while
    a pipeline embeds thousands of passages. ``embed_batch`` sorts passages by length
    (less padding) and holds the passage lock for one mini-batch at a time. Set
    ``NEXUS_QUERY_MODEL=shared`` to use one instance for both (half the memory; queries
    then wait for at most one passage mini-batch).
    """

    provider = "fastembed"

    def __init__(
        self,
        model_name: str | None = None,
        batch_size: int = 64,
        separate_query_model: bool | None = None,
    ) -> None:
        _budget_tokenizer_threads()
        from fastembed import TextEmbedding

        self.model_name = (
            model_name or os.environ.get("NEXUS_EMBEDDING_MODEL") or DEFAULT_EMBEDDING_MODEL
        )
        self.batch_size = max(1, batch_size)
        if separate_query_model is None:
            choice = (os.environ.get("NEXUS_QUERY_MODEL") or "separate").strip().lower()
            separate_query_model = choice != "shared"
        self._model = TextEmbedding(**_fastembed_kwargs(self.model_name))
        self._passage_lock = threading.Lock()
        if separate_query_model:
            self._query_model = TextEmbedding(**_fastembed_kwargs(self.model_name, query=True))
            self._query_lock = threading.Lock()
        else:
            self._query_model = self._model
            self._query_lock = self._passage_lock
        self.separate_query_model = bool(separate_query_model)
        self._counter = self._token_counter()
        # Token counts add up across whitespace (WordPiece after a whitespace/punctuation
        # pre-tokenizer): text splitters may then trust the sum of the parts' counts.
        self.additive_counts = _whitespace_additive(self._counter)
        self.window = self._window()
        self.max_tokens = max_chunk_tokens(self.window)
        self.dimensions = len(self.embed_query("dimension probe"))

    def _tokenizer(self) -> Any:
        return getattr(getattr(self._model, "model", None), "tokenizer", None)

    def _window(self) -> int:
        tok = self._tokenizer()
        truncation = getattr(tok, "truncation", None) or {}
        return int(truncation.get("max_length") or 512)

    def _token_counter(self) -> Any:
        """A non-truncating copy of the model's tokenizer (the model's own one truncates)."""
        tok = self._tokenizer()
        if tok is None:
            return None
        try:
            from tokenizers import Tokenizer

            counter = Tokenizer.from_str(tok.to_str())
            counter.no_truncation()
            counter.no_padding()
            return counter
        except Exception:  # pragma: no cover - tokenizer layout of another backend
            return None

    def count_tokens(self, text: str) -> int:
        """Tokens ``text`` costs in this model's window (without the special tokens)."""
        if self._counter is None:
            return estimate_tokens(text)
        return len(self._counter.encode(text or "", add_special_tokens=False).ids)

    def count_tokens_batch(self, texts: list[str]) -> list[int]:
        if self._counter is None:
            return [estimate_tokens(t) for t in texts]
        encoded = self._counter.encode_batch(list(texts), add_special_tokens=False)
        return [len(e.ids) for e in encoded]

    @staticmethod
    def _to_list(vec: Any) -> list[float]:
        tolist = getattr(vec, "tolist", None)  # numpy: one C call, same float values
        return tolist() if tolist is not None else [float(x) for x in vec]

    def embed(self, text: str) -> list[float]:
        return self.embed_batch([text])[0]

    def embed_query(self, text: str) -> list[float]:
        with self._query_lock:
            return self._to_list(next(iter(self._query_model.query_embed([text or " "]))))

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        clean = [t if (t and t.strip()) else " " for t in texts]
        # Length-sorted mini-batches pad less; results are put back in input order.
        order = sorted(range(len(clean)), key=lambda i: len(clean[i]))
        out: list[list[float] | None] = [None] * len(clean)
        for start in range(0, len(order), self.batch_size):
            idx = order[start : start + self.batch_size]
            batch = [clean[i] for i in idx]
            with self._passage_lock:  # one mini-batch at a time: other callers interleave
                vecs = list(self._model.passage_embed(batch, batch_size=len(batch)))
            for i, vec in zip(idx, vecs, strict=True):
                out[i] = self._to_list(vec)
        return out  # type: ignore[return-value]


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
        self.window = 8191
        self.max_tokens = max_chunk_tokens(self.window)

    def count_tokens(self, text: str) -> int:
        return estimate_tokens(text)

    def count_tokens_batch(self, texts: list[str]) -> list[int]:
        return [estimate_tokens(t) for t in texts]

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
    return _cached(_embedders, key, factory)


def embedder_for(config) -> TextEmbedder:
    """Embedder described by a retrieval EmbeddingConfig."""
    return create_text_embedder(provider=config.provider, model_name=config.model)


class CrossEncoderReranker:
    """Cross-encoder re-ranker: scores (query, passage) pairs jointly.

    Far more precise than bi-encoder similarity, so it is applied to a small
    candidate pool (typically 30-100) produced by hybrid first-stage retrieval.
    The model lock is held per mini-batch of pairs, so concurrent questions
    interleave instead of each waiting for every earlier pool to finish.
    """

    provider = "fastembed"
    batch_size = 32

    def __init__(self, model_name: str | None = None) -> None:
        _budget_tokenizer_threads()
        from fastembed.rerank.cross_encoder import TextCrossEncoder

        self.model_name = model_name or os.environ.get("NEXUS_RERANK_MODEL") or DEFAULT_RERANK_MODEL
        self._model = TextCrossEncoder(**_fastembed_kwargs(self.model_name))
        self._infer_lock = threading.Lock()

    def score(self, query: str, passages: list[str]) -> list[float]:
        if not passages:
            return []
        raw: list[float] = []
        for start in range(0, len(passages), self.batch_size):
            batch = passages[start : start + self.batch_size]
            with self._infer_lock:
                scores = self._model.rerank(query, batch, batch_size=len(batch))
                raw.extend(float(s) for s in scores)
        # Logits -> (0, 1) so callers can apply absolute relevance thresholds.
        return [_sigmoid(s) for s in raw]


def _sigmoid(x: float) -> float:
    """Logistic function that cannot overflow for large negative or positive logits."""
    if x >= 0:
        return 1.0 / (1.0 + math.exp(-x))
    z = math.exp(x)
    return z / (1.0 + z)


def _cached(cache: dict[str, Any], key: str, factory: Any) -> Any:
    """Process-wide instance per ``key``. A per-key lock: loading (or downloading) one model
    does not block callers that want another one."""
    with _lock:
        if key in cache:
            return cache[key]
        key_lock = _key_locks.setdefault(f"{id(cache)}:{key}", threading.Lock())
    with key_lock:
        with _lock:
            if key in cache:
                return cache[key]
        instance = factory()
        with _lock:
            cache[key] = instance
        return instance


def create_reranker(model_name: str | None = None) -> CrossEncoderReranker:
    """Process-wide cached cross-encoder re-ranker."""
    model = model_name or os.environ.get("NEXUS_RERANK_MODEL") or DEFAULT_RERANK_MODEL
    return _cached(_rerankers, model, lambda: CrossEncoderReranker(model_name=model))
