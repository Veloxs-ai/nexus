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

"""Keep every processed chunk inside the embedder's token window.

``ChunkLimiter`` is applied to the output of every ``NexusClient.process_*`` method.
A chunk over the budget becomes consecutive parts (``metadata.part`` / ``parts`` /
``parent_chunk_id``) with the chunk's context header repeated on each part. Row
payloads (``record``, ``records``, ``data``) stay on the first part only, so a row
is never counted twice.
"""

from __future__ import annotations

import functools
import os
import re
from collections.abc import Callable
from typing import Any

from nexus.models import ProcessedChunk, ProcessedDocumentPayload

try:
    from nexus.processing.quality import assess_text
    from nexus.processing.token_budget import DEFAULT_MAX_TOKENS, estimate_tokens, fit_text
    from nexus.processing.token_budget import _additive as _additive_counter
except (ImportError, ModuleNotFoundError):
    from nexus_processing.quality import assess_text
    from nexus_processing.token_budget import DEFAULT_MAX_TOKENS, estimate_tokens, fit_text
    from nexus_processing.token_budget import _additive as _additive_counter

__all__ = ["ChunkLimiter", "bounded_output"]

# Metadata that describes whole rows: kept on the first part of a split chunk only.
ROW_PAYLOAD_KEYS = ("record", "records", "data")


class ChunkLimiter:
    """Splits chunks over ``max_tokens`` (counted with ``count``) into header-led parts."""

    def __init__(
        self,
        max_tokens: int,
        count: Callable[[str], int] | None = None,
        count_many: Callable[[list[str]], list[int]] | None = None,
    ) -> None:
        self.max_tokens = max(16, int(max_tokens))
        self.count = count or estimate_tokens
        self._count_many = count_many
        # The count of joined texts is at most the sum of their counts (whitespace-split
        # tokenizers and the estimate): a packed group's summed row costs bound it.
        self.additive = _additive_counter(self.count)

    def group_bound(self, costs: list[int], first: int, last: int, header_tokens: int) -> int:
        """Token bound of a ``group_rows`` chunk: header plus each row's cost and separator
        (trusted by ``bound`` only when the counter is additive)."""
        return header_tokens + sum(costs[first : last + 1]) + (last - first + 1)

    def count_many(self, texts: list[str]) -> list[int]:
        """Token counts of many texts (batched through the tokenizer when it can)."""
        if self._count_many is not None:
            return self._count_many(texts)
        return [self.count(t) for t in texts]

    def fit(self, text: str, known: int | None = None) -> list[str]:
        """``text`` as pieces within the budget; ``known`` is its token count when counted."""
        return fit_text(text, self.max_tokens, self.count, known=known, count_many=self._count_many)

    def _known_to_fit(self, chunk: ProcessedChunk) -> bool:
        known = getattr(chunk, "_token_bound", None)
        return self.additive and known is not None and known <= self.max_tokens

    def bound(self, chunks: list[ProcessedChunk]) -> list[ProcessedChunk]:
        # A text never has more tokens than characters: count only the longer ones, batched.
        # A chunk whose producer bounded it already (packed rows, additive counter) is skipped.
        long_idx = [
            i
            for i, c in enumerate(chunks)
            if len(c.text) > self.max_tokens and not self._known_to_fit(c)
        ]
        long_counts = self.count_many([chunks[i].text for i in long_idx])
        counts = dict(zip(long_idx, long_counts, strict=True))
        out: list[ProcessedChunk] = []
        split = False
        for idx, chunk in enumerate(chunks):
            fits = counts.get(idx, 0) <= self.max_tokens
            pieces = [chunk.text] if fits else self.fit(chunk.text, counts[idx])
            if len(pieces) == 1:
                out.append(chunk)
                continue
            split = True
            for number, piece in enumerate(pieces, start=1):
                meta = dict(chunk.metadata)
                if number > 1:
                    for key in ROW_PAYLOAD_KEYS:
                        meta.pop(key, None)
                meta.update(
                    {"part": number, "parts": len(pieces), "parent_chunk_id": chunk.chunk_id}
                )
                out.append(
                    ProcessedChunk(
                        chunk_id=chunk.chunk_id if number == 1 else f"{chunk.chunk_id}#p{number}",
                        document_id=chunk.document_id,
                        chunk_index=chunk.chunk_index,
                        text=piece,
                        metadata=meta,
                    )
                )
        if split:
            out = [c.model_copy(update={"chunk_index": i}) for i, c in enumerate(out)]
        return out


def resolve_limiter(embedder_factory: Callable[[], Any], max_tokens: int | None) -> ChunkLimiter:
    """Budget = the smaller of the configured chunk size and the embedder's window.

    The token counter is the embedder's own tokenizer when the embedder can be loaded,
    else a conservative estimate.
    """
    configured = max_tokens
    if configured is None:
        raw = (os.environ.get("NEXUS_CHUNK_MAX_TOKENS") or "").strip()
        configured = int(raw) if raw.isdigit() and int(raw) > 0 else DEFAULT_MAX_TOKENS
    try:
        embedder = embedder_factory()
        window_cap = int(getattr(embedder, "max_tokens", configured) or configured)
        counter = getattr(embedder, "count_tokens", None)
        counter_many = getattr(embedder, "count_tokens_batch", None)
    except Exception:  # embedder unavailable (no model download, no API key): estimate
        window_cap, counter, counter_many = configured, None, None
    return ChunkLimiter(min(configured, window_cap), counter, counter_many)


_INTO_CHUNKS = re.compile(r"into \d+ chunks")


def bounded_output(
    method: Callable[..., ProcessedDocumentPayload],
) -> Callable[..., ProcessedDocumentPayload]:
    """Decorator for ``NexusClient.process_*``: bound the returned chunks to the token window."""

    @functools.wraps(method)
    def wrapper(self: Any, *args: Any, **kwargs: Any) -> ProcessedDocumentPayload:
        payload = method(self, *args, **kwargs)
        limiter = self.chunk_limiter
        if limiter is not None:
            bounded = limiter.bound(payload.chunks)
            if len(bounded) != len(payload.chunks):
                summary = _INTO_CHUNKS.sub(f"into {len(bounded)} chunks", payload.summary, count=1)
                payload = payload.model_copy(update={"chunks": bounded, "summary": summary})
        if not payload.quality:
            payload.quality = assess_text(c.text for c in payload.chunks)
        return payload

    return wrapper
