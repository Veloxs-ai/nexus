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

"""Zero-dependency, pure-Python ISO 32000-1 PDF text extraction.

``process_pdf_binary`` reads a PDF through ``pdf_extract.extract_pdf_pages`` (object
model reader with xref/object streams, ToUnicode fonts, a content-stream interpreter,
OCR of scanned pages, running header/footer removal and font-size headings) and returns
page-by-page text with grounded point dimensions. The older regular-expression scanner
(``parse_pdf_objects``) remains as the fallback for bytes the reader cannot open.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .pdf_legacy import (  # re-exported: public helpers of the pre-3.2.0 scanner
    _process_pdf_binary_legacy,
    decode_pdf_hex_string,
    decode_pdf_literal_string,
    decompress_stream,
    extract_text_from_content_stream,
    parse_pdf_objects,
)

__all__ = [
    "PDFMetadata",
    "PDFPage",
    "PDFPayload",
    "decode_pdf_hex_string",
    "decode_pdf_literal_string",
    "decompress_stream",
    "extract_text_from_content_stream",
    "parse_pdf_objects",
    "process_pdf_binary",
]


@dataclass
class PDFPage:
    page_number: int
    text: str
    page_label: str
    width_pts: float
    height_pts: float
    word_count: int
    char_count: int
    # text_layer | ocr | external | empty | needs_ocr | ocr_unsupported | encrypted
    source: str = "text_layer"
    heading_path: list[str] = field(default_factory=list)
    ocr_confidence: float | None = None


@dataclass
class PDFMetadata:
    format: str
    version: str
    page_count: int
    title: str
    author: str
    is_encrypted: bool
    file_size_bytes: int
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class PDFPayload:
    metadata: PDFMetadata
    pages: list[PDFPage]

    @property
    def full_text(self) -> str:
        return "\n\n".join(p.text for p in self.pages if p.text.strip())


def process_pdf_binary(
    data: bytes,
    ocr_provider: Any = None,
    auto_extract: bool = True,
    page_texts: Any = None,
) -> PDFPayload:
    """Page texts of a PDF (see the module docstring).

    ``page_texts``: page texts from another extractor (a list, or a function of the PDF
    bytes); Nexus then cleans them (scan OCR, running lines, hyphenation) instead of
    reading the text layer itself.
    """
    from .pdf_extract import extract_pdf_pages
    from .pdf_reader import PdfError

    try:
        extraction = extract_pdf_pages(
            data, page_texts=page_texts, ocr_provider=ocr_provider, auto_extract=auto_extract
        )
    except PdfError:
        return _process_pdf_binary_legacy(data, ocr_provider, auto_extract)
    if not extraction.pages:  # no page tree or page objects: the old scanner may still find text
        return _process_pdf_binary_legacy(data, ocr_provider, auto_extract)
    pages = [
        PDFPage(
            page_number=p.number,
            text=p.text,
            page_label=f"[Page {p.number}]",
            width_pts=float(p.width),
            height_pts=float(p.height),
            word_count=len(p.text.split()),
            char_count=len(p.text),
            source=p.source,
            heading_path=list(p.heading_path),
            ocr_confidence=p.ocr_confidence,
        )
        for p in extraction.pages
    ]
    sources: dict[str, int] = {}
    for p in pages:
        sources[p.source] = sources.get(p.source, 0) + 1
    meta = PDFMetadata(
        format="PDF",
        version=extraction.version,
        page_count=len(pages),
        title=extraction.title,
        author=extraction.author,
        is_encrypted=extraction.encrypted,
        file_size_bytes=len(data),
        details={
            "extracted_pages": len(pages),
            "page_sources": sources,
            "running_lines_removed": extraction.running_lines_removed,
            "repaired_xref": extraction.repaired,
            "errors": extraction.errors[:20],
        },
    )
    return PDFPayload(metadata=meta, pages=pages)
