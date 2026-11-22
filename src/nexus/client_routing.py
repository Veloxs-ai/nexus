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

"""Format routing for ``NexusClient.process_document``.

The format comes from ``file_type``, else the name's extension, and is corrected by sniffing
the leading bytes. Binary and structured formats are handed to their ``process_*`` method on
the client; plain text, CSV and JSON fall through to the document pipeline.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

__all__ = ["route_document"]

# Routed to process_audio; compressed formats are decoded with PyAV when installed.
_AUDIO_FORMATS = ("wav", "aiff", "aif", "mp3", "m4a", "aac", "ogg", "oga", "opus", "flac")


def _is_existing_file(value: str) -> bool:
    """True only for a real file path; raw document text never raises here."""
    if not value or len(value) > 4096 or "\n" in value or "\x00" in value:
        return False
    try:
        return Path(value).is_file()
    except (OSError, ValueError):
        return False


def route_document(
    client: Any,
    document_id: str,
    name: str,
    text: Any,
    file_type: str | None,
    metadata: dict[str, Any] | None,
    enable_guardrails: bool,
    shallow_mode: bool,
    kwargs: dict[str, Any],
) -> tuple[str, Any]:
    """``(format, payload)``: the payload of the ``process_*`` method the input is routed to,
    or ``None`` when the input is chunked by ``process_document`` itself."""
    # Resolve raw input bytes if present for content sniffing & binary routing
    raw_input_bytes: bytes | None = None
    if isinstance(text, bytes | bytearray):
        raw_input_bytes = bytes(text)
    elif isinstance(text, str):
        p = Path(text)
        if _is_existing_file(text):
            try:
                raw_input_bytes = p.read_bytes()
            except Exception:
                raw_input_bytes = None

    detected_format = (file_type or Path(name).suffix.removeprefix(".") or "text").lower()

    # Header sniffing for resilience against mismatched or missing extensions
    if raw_input_bytes:
        if raw_input_bytes.startswith(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"):
            detected_format = "xls"
        elif raw_input_bytes.startswith(b"\xff\xd8"):
            detected_format = "jpg"
        elif raw_input_bytes.startswith(b"\x89PNG\r\n\x1a\n"):
            detected_format = "png"
        elif raw_input_bytes.startswith(b"BM"):
            detected_format = "bmp"
        elif raw_input_bytes.startswith(b"ID3") or raw_input_bytes.startswith(b"\xff\xfb"):
            detected_format = "mp3"
        elif raw_input_bytes.startswith(b"OggS"):
            detected_format = "ogg"
        elif raw_input_bytes.startswith(b"fLaC"):
            detected_format = "flac"
        elif (
            len(raw_input_bytes) >= 12
            and raw_input_bytes[4:8] == b"ftyp"
            and (raw_input_bytes[8:11] == b"M4A" or detected_format in _AUDIO_FORMATS)
        ):
            detected_format = "m4a"
        elif len(raw_input_bytes) >= 8 and raw_input_bytes[4:8] in (b"ftyp", b"moov"):
            detected_format = "mp4"

    # Automatic routing for image payloads
    if detected_format in ("png", "jpg", "jpeg", "bmp"):
        raw_img_bytes = raw_input_bytes
        if raw_img_bytes is not None:
            return detected_format, client.process_image(
                image_id=document_id,
                name=name,
                image_bytes=raw_img_bytes,
                format_hint=detected_format,
                metadata=metadata,
                ocr_text=kwargs.get("ocr_text"),
                caption=kwargs.get("caption"),
                ocr_provider=kwargs.get("ocr_provider"),
                auto_extract=kwargs.get("auto_extract", False),
            )

    # Automatic routing for video payloads
    if detected_format in ("mp4", "mov", "m4v", "webm", "mkv"):
        raw_vid_bytes = raw_input_bytes
        if raw_vid_bytes is not None:
            return detected_format, client.process_video(
                video_id=document_id,
                name=name,
                video_bytes=raw_vid_bytes,
                metadata=metadata,
                scene_interval_seconds=kwargs.get("scene_interval_seconds", 10.0),
                transcript_segments=kwargs.get("transcript_segments"),
                transcript=kwargs.get("transcript"),
                captions=kwargs.get("captions"),
                demuxer=kwargs.get("demuxer"),
                transcriber=kwargs.get("transcriber"),
                ocr_provider=kwargs.get("ocr_provider"),
                auto_extract=kwargs.get("auto_extract", False),
            )

    # Automatic routing for PDF payloads
    if detected_format == "pdf":
        raw_pdf_bytes = None
        if isinstance(text, bytes | bytearray):
            raw_pdf_bytes = bytes(text)
        elif isinstance(text, str):
            p = Path(text)
            if _is_existing_file(text):
                raw_pdf_bytes = p.read_bytes()
        if raw_pdf_bytes is not None:
            return detected_format, client.process_pdf(
                pdf_id=document_id,
                name=name,
                pdf_bytes=raw_pdf_bytes,
                metadata=metadata,
                enable_guardrails=enable_guardrails,
                shallow_mode=shallow_mode,
            )

    # Automatic routing for MySQL table payloads
    if detected_format == "mysql":
        raw_rows = None
        if isinstance(text, list):
            raw_rows = text
        elif isinstance(text, str):
            p = Path(text)
            if _is_existing_file(text):
                try:
                    raw_rows = json.loads(p.read_text(encoding="utf-8"))
                except Exception:
                    raw_rows = None
            else:
                try:
                    raw_rows = json.loads(text)
                except Exception:
                    raw_rows = None
        if isinstance(raw_rows, list):
            return detected_format, client.process_mysql_table(
                table_name=name or document_id,
                rows=raw_rows,
                metadata=metadata,
                enable_guardrails=enable_guardrails,
                shallow_mode=shallow_mode,
            )

    # Automatic routing for MongoDB collection payloads
    if detected_format in ("mongodb", "mongo"):
        raw_docs = None
        if isinstance(text, list):
            raw_docs = text
        elif isinstance(text, str):
            p = Path(text)
            if _is_existing_file(text):
                try:
                    raw_docs = json.loads(p.read_text(encoding="utf-8"))
                except Exception:
                    raw_docs = None
            else:
                try:
                    raw_docs = json.loads(text)
                except Exception:
                    raw_docs = None
        if isinstance(raw_docs, list):
            return detected_format, client.process_mongo_collection(
                collection_name=name or document_id,
                documents=raw_docs,
                metadata=metadata,
                enable_guardrails=enable_guardrails,
                shallow_mode=shallow_mode,
            )

    # Automatic routing for Audio payloads
    if detected_format in _AUDIO_FORMATS:
        raw_audio_bytes = raw_input_bytes
        if raw_audio_bytes is not None:
            return detected_format, client.process_audio(
                audio_id=document_id,
                name=name,
                audio_bytes=raw_audio_bytes,
                window_seconds=kwargs.get("window_seconds", 10.0),
                transcript=kwargs.get("transcript"),
                speaker=kwargs.get("speaker"),
                metadata=metadata,
                enable_guardrails=enable_guardrails,
                shallow_mode=shallow_mode,
                transcriber=kwargs.get("transcriber"),
                auto_extract=kwargs.get("auto_extract", False),
            )

    # Automatic routing for Spreadsheet (.xlsx and legacy .xls) payloads
    if detected_format in ("xlsx", "xls", "excel"):
        raw_xlsx_bytes = raw_input_bytes
        if raw_xlsx_bytes is not None:
            return detected_format, client.process_spreadsheet(
                spreadsheet_id=document_id,
                name=name or f"workbook.{detected_format}",
                spreadsheet_bytes=raw_xlsx_bytes,
                metadata=metadata,
                enable_guardrails=enable_guardrails,
                shallow_mode=shallow_mode,
            )

    # Automatic routing for Presentation (.pptx) payloads
    if detected_format in ("pptx", "powerpoint"):
        raw_pptx_bytes = None
        if isinstance(text, bytes | bytearray):
            raw_pptx_bytes = bytes(text)
        elif isinstance(text, str):
            p = Path(text)
            if _is_existing_file(text):
                raw_pptx_bytes = p.read_bytes()
        if raw_pptx_bytes is not None:
            return detected_format, client.process_presentation(
                presentation_id=document_id,
                name=name or "presentation.pptx",
                presentation_bytes=raw_pptx_bytes,
                metadata=metadata,
                enable_guardrails=enable_guardrails,
                shallow_mode=shallow_mode,
            )

    # Automatic routing for Word Document (.docx) payloads
    if detected_format in ("docx", "word") or (
        detected_format == "doc"
        and isinstance(text, bytes | bytearray)
        and text.startswith(b"PK\x03\x04")
    ):
        raw_docx_bytes = None
        if isinstance(text, bytes | bytearray):
            raw_docx_bytes = bytes(text)
        elif isinstance(text, str):
            p = Path(text)
            if _is_existing_file(text):
                raw_docx_bytes = p.read_bytes()
        if raw_docx_bytes is not None:
            return detected_format, client.process_word_document(
                document_id=document_id,
                name=name or "document.docx",
                docx_bytes=raw_docx_bytes,
                metadata=metadata,
                enable_guardrails=enable_guardrails,
                shallow_mode=shallow_mode,
            )

    # Automatic routing for Email (.eml) payloads
    if detected_format in ("eml", "email"):
        raw_email_bytes = None
        if isinstance(text, bytes | bytearray):
            raw_email_bytes = bytes(text)
        elif isinstance(text, str):
            p = Path(text)
            if _is_existing_file(text):
                raw_email_bytes = p.read_bytes()
            elif text.startswith(("From:", "Received:", "Return-Path:", "MIME-Version:")):
                raw_email_bytes = text.encode("utf-8")
        if raw_email_bytes is not None:
            return detected_format, client.process_email(
                email_id=document_id,
                name=name or "message.eml",
                email_bytes=raw_email_bytes,
                metadata=metadata,
                enable_guardrails=enable_guardrails,
                shallow_mode=shallow_mode,
            )

    # Automatic routing for Chat conversation payloads
    if detected_format in ("chat", "slack", "teams"):
        return detected_format, client.process_chat(
            chat_id=document_id,
            conversation_name=name or "chat_conversation",
            chat_data=text,
            metadata=metadata,
            enable_guardrails=enable_guardrails,
            shallow_mode=shallow_mode,
        )

    # Automatic routing for SQLite database payloads
    if detected_format in ("sqlite", "sqlite3", "db") or (
        isinstance(text, bytes | bytearray) and text.startswith(b"SQLite format 3\x00")
    ):
        raw_db_bytes = None
        db_file_path = None
        if isinstance(text, bytes | bytearray):
            raw_db_bytes = bytes(text)
        elif isinstance(text, str):
            p = Path(text)
            if _is_existing_file(text):
                db_file_path = p
        if raw_db_bytes is not None or db_file_path is not None:
            return detected_format, client.process_sqlite(
                db_id=document_id,
                name=name or "database.db",
                db_bytes=raw_db_bytes,
                file_path=db_file_path,
                metadata=metadata,
                enable_guardrails=enable_guardrails,
                shallow_mode=shallow_mode,
            )

    # Automatic routing for OpenAPI / Swagger specifications
    if detected_format in ("openapi", "swagger") or (
        detected_format in ("json", "yaml", "yml")
        and ("openapi" in (name or "").lower() or "swagger" in (name or "").lower())
    ):
        return detected_format, client.process_openapi(
            spec_id=document_id,
            name=name or "openapi.json",
            spec_data=text,
            metadata=metadata,
            enable_guardrails=enable_guardrails,
            shallow_mode=shallow_mode,
        )

    # Automatic routing for Source Code AST & Polyglot files
    code_exts = (
        "py",
        "python",
        "js",
        "jsx",
        "ts",
        "tsx",
        "go",
        "golang",
        "rs",
        "rust",
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
    )
    if detected_format in code_exts:
        return detected_format, client.process_code(
            code_id=document_id,
            name=name or f"source.{detected_format}",
            code_input=text,
            language=detected_format,
            metadata=metadata,
            enable_guardrails=enable_guardrails,
            shallow_mode=shallow_mode,
        )

    return detected_format, None
