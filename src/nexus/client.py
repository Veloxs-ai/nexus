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

"""``NexusClient``: the in-process Nexus client.

The ``process_*`` families live in mixin modules (``client_document`` with its format router
``client_routing``, ``client_image``, ``client_video``, ``client_audio``, ``client_databases``,
``client_tabular``, ``client_office``, ``client_email``, ``client_chat``, ``client_code``,
``client_pdf``, ``client_ingest``, ``client_store``); this module combines them into one class.
"""

from __future__ import annotations

import importlib
from pathlib import Path
from typing import Any

from nexus.chunk_limits import ChunkLimiter, resolve_limiter
from nexus.client_audio import AudioMixin
from nexus.client_chat import ChatMixin
from nexus.client_code import CodeMixin
from nexus.client_databases import DatabaseMixin
from nexus.client_document import DocumentMixin
from nexus.client_email import EmailMixin
from nexus.client_image import ImageMixin
from nexus.client_ingest import IngestMixin
from nexus.client_office import OfficeMixin
from nexus.client_pdf import PdfMixin
from nexus.client_store import StoreMixin
from nexus.client_tabular import TabularMixin
from nexus.client_video import VideoMixin
from nexus.models import NexusConfig, ProcessedDocumentPayload

try:
    from nexus.experience.config import AuthConfig, EngagementConfig
    from nexus.experience.config import TenantConfig as ExpTenantConfig
    from nexus.experience.gateway import InMemoryGuardrailsGateway
    from nexus.experience.models import AskRequest, AskResponse, Principal
    from nexus.experience.service import ExperienceService
    from nexus.guardrails.engine import GuardrailsEngine
    from nexus.processing.engine import ProcessingEngine
    from nexus.retrieval.engine import RetrievalEngine
except (ImportError, ModuleNotFoundError):
    from nexus_experience.config import AuthConfig, EngagementConfig
    from nexus_experience.config import TenantConfig as ExpTenantConfig
    from nexus_experience.gateway import InMemoryGuardrailsGateway
    from nexus_experience.models import AskRequest, AskResponse, Principal
    from nexus_experience.service import ExperienceService
    from nexus_guardrails.engine import GuardrailsEngine
    from nexus_processing.engine import ProcessingEngine
    from nexus_retrieval.engine import RetrievalEngine

# Names this module exposed before the process_* methods moved to their mixin modules.
_MOVED = {
    "client_audio": ("process_audio_binary",),
    "client_chat": ("process_chat_dialog",),
    "client_code": ("process_code", "process_openapi_spec"),
    "client_databases": (
        "chunk_mongo_collection",
        "chunk_mysql_table",
        "flatten_mongo_document",
        "serialize_bson_value",
    ),
    "client_document": (
        "ProcessedChunk",
        "ProcessingStageTrace",
        "_MASK_TOKEN",
        "_display",
        "_json_like",
        "bounded_output",
        "csv_row_text",
        "decode_text",
        "group_rows",
        "jsonable",
        "mask_rows",
        "parse_csv_table",
    ),
    "client_email": ("process_email_binary",),
    "client_image": ("process_image_binary",),
    "client_office": (
        "group_word_sections",
        "process_presentation_binary",
        "process_word_binary",
    ),
    "client_routing": ("_AUDIO_FORMATS", "_is_existing_file"),
    "client_tabular": (
        "process_spreadsheet_binary",
        "process_sqlite_binary",
        "process_sqlite_file",
        "spreadsheet_row_text",
    ),
    "client_video": ("process_video_binary",),
}
_MOVED_FROM = {name: module for module, names in _MOVED.items() for name in names}


def __getattr__(name: str) -> Any:
    module = _MOVED_FROM.get(name)
    if module is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    return getattr(importlib.import_module(f"nexus.{module}"), name)


def _semantic():
    try:
        from nexus.retrieval import semantic
    except (ImportError, ModuleNotFoundError):
        from nexus_retrieval import semantic
    return semantic


class NexusClient(
    IngestMixin,
    StoreMixin,
    PdfMixin,
    DocumentMixin,
    ImageMixin,
    VideoMixin,
    AudioMixin,
    DatabaseMixin,
    TabularMixin,
    OfficeMixin,
    EmailMixin,
    ChatMixin,
    CodeMixin,
):
    """Unified in-memory Python library client for the Nexus Enterprise Intelligence Framework.

    Provides high-performance, thread-safe, single-process document processing,
    format-aware chunking, configurable PII scrubbing, semantic embeddings
    (embed_texts / embed_query), cross-encoder re-ranking, execution telemetry
    traces, and grounded guardrail Q&A
    with zero disk I/O.
    """

    def __init__(
        self,
        config: NexusConfig | None = None,
        base_dir: Path | None = None,
        tenant_id: str = "default",
        in_memory_only: bool = True,
        processing_engine: ProcessingEngine | None = None,
        retrieval_engine: RetrievalEngine | None = None,
        guardrails_engine: GuardrailsEngine | None = None,
        experience_service: ExperienceService | None = None,
        chunk_max_tokens: int | None = None,
    ) -> None:
        """``chunk_max_tokens`` caps every processed chunk (default: ``NEXUS_CHUNK_MAX_TOKENS``
        or 450, never above the embedder's window); ``0`` turns the cap off."""
        self.config = config
        self._chunk_max_tokens = chunk_max_tokens
        self._chunk_limiter: ChunkLimiter | None = None
        self.base_dir = base_dir or Path.cwd()
        self.tenant_id = tenant_id
        self.in_memory_only = in_memory_only

        self.processing = processing_engine or ProcessingEngine()
        self.retrieval = retrieval_engine or RetrievalEngine(
            base_dir=self.base_dir,
            in_memory_only=self.in_memory_only,
        )
        self.guardrails = guardrails_engine or GuardrailsEngine(
            base_dir=self.base_dir,
            retrieval_engine=self.retrieval,
        )

        if experience_service is not None:
            self.experience = experience_service
        else:
            exp_config = EngagementConfig(
                tenant=ExpTenantConfig(id=self.tenant_id, display_name=f"Tenant {self.tenant_id}"),
                auth=AuthConfig(enabled=False),
            )
            gateway = InMemoryGuardrailsGateway(self.guardrails)
            self.experience = ExperienceService(exp_config, gateway)

    def index_document(
        self,
        payload: ProcessedDocumentPayload,
        collection: str = "general",
    ) -> None:
        """Index a processed document payload into the thread-safe in-memory
        vector store, lexical index, and knowledge graph.
        """
        for chunk in payload.chunks:
            self.retrieval.add_entry(
                doc_id=chunk.chunk_id,
                text=chunk.text,
                collection=collection,
                metadata=chunk.metadata,
            )

    def ask(
        self,
        query: str,
        channel: str = "assistant",
        user_id: str = "default_user",
        tenant_id: str | None = None,
        session_id: str | None = None,
    ) -> AskResponse:
        """Runs grounded RAG with safety guardrails in-memory without subprocess latency."""
        active_tenant = tenant_id or self.tenant_id
        principal = Principal(
            user_id=user_id,
            tenant_id=active_tenant,
            role="analyst",
            permissions=["ask", "session"],
        )
        request = AskRequest(
            query=query,
            channel=channel,
            session_id=session_id,
        )
        return self.experience.ask(principal, request)

    def search(self, query: str, limit: int = 10):
        """Performs hybrid retrieval over indexed documents."""
        return self.retrieval.search(query, limit=limit)

    @property
    def text_embedder(self):
        """Process-wide semantic text embedder (FastEmbed; hashing fallback)."""
        return _semantic().create_text_embedder()

    def embedding_info(self) -> dict[str, Any]:
        """Provider, model id, vector dimensions and token limits of the semantic embedder.

        Persist ``model`` next to stored vectors: vectors from different models
        live in different spaces and must never be compared. ``max_tokens`` is the
        largest chunk the model embeds whole (``window`` minus headroom for special
        tokens and a short name prefix); text past ``window`` is ignored by the model.
        """
        emb = self.text_embedder
        return {
            "provider": emb.provider,
            "model": emb.model_name,
            "dimensions": emb.dimensions,
            "max_tokens": getattr(emb, "max_tokens", None),
            "window": getattr(emb, "window", None),
        }

    def count_tokens(self, text: str) -> int:
        """Tokens ``text`` takes in the embedder's window (its own tokenizer when local)."""
        return self.text_embedder.count_tokens(text)

    @property
    def chunk_limiter(self) -> ChunkLimiter | None:
        """Token budget applied to every processed chunk (``None`` when turned off)."""
        if self._chunk_max_tokens == 0:
            return None
        if self._chunk_limiter is None:
            self._chunk_limiter = resolve_limiter(
                lambda: _semantic().create_text_embedder(), self._chunk_max_tokens
            )
        return self._chunk_limiter

    def fit_chunk_text(self, text: str) -> list[str]:
        """Split ``text`` into header-led pieces that fit the chunk token budget."""
        limiter = self.chunk_limiter
        return limiter.fit(text) if limiter else [text]

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """Batch-embed passages/chunks for storage (normalized dense vectors)."""
        return self.text_embedder.embed_batch(list(texts))

    def embed_query(self, text: str) -> list[float]:
        """Embed a search query (asymmetric query encoding for retrieval models)."""
        return self.text_embedder.embed_query(text)

    def rerank(self, query: str, passages: list[str]) -> list[float]:
        """Cross-encoder relevance scores in (0, 1), aligned with ``passages``."""
        return _semantic().create_reranker().score(query, list(passages))
