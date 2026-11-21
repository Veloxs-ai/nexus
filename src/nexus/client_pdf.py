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

"""``NexusClient.process_pdf``: PDF bytes to page-grounded, masked chunks.

Pages come from ``nexus.processing.pdf.process_pdf_binary`` (stdlib PDF reader, OCR of
scanned pages, running header/footer removal, font-size headings), or from page texts a
caller extracted with its own engine (``page_texts``). One chunk per page with text,
``[Page N]``-prefixed; the heading path in force where the page starts is added as a
``Section:`` line and as ``metadata.heading_path``. Pages without text produce no chunk
(they are counted in the document metadata), so an empty scan never takes a top-k slot.
"""

from __future__ import annotations

import hashlib
import time
from pathlib import Path
from typing import Any

from nexus.chunk_limits import bounded_output
from nexus.models import ProcessedChunk, ProcessedDocumentPayload, ProcessingStageTrace

try:
    from nexus.processing.pdf import process_pdf_binary
except (ImportError, ModuleNotFoundError):
    from nexus_processing.pdf import process_pdf_binary

__all__ = ["PdfMixin"]


def _trace(
    step: int, name: str, started: float, summary: str, details: dict[str, Any]
) -> ProcessingStageTrace:
    return ProcessingStageTrace(
        step_number=step,
        stage_name=name,
        status="completed",
        duration_ms=round((time.perf_counter() - started) * 1000.0, 2),
        summary=summary,
        details=details,
    )


class PdfMixin:
    """Mixed into ``NexusClient``."""

    @bounded_output
    def process_pdf(
        self,
        pdf_id: str,
        name: str,
        pdf_bytes: bytes | None = None,
        file_path: str | Path | None = None,
        metadata: dict[str, Any] | None = None,
        enable_guardrails: bool = True,
        shallow_mode: bool = False,
        ocr_provider: Any = None,
        auto_extract: bool = True,
        page_texts: Any = None,
    ) -> ProcessedDocumentPayload:
        """Process a PDF into page-grounded chunks (see the module docstring).

        Args:
            pdf_id: Unique identifier for the PDF document.
            name: Filename or descriptor (e.g. 'annual_report.pdf').
            pdf_bytes: Raw binary PDF payload.
            file_path: Optional path to read the PDF from when ``pdf_bytes`` is not given.
            metadata: Custom metadata attached to the document and every page chunk.
            enable_guardrails: When True (default), PII is masked.
            shallow_mode: Alias for bypassing PII masking for internal reviews.
            ocr_provider: OCR engine for scanned pages (auto-detected when ``auto_extract``).
            auto_extract: When True (default), scanned pages are OCR'd if an engine exists.
            page_texts: Page texts from another extractor (a list, or a function of the
                PDF bytes); Nexus then skips its own text-layer reading.
        """
        t_start_total = time.perf_counter()
        apply_guardrails = enable_guardrails and (not shallow_mode)
        if pdf_bytes is not None:
            raw_data = pdf_bytes
        elif file_path is not None:
            raw_data = Path(file_path).read_bytes()
        else:
            raise ValueError("Either pdf_bytes or file_path must be provided to process_pdf.")
        file_size_bytes = len(raw_data)
        content_hash = hashlib.md5(raw_data).hexdigest()
        traces: list[ProcessingStageTrace] = []

        t0 = time.perf_counter()
        pdf_payload = process_pdf_binary(
            raw_data, ocr_provider=ocr_provider, auto_extract=auto_extract, page_texts=page_texts
        )
        meta = pdf_payload.metadata
        sources = dict(meta.details.get("page_sources") or {})
        traces.append(
            _trace(
                1,
                "PDF Header & Object Graph Parsing",
                t0,
                f"Parsed ISO 32000-1 PDF v{meta.version} object graph ({file_size_bytes} bytes, "
                f"{meta.page_count} pages detected).",
                {
                    "version": meta.version,
                    "page_count": meta.page_count,
                    "file_size_bytes": file_size_bytes,
                    "is_encrypted": meta.is_encrypted,
                    "repaired_xref": meta.details.get("repaired_xref", False),
                },
            )
        )
        t0 = time.perf_counter()
        traces.append(
            _trace(
                2,
                "FlateDecode Stream Decompression (zlib)",
                t0,
                f"Decoded content streams of {meta.page_count} page objects (Flate, LZW, ASCII85, "
                "ASCIIHex, RunLength; standard library).",
                {"decompressed_pages": meta.page_count},
            )
        )
        t0 = time.perf_counter()
        total_words = sum(p.word_count for p in pdf_payload.pages)
        total_chars = sum(p.char_count for p in pdf_payload.pages)
        traces.append(
            _trace(
                3,
                "PostScript Text Operator Decoding (BT/ET/Tj/TJ)",
                t0,
                f"Decoded {total_words} words ({total_chars} characters) across "
                f"{len(pdf_payload.pages)} pages; page sources {sources}; "
                f"{meta.details.get('running_lines_removed', 0)} running header/footer lines "
                "removed.",
                {
                    "total_words": total_words,
                    "total_chars": total_chars,
                    "pages_extracted": len(pdf_payload.pages),
                    "page_sources": sources,
                    "running_lines_removed": meta.details.get("running_lines_removed", 0),
                },
            )
        )

        t0 = time.perf_counter()
        sanitized: list[tuple[Any, str]] = []
        total_masked_items = 0
        for page in pdf_payload.pages:
            text = page.text.strip()
            if not text:
                continue
            if apply_guardrails:
                scrubbed = self.guardrails.mask_pii(text)
                total_masked_items += int(scrubbed != text)
            else:
                scrubbed = text
            sanitized.append((page, scrubbed))
        traces.append(
            _trace(
                4,
                "Safety Guardrails & PII Sanitization",
                t0,
                f"Applied PII detection across {len(sanitized)} pages. Masked {total_masked_items} "
                "sensitive items (Luhn cards, emails, SSNs).",
                {"guardrails_enabled": apply_guardrails, "masked_items": total_masked_items},
            )
        )

        t0 = time.perf_counter()
        chunks: list[ProcessedChunk] = []
        for page, text in sanitized:
            crumb = " > ".join(page.heading_path)
            starts_with_heading = text.startswith("#")
            lead = f"Section: {crumb}\n" if crumb and not starts_with_heading else ""
            sep = "\n" if (lead or starts_with_heading) else " "
            chunk_meta: dict[str, Any] = {
                "page_number": page.page_number,
                "page_label": page.page_label,
                "width_pts": page.width_pts,
                "height_pts": page.height_pts,
                "word_count": page.word_count,
                "char_count": page.char_count,
                "is_pdf": True,
                "text_source": page.source,
            }
            if page.heading_path:
                chunk_meta["heading_path"] = list(page.heading_path)
            if page.ocr_confidence is not None:
                chunk_meta["ocr_confidence"] = page.ocr_confidence
            if metadata:
                chunk_meta.update(metadata)
            chunks.append(
                ProcessedChunk(
                    chunk_id=f"{pdf_id}:{page.page_number - 1}",
                    document_id=pdf_id,
                    chunk_index=len(chunks),
                    text=f"{page.page_label}{sep}{lead}{text}",
                    metadata=chunk_meta,
                )
            )
        empty_pages = [p.page_number for p in pdf_payload.pages if not p.text.strip()]
        traces.append(
            _trace(
                5,
                "Page-Grounded Chunk Assembly",
                t0,
                "Assembled final chunks with grounded metadata (vectors are produced at storage "
                f"time by embed_texts()); {len(empty_pages)} page(s) without text were not "
                "chunked.",
                {"empty_pages": empty_pages[:200]},
            )
        )

        doc_meta: dict[str, Any] = {
            "format": "PDF",
            "version": meta.version,
            "page_count": meta.page_count,
            "total_words": total_words,
            "total_chars": total_chars,
            "is_encrypted": meta.is_encrypted,
            "is_pdf": True,
            "page_sources": sources,
            "empty_pages": len(empty_pages),
        }
        if meta.title:
            doc_meta["title"] = meta.title
        if metadata:
            doc_meta.update(metadata)
        total_ms = (time.perf_counter() - t_start_total) * 1000.0
        return ProcessedDocumentPayload(
            document_id=pdf_id,
            name=name,
            file_type="pdf",
            file_size_bytes=file_size_bytes,
            content_hash=content_hash,
            classification=doc_meta.get("classification", "document"),
            chunks=chunks,
            metadata=doc_meta,
            execution_trace=traces,
            summary=(
                f"Successfully processed PDF '{name}' ({meta.page_count} pages, {total_words} "
                f"words) into {len(chunks)} page-grounded chunks in {total_ms:.1f}ms."
            ),
        )
