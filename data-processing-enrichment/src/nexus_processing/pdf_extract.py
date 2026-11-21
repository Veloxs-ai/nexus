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

"""PDF pages to clean page text: text layer, OCR for scans, layout clean-up.

``extract_pdf_pages`` is the PDF pipeline every PDF path in Nexus goes through:

1. text per page from the PDF's text layer (``pdf_reader`` + ``pdf_content``), or from
   ``page_texts`` when the caller already extracted it with another engine;
2. pages without a text layer (scans) are OCR'd from their page image (``pdf_scan``)
   when an OCR provider is available, keeping a confidence score; when it is not, or
   the image codec is unsupported (JBIG2), the page is flagged instead;
3. running headers, footers and page numbers repeated on most pages are removed;
4. headings are recognised from font sizes and rendered as Markdown ``#`` lines, and
   each page knows the heading path in force where it starts;
5. words hyphenated across lines are re-joined. Pages with no text are kept as empty
   (callers must not index them).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from .pdf_content import PageContent, page_content
from .pdf_layout import (
    heading_sizes,
    lines_from_text,
    page_markdown,
    remove_running_lines,
    runs_to_lines,
)
from .pdf_reader import PdfDocument, PdfError
from .pdf_scan import page_image

__all__ = ["PdfExtraction", "PdfPageText", "extract_pdf_pages", "ocr_image"]

SCANNED_PAGE_CHARS = 20  # a page with less text than this has no usable text layer
MIN_OCR_CONFIDENCE = 0.3


@dataclass
class PdfPageText:
    number: int
    text: str  # Markdown (headings as "#" lines); "" when the page has no text
    source: str  # text_layer | ocr | external | empty | needs_ocr | ocr_unsupported
    width: float = 612.0
    height: float = 792.0
    heading_path: list[str] = field(default_factory=list)  # in force where the page starts
    headings: list[tuple[int, str]] = field(default_factory=list)
    ocr_confidence: float | None = None


@dataclass
class PdfExtraction:
    pages: list[PdfPageText]
    version: str = "1.4"
    encrypted: bool = False
    repaired: bool = False
    title: str = ""
    author: str = ""
    running_lines_removed: int = 0
    errors: list[str] = field(default_factory=list)


def ocr_image(provider: Any, image: bytes) -> tuple[str, float | None]:
    """OCR one image; ``(text, mean confidence)``. Providers with ``read_lines`` give
    confidences (lines under ``MIN_OCR_CONFIDENCE`` are dropped); others only text."""
    reader = getattr(provider, "read_lines", None)
    if callable(reader):
        lines = [(t, c) for t, c in reader(image) if t and c >= MIN_OCR_CONFIDENCE]
        if not lines:
            return "", None
        return "\n".join(t for t, _ in lines), round(sum(c for _, c in lines) / len(lines), 3)
    return (provider.extract_text(image) or "").strip(), None


def _info_text(value: Any) -> str:
    if isinstance(value, bytes):
        if value.startswith((b"\xfe\xff", b"\xff\xfe")):
            return value.decode("utf-16", errors="replace")
        return value.decode("latin-1", errors="replace")
    return str(value or "")


def _contents(
    doc: PdfDocument, errors: list[str], only: set[int] | None = None
) -> dict[int, PageContent]:
    """Page content by 0-based page index (all pages, or the indexes in ``only``)."""
    fonts: dict[int, Any] = {}
    out: dict[int, PageContent] = {}
    for index, page in enumerate(doc.pages()):
        if only is not None and index not in only:
            continue
        try:
            out[index] = page_content(doc, page, fonts)
        except Exception as exc:
            errors.append(f"page {index + 1}: {type(exc).__name__}")
            out[index] = PageContent()
    return out


def extract_pdf_pages(
    data: bytes,
    *,
    page_texts: list[str] | Callable[[bytes], list[str]] | None = None,
    ocr_provider: Any = None,
    auto_extract: bool = True,
) -> PdfExtraction:
    """Clean text of every page of a PDF (see the module docstring).

    ``page_texts``: page texts from another extractor (a list, or a function of the PDF
    bytes); Nexus then skips its own text layer reading but still OCRs empty pages,
    removes running lines and re-joins hyphenation. ``ocr_provider``: an OCR engine
    (``auto_detect_ocr_provider()`` is used when ``auto_extract`` and none is given).
    Raises ``PdfError`` when the bytes are not a readable PDF and no ``page_texts`` exist.
    """
    errors: list[str] = []
    doc: PdfDocument | None = None
    try:
        doc = PdfDocument(data)
    except PdfError as exc:
        if page_texts is None:
            raise
        errors.append(str(exc))
    external = page_texts(data) if callable(page_texts) else page_texts
    contents: dict[int, PageContent] = {}
    recovered: set[int] = set()
    if external is not None:
        pages_lines = [lines_from_text(t) for t in external]
        empty = {i for i, t in enumerate(external) if len((t or "").strip()) < SCANNED_PAGE_CHARS}
        if doc is not None and empty:  # pages the other engine found empty: Nexus reads them itself
            try:
                contents = _contents(doc, errors, empty)
            except Exception as exc:
                errors.append(f"layer: {type(exc).__name__}")
        for index, content in contents.items():
            lines = runs_to_lines(content.runs)
            own = len(" ".join(ln.text for ln in lines))
            if index >= len(pages_lines) or own < SCANNED_PAGE_CHARS:
                continue
            if own > len(" ".join(ln.text for ln in pages_lines[index])):
                pages_lines[index] = lines  # a real text layer the other engine missed
                recovered.add(index)
        source = "external"
    else:
        assert doc is not None
        contents = _contents(doc, errors)
        pages_lines = [runs_to_lines(contents[i].runs) for i in sorted(contents)]
        source = "text_layer"

    if ocr_provider is None and auto_extract:
        from .ml_providers import auto_detect_ocr_provider

        try:
            ocr_provider = auto_detect_ocr_provider()
        except Exception:
            ocr_provider = None

    pages_lines, removed = remove_running_lines(pages_lines)
    _body, levels = heading_sizes(pages_lines)
    out: list[PdfPageText] = []
    path: list[tuple[int, str]] = []
    for index, lines in enumerate(pages_lines):
        content = contents.get(index)
        width, height = (content.width, content.height) if content else (612.0, 792.0)
        text, headings = page_markdown(lines, levels)
        page_source = "text_layer" if external is not None and index in recovered else source
        page = PdfPageText(index + 1, text, page_source, width, height, [t for _, t in path])
        if len(text.strip()) < SCANNED_PAGE_CHARS:
            page.text = text.strip()
            page.source = "empty" if not text.strip() else page_source
            if doc is not None and content is not None:
                scan = page_image(doc, content.images, width * height)
                if scan is not None:
                    if scan.data is None:
                        page.source = "ocr_unsupported"
                    elif ocr_provider is None or not auto_extract:
                        page.source = "needs_ocr"
                    else:
                        try:
                            ocr_text, confidence = ocr_image(ocr_provider, scan.data)
                        except Exception as exc:
                            errors.append(f"page {index + 1} ocr: {type(exc).__name__}")
                            ocr_text, confidence = "", None
                        if ocr_text.strip():
                            page.text, page.source, page.ocr_confidence = (
                                ocr_text.strip(),
                                "ocr",
                                confidence,
                            )
        for level, title in headings:
            path = [(lvl, t) for lvl, t in path if lvl < level] + [(level, title)]
        page.headings = headings
        out.append(page)

    info = doc.info() if doc is not None else {}
    return PdfExtraction(
        pages=out,
        version=doc.version if doc is not None else "1.4",
        encrypted=bool(doc and doc.encrypted),
        repaired=bool(doc and doc.repaired),
        title=_info_text(doc.resolve(info.get("Title"))) if doc is not None else "",
        author=_info_text(doc.resolve(info.get("Author"))) if doc is not None else "",
        running_lines_removed=removed,
        errors=errors,
    )
