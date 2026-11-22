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

"""``NexusClient.process_document``: format routing, then text/CSV/JSON chunking, masking and
metadata.
"""

from __future__ import annotations

import hashlib
import re
import time
import unicodedata
from typing import Any

from nexus.chunk_limits import bounded_output
from nexus.models import ProcessedChunk, ProcessedDocumentPayload, ProcessingStageTrace
from nexus.table_records import jsonable, mask_rows

try:
    from nexus.processing.csv_table import group_rows, parse_csv_table
    from nexus.processing.csv_table import row_text as csv_row_text
    from nexus.processing.text_decode import decode_text
except (ImportError, ModuleNotFoundError):
    from nexus_processing.csv_table import group_rows, parse_csv_table
    from nexus_processing.csv_table import row_text as csv_row_text
    from nexus_processing.text_decode import decode_text

from nexus.client_routing import route_document

# A mask the guardrails wrote ("[EMAIL]", "[PHONE:3f9a1c2b7d]", a custom "[ENTITY]").
_MASK_TOKEN = re.compile(r"\[[A-Z][A-Z_]*(?::[0-9a-f]{10})?\]")


def _json_like(file_type: str, text: str) -> bool:
    """True when the text is chunked as JSON (by format, or by the chunker's own sniffing)."""
    if file_type in ("json", "jsonl"):
        return True
    stripped = text.strip()
    return (stripped[:1], stripped[-1:]) in (("{", "}"), ("[", "]"))


def _display(value: Any) -> str:
    """A masked table cell as row text (``""`` for an empty value)."""
    return "" if value is None else str(value)


__all__ = ["DocumentMixin"]


class DocumentMixin:
    """Mixed into ``NexusClient``."""

    @bounded_output
    def process_document(
        self,
        document_id: str,
        name: str,
        text: str | bytes,
        file_type: str | None = None,
        metadata: dict[str, Any] | None = None,
        enable_guardrails: bool = True,
        shallow_mode: bool = False,
        **kwargs: Any,
    ) -> ProcessedDocumentPayload:
        """Pipeline raw text through format-aware chunking and optional PII masking.

        Processing never computes vectors: embed chunk texts with :meth:`embed_texts`.

        Args:
            document_id: Unique identifier for the document record.
            name: Original filename or title.
            text: Raw document text, or binary bytes for images/videos/audio/spreadsheets.
            file_type: Optional file extension override.
            metadata: Custom metadata dictionary to attach to document and chunks.
            enable_guardrails: When True (default), applies PII detection and
                regex masking (Luhn cards, emails, SSNs).
                               When False, preserves exact verbatim text without any masking.
            shallow_mode: Alias for bypassing PII masking for internal reviews.
            **kwargs: Format-specific parameters (e.g. transcript, speaker, ocr_text, caption).

        Returns:
            ProcessedDocumentPayload with chunks, execution trace, and metadata.
        """
        t_start_total = time.perf_counter()
        traces: list[ProcessingStageTrace] = []
        apply_guardrails = enable_guardrails and (not shallow_mode)

        # -------------------------------------------------------------------------
        # Step 1: Text Normalization & Hash Computation (0% - 20%)
        # -------------------------------------------------------------------------
        t0 = time.perf_counter()

        detected_format, routed = route_document(
            self,
            document_id,
            name,
            text,
            file_type,
            metadata,
            enable_guardrails,
            shallow_mode,
            kwargs,
        )
        if routed is not None:
            return routed

        encoding = "str"
        if isinstance(text, bytes | bytearray):
            decoded = decode_text(bytes(text))  # BOM / UTF-8 / UTF-16 / cp1252: never a bytes repr
            text, encoding = decoded.text, decoded.encoding
        clean_text = (
            text.replace("\r\n", "\n").replace("\r", "\n") if isinstance(text, str) else str(text)
        )
        # NFC keeps what the source wrote (x², ﬁ, ①); detection works on its own NFKC view.
        normalized_text = unicodedata.normalize("NFC", clean_text)
        encoded = normalized_text.encode("utf-8")
        file_size_bytes = len(encoded)
        content_hash = hashlib.md5(encoded).hexdigest()
        del encoded
        dt_step1 = (time.perf_counter() - t0) * 1000.0

        traces.append(
            ProcessingStageTrace(
                step_number=1,
                stage_name="Document Ingestion & UTF-8 Normalization",
                status="completed",
                duration_ms=round(dt_step1, 2),
                summary=(
                    f"Normalized {file_size_bytes} bytes of UTF-8 content "
                    f"for format '{detected_format}'. "
                    f"Computed MD5: {content_hash[:8]}..."
                ),
                details={
                    "detected_format": detected_format,
                    "size_bytes": file_size_bytes,
                    "content_hash": content_hash,
                    "encoding": encoding,
                },
            )
        )

        # -------------------------------------------------------------------------
        # Step 2: Format-Aware Structural Chunking (20% - 40%)
        # -------------------------------------------------------------------------
        t0 = time.perf_counter()
        csv_records: list[tuple[list[dict[str, Any]], int, int]] | None = None
        token_bounds: list[int | None] = []
        if detected_format in ("csv", "json"):
            record_chunks = (
                self._csv_record_chunks(normalized_text, apply_guardrails)
                if detected_format == "csv"
                else self._json_record_chunks(normalized_text, apply_guardrails)
            )
            if record_chunks:
                raw_chunks = [item[0] for item in record_chunks]
                csv_records = [(item[1], item[2], item[3]) for item in record_chunks]
                token_bounds = [item[4] if len(item) > 4 else None for item in record_chunks]
        # Free text is masked once, as a whole, before chunking: a value cut at a chunk
        # boundary (or repeated in an overlap) can then never escape the detectors, and
        # overlapping text is not scanned twice. Table rows are masked by column above;
        # JSON is masked per chunk, after it is parsed (a mask would break a bare number).
        masked_text = normalized_text
        mask_whole = (
            apply_guardrails
            and csv_records is None
            and not _json_like(detected_format, normalized_text)
        )
        if mask_whole:
            masked_text = self.guardrails.mask_pii(normalized_text)
        if csv_records is None:
            raw_chunks = self.processing.chunk_document(masked_text, file_type=detected_format)
        if not raw_chunks:
            raw_chunks = [masked_text] if masked_text.strip() else []
        dt_step2 = (time.perf_counter() - t0) * 1000.0

        chunk_desc = (
            "CSV row narratives"
            if detected_format == "csv"
            else ("JSON object blocks" if detected_format == "json" else "semantic paragraphs")
        )
        traces.append(
            ProcessingStageTrace(
                step_number=2,
                stage_name="Format-Aware Structural Chunking",
                status="completed",
                duration_ms=round(dt_step2, 2),
                summary=f"Generated {len(raw_chunks)} {chunk_desc} preserving contextual layout.",
                details={"chunk_count": len(raw_chunks), "strategy": chunk_desc},
            )
        )

        # -------------------------------------------------------------------------
        # Step 3: Document Metadata & Classification Extraction (40% - 60%)
        # -------------------------------------------------------------------------
        t0 = time.perf_counter()
        # Metadata of what is stored: with guardrails on, the masked text (no raw e-mail
        # addresses in ``metadata.emails``); table rows, from their masked chunks.
        # Rows and JSON chunks are masked after this step: their e-mail list is taken from
        # the masked chunks in step 5.
        rows_masked = apply_guardrails and not mask_whole
        doc_metadata = self.processing.extract_metadata(
            normalized_text if rows_masked else masked_text
        )
        if metadata:
            doc_metadata.update(metadata)
        doc_metadata["file_type"] = detected_format
        doc_metadata["source_format"] = detected_format
        doc_metadata["is_tabular"] = detected_format == "csv" or csv_records is not None
        doc_metadata["guardrails_enabled"] = apply_guardrails
        classification = doc_metadata.get("classification", "general")
        dt_step3 = (time.perf_counter() - t0) * 1000.0

        traces.append(
            ProcessingStageTrace(
                step_number=3,
                stage_name="Metadata & Entity Classification",
                status="completed",
                duration_ms=round(dt_step3, 2),
                summary=(
                    f"Classified as '{classification}'. "
                    f"Extracted {len(doc_metadata.get('entities', []))} entities "
                    f"and {len(doc_metadata.get('tags', []))} domain tags."
                ),
                details={
                    "classification": classification,
                    "entities_count": len(doc_metadata.get("entities", [])),
                    "tags": doc_metadata.get("tags", []),
                },
            )
        )

        # -------------------------------------------------------------------------
        # Step 4: Safety Guardrails & PII Masking (60% - 80%)
        # -------------------------------------------------------------------------
        t0 = time.perf_counter()
        # Rows were masked by column and free text as a whole (step 2): count the chunks
        # that carry a mask. JSON chunks are masked here.
        cleaned_chunks_text: list[str] = list(raw_chunks)
        total_redacted = 0
        if mask_whole and masked_text != normalized_text:
            total_redacted = sum(1 for c in cleaned_chunks_text if _MASK_TOKEN.search(c))
        elif apply_guardrails and csv_records is None:
            for i, chunk_txt in enumerate(raw_chunks):
                masked = self.guardrails.mask_pii(chunk_txt)
                total_redacted += masked != chunk_txt
                cleaned_chunks_text[i] = masked
        dt_step4 = (time.perf_counter() - t0) * 1000.0

        guardrails_summary = (
            f"Evaluated {len(raw_chunks)} chunks through PII scrubbers "
            f"(Luhn credit cards, emails, SSNs). "
            f"Redacted items in {total_redacted} chunk(s)."
            if apply_guardrails
            else "Safety guardrails bypassed: preserving raw verbatim text without redaction."
        )

        traces.append(
            ProcessingStageTrace(
                step_number=4,
                stage_name="Safety Guardrails & PII Sanitization",
                status="completed",
                duration_ms=round(dt_step4, 2),
                summary=guardrails_summary,
                details={"guardrails_enabled": apply_guardrails, "chunks_with_pii": total_redacted},
            )
        )

        # -------------------------------------------------------------------------
        # Step 5: Dimensional Chunk Assembly (80% - 100%)
        # -------------------------------------------------------------------------
        t0 = time.perf_counter()
        processed_chunks: list[ProcessedChunk] = []
        for idx, cleaned_chunk in enumerate(cleaned_chunks_text):
            chunk_meta = self.processing.extract_metadata(cleaned_chunk)
            chunk_meta["document_id"] = document_id
            chunk_meta["document_name"] = name
            chunk_meta["classification"] = classification
            chunk_meta["file_type"] = detected_format
            chunk_meta["source_format"] = detected_format
            chunk_meta["is_tabular"] = detected_format == "csv" or csv_records is not None
            chunk_meta["guardrails_enabled"] = apply_guardrails
            chunk_meta["content_hash"] = hashlib.md5(cleaned_chunk.encode("utf-8")).hexdigest()
            if csv_records is not None:
                records, first, last = csv_records[idx]
                if records:
                    chunk_meta["records"] = records
                    chunk_meta["row_range"] = [first, last]

            chunk_id = f"{document_id}:{idx}"
            chunk = ProcessedChunk(
                chunk_id=chunk_id,
                document_id=document_id,
                chunk_index=idx,
                text=cleaned_chunk,
                metadata=chunk_meta,
            )
            if idx < len(token_bounds):
                chunk._token_bound = token_bounds[idx]
            processed_chunks.append(chunk)
        if rows_masked:  # the e-mail addresses still visible in the masked rows
            doc_metadata["emails"] = sorted(
                {e for c in processed_chunks for e in c.metadata.get("emails", ())}
            )
        dt_step5 = (time.perf_counter() - t0) * 1000.0

        traces.append(
            ProcessingStageTrace(
                step_number=5,
                stage_name="Chunk Assembly",
                status="completed",
                duration_ms=round(dt_step5, 2),
                summary="Assembled final chunks with grounded metadata (vectors are produced at "
                "storage time by embed_texts()).",
                details={},
            )
        )

        total_ms = (time.perf_counter() - t_start_total) * 1000.0
        summary_msg = (
            f"Successfully processed '{name}' into {len(processed_chunks)} "
            f"chunks in {total_ms:.1f}ms."
        )

        return ProcessedDocumentPayload(
            document_id=document_id,
            name=name,
            file_type=detected_format,
            file_size_bytes=file_size_bytes,
            content_hash=content_hash,
            classification=classification,
            chunks=processed_chunks,
            metadata=doc_metadata,
            execution_trace=traces,
            summary=summary_msg,
        )

    def _csv_record_chunks(
        self, text: str, apply_guardrails: bool
    ) -> list[tuple[str, list[dict[str, Any]], int, int, int | None]]:
        """CSV -> row-group chunks with their typed, column-masked rows.

        Returns ``(text, records, first row, last row, token bound)`` per chunk (1-based
        rows; the bound is the summed row costs, ``None`` without a limiter), or an empty
        list when the text is not a usable table.
        """
        table = parse_csv_table(text)
        if table is None:
            return []
        classify = getattr(self.guardrails, "classify_columns", None)
        kinds = classify(table.typed_rows) if (apply_guardrails and classify) else None
        typed, _ = mask_rows(self.guardrails, table.typed_rows, apply_guardrails, kinds)
        # Each cell is masked once: a display cell is its source text unless masking
        # changed the typed value (then it is the masked value).
        shown = (
            [
                {
                    k: v if masked.get(k) == source.get(k) else _display(masked.get(k))
                    for k, v in row.items()
                }
                for row, source, masked in zip(table.rows, table.typed_rows, typed, strict=True)
            ]
            if apply_guardrails
            else table.rows
        )
        texts = [csv_row_text(n, row) for n, row in enumerate(shown, start=1)]
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
        return [
            (
                chunk_text,
                [jsonable(r) for r in typed[first : last + 1]],
                first + 1,
                last + 1,
                limiter.group_bound(costs, first, last, header_tokens) if limiter else None,
            )
            for chunk_text, first, last in groups
        ]
