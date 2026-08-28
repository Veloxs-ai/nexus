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

import hashlib
from typing import Any

from .chunking import chunk_csv, chunk_json, chunk_smart_text, chunk_text
from .config import MetadataConfig, ProcessingConfig
from .enrichment import extract_metadata


class ProcessingEngine:
    """In-memory processing and enrichment engine.

    Provides high-performance, format-aware document chunking, metadata extraction,
    and text transformation without spawning subprocesses or requiring disk persistence.
    """

    def __init__(self, config: ProcessingConfig | None = None) -> None:
        self.config = config
        self._default_metadata_config = MetadataConfig(
            keyword_tags={
                "security": ["mfa", "access", "auth", "security", "encryption", "password"],
                "finance": ["invoice", "payment", "revenue", "budget", "billing", "usd"],
                "customer": ["customer", "client", "renewal", "account", "sla", "support"],
            }
        )

    def chunk_document(
        self,
        text: str,
        file_type: str | None = None,
        max_tokens: int = 1000,
        overlap_tokens: int = 200,
    ) -> list[str]:
        """Format-aware document chunker supporting CSV, JSON, Markdown, and plain text."""
        cleaned = text.strip()
        if not cleaned:
            return []

        fmt = (file_type or "").lower().removeprefix(".")
        if fmt == "csv":
            return chunk_csv(cleaned)
        if fmt in {"json", "jsonl"}:
            return chunk_json(cleaned)
        if fmt in {"md", "markdown", "txt", "text"}:
            return chunk_smart_text(cleaned, chunk_size=max_tokens, chunk_overlap=overlap_tokens)

        # Auto-detect using universal router
        return chunk_text(cleaned, max_tokens=max_tokens, overlap_tokens=overlap_tokens)

    def extract_metadata(self, text: str) -> dict[str, Any]:
        """Extract tags, named entities, dates, currency, and domain classification."""
        meta_cfg = (
            self.config.jobs[0].enrichment.metadata
            if (self.config and self.config.jobs)
            else self._default_metadata_config
        )
        return extract_metadata(text, meta_cfg)

    @staticmethod
    def compute_content_hash(text: str) -> str:
        """Computes MD5 content hash for deduplication and incremental sync."""
        return hashlib.md5(text.encode("utf-8")).hexdigest()
