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

"""``NexusClient`` file ingestion: one entry point per file and plain-text extraction.

An application hands Nexus raw bytes and gets back everything it stores, so all data
processing stays in Nexus:

- ``process_file``: format dispatch by extension and content sniffing;
- ``extract_text``: readable text of a file (pages, slides, sheets) without chunking.

Storage-side helpers (``prepare_chunks``, ``embed_passages``, ``process_change_events``,
re-ranking) are in ``nexus.client_store``.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from nexus.models import ProcessedDocumentPayload

try:
    from nexus.processing.slack_export import looks_like_slack_export
    from nexus.processing.text_decode import decode_text, looks_binary
except (ImportError, ModuleNotFoundError):  # dev layout: layers installed separately
    from nexus_processing.slack_export import looks_like_slack_export
    from nexus_processing.text_decode import decode_text, looks_binary

__all__ = ["ExtractedText", "IngestMixin", "UnsupportedFormat"]

AUDIO_EXTS = ("wav", "mp3", "aiff", "aif", "ogg", "oga", "opus", "flac", "m4a", "aac")
VIDEO_EXTS = ("mp4", "mov", "avi", "mkv", "webm", "m4v")
IMAGE_EXTS = ("png", "jpg", "jpeg", "bmp", "gif", "webp", "tiff", "tif")
CODE_EXTS = (
    "py",
    "ts",
    "tsx",
    "js",
    "jsx",
    "go",
    "rs",
    "java",
    "cpp",
    "c",
    "h",
    "hpp",
    "cs",
    "rb",
    "php",
    "swift",
    "kt",
    "sql",
    "sh",
)
BINARY_DOC_EXTS = ("pdf", "docx", "doc", "xlsx", "xls", "pptx", "ppt")


class UnsupportedFormat(ValueError):
    """The payload is a format Nexus does not process (e.g. a .zip that is not a Slack export)."""


@dataclass
class ExtractedText:
    """Readable text of one file."""

    text: str
    format: str
    units: list[tuple[str, str]] = field(default_factory=list)  # ("Page 3", text), ("Slide 2", ...)
    readable: bool = True
    encoding: str = ""


def _ext(name: str, file_type: str | None) -> str:
    return (file_type or Path(name).suffix.lstrip(".")).lower()


def _as_bytes(payload: bytes | bytearray | str) -> bytes:
    return (
        bytes(payload) if isinstance(payload, bytes | bytearray) else str(payload).encode("utf-8")
    )


def _image_format(raw: bytes, ext: str) -> str:
    if raw.startswith(b"\xff\xd8\xff"):
        return "jpeg"
    if raw.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if raw.startswith(b"GIF8"):
        return "gif"
    if raw.startswith(b"RIFF") and len(raw) > 12 and raw[8:12] == b"WEBP":
        return "webp"
    if raw.startswith(b"BM"):
        return "bmp"
    return ext


class IngestMixin:
    """Mixed into ``NexusClient`` (uses its ``process_*`` methods, guardrails and embedder)."""

    # ---- files -----------------------------------------------------------------------
    def process_file(
        self,
        document_id: str,
        name: str,
        payload: bytes | str,
        file_type: str | None = None,
        *,
        metadata: dict[str, Any] | None = None,
        enable_guardrails: bool = True,
        shallow_mode: bool = False,
        pdf_page_texts: Callable[[bytes], list[str]] | list[str] | None = None,
    ) -> ProcessedDocumentPayload:
        """Process one file by its extension (``file_type`` overrides it) and content.

        Slack exports (a workspace ``.zip`` or a channel's message ``.json``) are detected
        by content; any other ``.zip`` raises ``UnsupportedFormat``. Text formats are
        decoded with ``decode_text`` (BOM, UTF-8, UTF-16, cp1252; nothing is dropped).
        ``pdf_page_texts`` lets a caller supply page texts from its own PDF engine: Nexus
        still does everything after extraction (scans, running lines, masking, chunks).
        """
        ext = _ext(name, file_type)
        guard = {"enable_guardrails": enable_guardrails, "shallow_mode": shallow_mode}
        if ext in ("zip", "json", "slack"):
            raw = _as_bytes(payload)
            if looks_like_slack_export(raw, name):
                return self.process_slack_export(
                    export_id=document_id, name=name, export_bytes=raw, metadata=metadata, **guard
                )
            if ext == "zip":
                raise UnsupportedFormat(
                    "unsupported .zip archive: only Slack workspace exports are processed; "
                    "upload files individually"
                )
        if ext in ("docx", "doc"):
            return self.process_word_document(
                document_id=document_id,
                name=name,
                docx_bytes=_as_bytes(payload),
                metadata=metadata,
                **guard,
            )
        if ext in ("xlsx", "xls"):
            return self.process_spreadsheet(
                spreadsheet_id=document_id,
                name=name,
                spreadsheet_bytes=_as_bytes(payload),
                metadata=metadata,
                **guard,
            )
        if ext in ("pptx", "ppt"):
            return self.process_presentation(
                presentation_id=document_id,
                name=name,
                presentation_bytes=_as_bytes(payload),
                metadata=metadata,
                **guard,
            )
        if ext == "pdf":
            return self.process_pdf(
                pdf_id=document_id,
                name=name,
                pdf_bytes=_as_bytes(payload),
                metadata=metadata,
                page_texts=pdf_page_texts,
                **guard,
            )
        if ext in AUDIO_EXTS:
            return self.process_audio(
                audio_id=document_id,
                name=name,
                audio_bytes=_as_bytes(payload),
                metadata=metadata,
                auto_extract=True,
                **guard,
            )
        if ext in VIDEO_EXTS:
            return self.process_video(
                video_id=document_id,
                name=name,
                video_bytes=_as_bytes(payload),
                metadata=metadata,
                auto_extract=True,
            )
        if ext in IMAGE_EXTS:
            raw = _as_bytes(payload)
            return self.process_image(
                image_id=document_id,
                name=name,
                image_bytes=raw,
                format_hint=_image_format(raw, ext),
                metadata=metadata,
                auto_extract=True,
            )
        if ext in ("sqlite", "sqlite3", "db"):
            return self.process_sqlite(
                db_id=document_id,
                name=name,
                db_bytes=_as_bytes(payload),
                metadata=metadata,
                **guard,
            )
        text = decode_text(payload).text if isinstance(payload, bytes | bytearray) else str(payload)
        if ext in CODE_EXTS:
            return self.process_code(
                code_id=document_id,
                name=name,
                code_input=text,
                language=ext,
                metadata=metadata,
                **guard,
            )
        if ext in ("eml", "msg", "mbox"):
            return self.process_email(
                email_id=document_id,
                name=name,
                email_bytes=_as_bytes(payload),
                metadata=metadata,
                **guard,
            )
        if ext in ("chat", "slack", "teams"):
            try:
                chat: Any = json.loads(text)
            except ValueError:
                chat = text
            return self.process_chat(
                chat_id=document_id,
                conversation_name=name,
                chat_data=chat,
                metadata=metadata,
                **guard,
            )
        if name.endswith((".openapi.json", ".openapi.yaml", ".openapi.yml")) or ext in (
            "openapi",
            "swagger",
        ):
            return self.process_openapi(
                spec_id=document_id, name=name, spec_data=text, metadata=metadata, **guard
            )
        return self.process_document(
            document_id=document_id,
            name=name,
            text=text,
            file_type=ext or "txt",
            metadata=metadata,
            **guard,
        )

    def extract_text(
        self,
        name: str,
        data: bytes,
        *,
        file_type: str | None = None,
        strict: bool = True,
        pdf_page_texts: Callable[[bytes], list[str]] | list[str] | None = None,
    ) -> ExtractedText:
        """Readable text of a file without chunking or masking.

        PDF pages, Word paragraphs, spreadsheet rows and slides keep their position as
        ``units`` and in the text (``[Page 3]``, ``[Slide 2]``, ``[Sheet R4]``). Media files
        give no text. With ``strict``, a PDF/Office file that yields no text, or a binary
        payload, gives ``""`` and ``readable=False`` instead of decoded noise.
        """
        try:
            from nexus.processing import office
            from nexus.processing.pdf import process_pdf_binary
        except (ImportError, ModuleNotFoundError):
            import nexus_processing.office as office
            from nexus_processing.pdf import process_pdf_binary

        ext = _ext(name, file_type)
        raw = bytes(data)
        units: list[tuple[str, str]] = []
        fmt = ext or "text"
        try:
            if ext == "pdf":
                pdf = process_pdf_binary(raw, auto_extract=False, page_texts=pdf_page_texts)
                units = [(f"Page {p.page_number}", p.text) for p in pdf.pages if p.text.strip()]
                text = "\n\n".join(f"[{label}]\n{body}" for label, body in units)
            elif ext in ("docx", "doc") and raw.startswith(b"PK"):
                word = office.process_word_binary(raw, filename=name, auto_extract=False)
                units = [
                    (c.section_title or f"Paragraph {c.index + 1}", c.text)
                    for c in word.chunks
                    if c.text.strip()
                ]
                text = "\n\n".join(body for _, body in units)
            elif ext in ("xlsx", "xls"):
                sheet = office.process_spreadsheet_binary(raw, filename=name, auto_extract=False)
                units = [
                    (
                        f"{c.sheet_name} R{c.row_index}",
                        " | ".join(f"{v}" for v in c.data.values() if v not in (None, "")),
                    )
                    for c in sheet.all_chunks
                ]
                units = [u for u in units if u[1]]
                text = "\n".join(f"[{label}] {body}" for label, body in units)
            elif ext in ("pptx", "ppt") and raw.startswith(b"PK"):
                deck = office.process_presentation_binary(raw, filename=name, auto_extract=False)
                units = [
                    (f"Slide {s.slide_number}", s.narrative_text)
                    for s in deck.slides
                    if s.narrative_text.strip()
                ]
                text = "\n\n".join(f"[{label}]\n{body}" for label, body in units)
            elif ext in AUDIO_EXTS + VIDEO_EXTS + IMAGE_EXTS:
                return ExtractedText("", fmt, [], readable=False)
            else:
                text = ""
        except Exception:
            text = ""
        if text.strip():
            return ExtractedText(text.replace("\x00", ""), fmt, units, True)
        if strict and (ext in BINARY_DOC_EXTS or looks_binary(raw)):
            return ExtractedText("", fmt, [], readable=False)
        decoded = decode_text(raw)
        return ExtractedText(decoded.text, fmt, [], bool(decoded.text.strip()), decoded.encoding)
