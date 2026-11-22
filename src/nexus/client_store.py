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

"""``NexusClient`` storage helpers: storage-ready chunks, title-aware embeddings, CDC change
processing, JSON record chunks and multi-query re-ranking.

- ``prepare_chunks`` / ``document_digest``: chunks bounded to the embedder's window,
  packed row groups, and the document summary text;
- ``embed_passages``: embeddings with a document title prefixed inside the window;
- ``process_change_events``: CDC events applied to record state, masked by column with
  stable column kinds, rendered as chunk text;
- ``rerank_multi`` / ``reranker_info``: multi-query re-ranking and its cost profile.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from nexus.table_records import jsonable, mask_rows

try:
    from nexus.processing import cdc as _cdc
    from nexus.processing.chunk_store import document_digest, prepare_chunks, title_passages
    from nexus.processing.csv_table import group_rows
    from nexus.processing.csv_table import row_text as _row_text
    from nexus.processing.json_table import json_table
    from nexus.retrieval.ranking import rerank_multi
except (ImportError, ModuleNotFoundError):  # dev layout: layers installed separately
    import nexus_processing.cdc as _cdc
    from nexus_processing.chunk_store import document_digest, prepare_chunks, title_passages
    from nexus_processing.csv_table import group_rows
    from nexus_processing.csv_table import row_text as _row_text
    from nexus_processing.json_table import json_table
    from nexus_retrieval.ranking import rerank_multi

__all__ = ["RERANK_PROFILES", "ChangeChunk", "StoreMixin"]

# Re-ranker model -> (characters of each candidate scored, pool, pool for broad questions):
# cross-encoder cost is pairs x tokens, so larger models get fewer pairs and long-window
# models see more of each candidate. Starting points measured on CPU (MiniLM-L-6: 48 x
# 700 characters ~ 1 s); unknown models use the MiniLM-L-6 profile.
RERANK_PROFILES: dict[str, tuple[int, int, int]] = {
    "xenova/ms-marco-minilm-l-6-v2": (700, 32, 48),
    "xenova/ms-marco-minilm-l-12-v2": (700, 24, 32),
    "baai/bge-reranker-base": (600, 16, 24),
    "jinaai/jina-reranker-v1-tiny-en": (1600, 24, 32),
    "jinaai/jina-reranker-v1-turbo-en": (1600, 24, 32),
    "jinaai/jina-reranker-v2-base-multilingual": (1200, 16, 24),
}
_DEFAULT_PROFILE = RERANK_PROFILES["xenova/ms-marco-minilm-l-6-v2"]


@dataclass
class ChangeChunk:
    """One record's chunk after a change event (or a delete when ``delete``)."""

    key: str
    delete: bool
    text: str = ""
    record: dict[str, Any] | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


class StoreMixin:
    """Mixed into ``NexusClient`` (uses its guardrails, chunk limiter, embedder and re-ranker)."""

    def _json_record_chunks(
        self, text: str, apply_guardrails: bool
    ) -> list[tuple[str, list[dict[str, Any]], int, int, int | None]]:
        """JSON with a record array -> row-group chunks with their column-masked records.

        Returns ``(text, records, first row, last row, token bound)`` per chunk (1-based
        rows; the first chunk holds the document's other fields when there are any, with
        no records; the bound is the summed row costs or ``None``), or ``[]`` when the
        JSON has no record array (``chunk_json`` then applies).
        """
        table = json_table(text)
        if table is None:
            return []
        rows = [jsonable(r) for r in table.rows]
        classify = getattr(self.guardrails, "classify_columns", None)
        kinds = classify(rows) if (apply_guardrails and classify) else None
        masked, _ = mask_rows(self.guardrails, rows, apply_guardrails, kinds)
        texts = [_row_text(n, row) for n, row in enumerate(masked, start=1)]
        header = f"Columns: {', '.join(table.columns)}"
        limiter = self.chunk_limiter
        costs = limiter.count_many(texts) if limiter else None
        header_tokens = limiter.count(header) + 1 if limiter else 0
        groups = group_rows(
            texts,
            header=header,
            max_tokens=limiter.max_tokens if limiter else None,
            token_costs=costs,
            header_tokens=header_tokens,
        )
        out: list[tuple[str, list[dict[str, Any]], int, int, int | None]] = []
        if table.context:
            context = "\n".join([f"Records: {table.path} ({len(rows)} rows)", *table.context])
            if apply_guardrails:
                context = self.guardrails.mask_pii(context)
            out.append((context, [], 0, 0, None))
        out.extend(
            (
                chunk,
                masked[first : last + 1],
                first + 1,
                last + 1,
                limiter.group_bound(costs, first, last, header_tokens) if limiter else None,
            )
            for chunk, first, last in groups
        )
        return out

    # ---- storage-ready chunks and embeddings -------------------------------------------
    def prepare_chunks(
        self,
        chunks: list[dict[str, Any]],
        title: str = "",
        drop_keys: tuple[str, ...] = ("data",),
        **options: Any,
    ) -> list[dict[str, Any]]:
        """``nexus.processing.chunk_store.prepare_chunks`` with this client's token budget and
        tokenizer (chunks bounded to the embedder's window, records kept on first parts)."""
        limiter = self.chunk_limiter
        if limiter is not None:
            options.setdefault("count_many", limiter.count_many)
        return prepare_chunks(
            chunks,
            max_tokens=limiter.max_tokens if limiter else None,
            count_tokens=limiter.count if limiter else None,
            title=title,
            drop_keys=drop_keys,
            **options,
        )

    @staticmethod
    def document_digest(
        name: str, file_type: str, chunks: list[dict[str, Any]], **options: Any
    ) -> str:
        """Summary text of a document (see ``chunk_store.document_digest``)."""
        return document_digest(name, file_type, chunks, **options)

    def embed_passages(
        self, texts: list[str], titles: list[str] | str | None = None
    ) -> list[list[float]]:
        """Embed passages for storage, each prefixed with its document title.

        The input is ``f"{title}\\n{text}"``; when that would not fit the model's window the
        title is shortened (word by word, then dropped), never the passage
        (``chunk_store.title_passages``). With no title this is ``embed_texts``.
        """
        embedder = self.text_embedder
        inputs = title_passages(
            list(texts),
            titles,
            count_tokens=getattr(embedder, "count_tokens", None),
            window=int(getattr(embedder, "window", 0) or 0) or None,
        )
        return self.embed_texts(inputs)

    # ---- re-ranking ----------------------------------------------------------------------
    def reranker_info(self) -> dict[str, Any]:
        """The configured re-ranker and its cost profile: ``{"model", "max_chars", "pool",
        "broad_pool"}`` (characters of each candidate worth scoring, pool sizes)."""
        import os

        model = os.environ.get("NEXUS_RERANK_MODEL") or "Xenova/ms-marco-MiniLM-L-6-v2"
        chars, pool, broad = RERANK_PROFILES.get(model.lower(), _DEFAULT_PROFILE)
        return {"model": model, "max_chars": chars, "pool": pool, "broad_pool": broad}

    def rerank_multi(
        self,
        queries: list[str],
        passages: list[str],
        found_by: list[set[int]] | None = None,
    ) -> list[float]:
        """Re-rank ``passages`` for a question and its sub-queries (best score per passage;
        see ``nexus.retrieval.ranking.rerank_multi``)."""
        return rerank_multi(queries, passages, self.rerank, found_by)

    # ---- change data capture ----------------------------------------------------------------
    def process_change_events(
        self,
        events: list[Any],
        *,
        state: dict[str, dict[str, Any]] | None = None,
        column_kinds: dict[str, str] | None = None,
        enable_guardrails: bool = True,
        positions: dict[str, str] | None = None,
    ) -> tuple[list[ChangeChunk], dict[str, str]]:
        """Apply change events to record state and render each record's chunk.

        ``events``: ``ChangeEvent`` objects (or raw events, normalised here). ``state``:
        the stored records by key (needed for partial updates; it is updated in place).
        Records are masked by column with stable kinds (``column_kinds`` from earlier
        batches are kept; new columns are classified from this batch), and the chunk text
        is rendered from the masked record, so id and amount columns keep their values and
        PII columns are masked in both. Returns ``(chunks, column kinds)``; keep the kinds
        for the next batch.

        One chunk per record key: the batch's events for a key are applied in order and
        only its final state is rendered (or one delete). An event that is not newer than
        the last applied one for its key (same or lower log position: an at-least-once
        redelivery) is skipped, so a stale event never overwrites newer state.
        ``positions`` (key -> last applied position, updated in place) carries that check
        across batches. Kafka tombstones (``None`` events) are ignored.
        """
        events = [e for e in events if e is not None]
        if events and not all(hasattr(e, "operation") for e in events):
            events = _cdc.normalize_change_events(events)
        state = state if state is not None else {}
        newest: dict[str, Any] = {}
        final: dict[str, tuple[Any, dict[str, Any] | None]] = {}
        for n, event in enumerate(e for e in events if e.is_data_change):
            if not event.key:  # no key: nothing to merge with, every event stands alone
                final[f"\0{n}"] = (event, _cdc.apply_change(None, event))
                continue
            last = newest.get(event.key)
            if last is None and positions:
                last = positions.get(event.key) or None
            if not _cdc.is_newer(event, last):
                continue
            newest[event.key] = event
            record = _cdc.apply_change(state.get(event.key), event)
            if record is None:
                state.pop(event.key, None)
            else:
                state[event.key] = record
            final.pop(event.key, None)  # keep the order of each key's last change
            final[event.key] = (event, record)
            if positions is not None and event.source_position:
                positions[event.key] = event.source_position
        merged = list(final.values())
        guard = self.guardrails
        kinds = dict(column_kinds or {})
        if enable_guardrails and hasattr(guard, "merge_column_kinds"):
            kinds = guard.merge_column_kinds(kinds, [r for _, r in merged if r is not None])
        out: list[ChangeChunk] = []
        for event, record in merged:
            meta = {
                "source": "cdc_stream",
                "table": ".".join(p for p in (event.database, event.table) if p) or "events",
                "operation": event.operation,
                "format": event.source_format,
                "timestamp_ms": event.timestamp_ms,
            }
            if event.source_position:
                meta["source_position"] = event.source_position
            if record is None:
                out.append(ChangeChunk(event.key, True, metadata=meta))
                continue
            if enable_guardrails:
                masked = (
                    guard.mask_record(record, column_kinds=kinds)
                    if hasattr(guard, "mask_record")
                    else {
                        k: guard.mask_pii(v) if isinstance(v, str) else v for k, v in record.items()
                    }
                )
            else:
                masked = dict(record)
            state[event.key] = masked
            shown = _cdc.ChangeEvent(
                event.operation, event.source_format, event.database, event.table, event.key, masked
            )
            out.append(
                ChangeChunk(
                    event.key,
                    False,
                    _cdc.change_event_text(shown),
                    masked,
                    {**meta, "record": masked},
                )
            )
        return out, kinds
