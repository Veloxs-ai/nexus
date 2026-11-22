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

"""Data processing and enrichment package."""

from .audio import (
    AudioMetadata,
    AudioPayload,
    AudioSegment,
    format_audio_timestamp,
    parse_id3_metadata,
    process_audio_binary,
)
from .cdc import (
    ChangeEvent,
    apply_change,
    change_event_text,
    driver_jsonable,
    is_newer,
    mongo_change_event,
    mysql_row_event,
    normalize_change_event,
    normalize_change_events,
    sign_webhook_payload,
    verify_webhook_signature,
)
from .cdc_ddl import DdlChange, ddl_cleared_tables, parse_ddl
from .chunk_store import document_digest, prepare_chunks, title_passages
from .code import (
    CodeChunk,
    CodeMetadata,
    CodeProcessingPayload,
    CodeSymbol,
    process_code,
    process_openapi_spec,
    process_polyglot_source,
    process_python_source,
)
from .email_chat import (
    AttachmentInfo,
    ChatConversationMetadata,
    ChatConversationPayload,
    ChatMessage,
    ChatThread,
    EmailChunk,
    EmailMetadata,
    EmailPayload,
    process_chat_dialog,
    process_email_binary,
)
from .engine import ProcessingEngine
from .github_markdown import (
    code_fence,
    github_file_markdown,
    github_issue_markdown,
    is_markdown_path,
    markdown_links_absolute,
)
from .images import ImageMetadata, VisualFeaturePayload, process_image_binary
from .json_table import JsonTable, compact_json, find_record_array, flatten_json, json_table
from .kafka import KafkaRecord, KafkaSettings, KafkaSource, KafkaSourceError
from .language import detect_language, detect_script
from .markup_adf import adf_to_markdown
from .markup_html import html_to_markdown
from .ml_providers import (
    AudioTranscriber,
    CaptionProvider,
    EasyOCRProvider,
    FasterWhisperTranscriber,
    OCRProvider,
    PyAVDemuxer,
    VideoDemuxer,
    auto_detect_demuxer,
    auto_detect_ocr_provider,
    auto_detect_transcriber,
    is_easyocr_available,
    is_faster_whisper_available,
    is_package_available,
    is_pyav_available,
    release_idle_models,
)
from .mongodb import (
    chunk_mongo_collection,
    flatten_mongo_document,
    serialize_bson_value,
    serialize_mongo_document,
)
from .mysql import (
    chunk_mysql_table,
    serialize_mysql_row,
)
from .notion import (
    notion_blocks_to_markdown,
    notion_page_title,
    notion_property_value,
    notion_rich_text,
)
from .office import (
    PresentationMetadata,
    PresentationPayload,
    SheetData,
    SlideData,
    SpreadsheetMetadata,
    SpreadsheetPayload,
    SpreadsheetRowChunk,
    WordMetadata,
    WordPayload,
    WordSectionChunk,
    group_word_sections,
    process_presentation_binary,
    process_spreadsheet_binary,
    process_word_binary,
)
from .outline import Outline, OutlineSection, build_outline, plan_sections, section_text
from .passages import join_adjacent, stitch
from .pdf import PDFMetadata, PDFPage, PDFPayload, process_pdf_binary
from .pdf_extract import PdfExtraction, PdfPageText, extract_pdf_pages
from .pgoutput import (
    PgOutputDecoder,
    PgOutputError,
    PgTransaction,
    PostgresLogicalStream,
    PublishedTable,
    SlotInfo,
)
from .quality import assess_text
from .record_caps import cap_document, cap_record_values
from .slack_export import (
    SlackChunk,
    looks_like_slack_export,
    messages_to_chunks,
    parse_slack_export,
    slack_event_message,
    verify_slack_signature,
)
from .sqlite import (
    ColumnSchema,
    ForeignKeyInfo,
    SQLiteMetadata,
    SQLitePayload,
    SQLiteRowChunk,
    TableSchema,
    process_sqlite_binary,
    process_sqlite_file,
)
from .text_decode import DecodedText, decode_text, looks_binary
from .token_budget import estimate_tokens, fit_text, split_header
from .video import (
    VideoMetadata,
    VideoPayload,
    VideoSceneChunk,
    format_timestamp,
    process_video_binary,
)

__all__ = [
    "AttachmentInfo",
    "AudioMetadata",
    "AudioPayload",
    "AudioSegment",
    "AudioTranscriber",
    "CaptionProvider",
    "ChangeEvent",
    "ChatConversationMetadata",
    "ChatConversationPayload",
    "ChatMessage",
    "ChatThread",
    "CodeChunk",
    "CodeMetadata",
    "CodeProcessingPayload",
    "CodeSymbol",
    "ColumnSchema",
    "DdlChange",
    "DecodedText",
    "EasyOCRProvider",
    "EmailChunk",
    "EmailMetadata",
    "EmailPayload",
    "FasterWhisperTranscriber",
    "ForeignKeyInfo",
    "ImageMetadata",
    "JsonTable",
    "KafkaRecord",
    "KafkaSettings",
    "KafkaSource",
    "KafkaSourceError",
    "OCRProvider",
    "Outline",
    "OutlineSection",
    "PDFMetadata",
    "PDFPage",
    "PDFPayload",
    "PdfExtraction",
    "PdfPageText",
    "PgOutputDecoder",
    "PgOutputError",
    "PgTransaction",
    "PostgresLogicalStream",
    "PresentationMetadata",
    "PresentationPayload",
    "ProcessingEngine",
    "PublishedTable",
    "PyAVDemuxer",
    "SQLiteMetadata",
    "SQLitePayload",
    "SQLiteRowChunk",
    "SheetData",
    "SlackChunk",
    "SlideData",
    "SlotInfo",
    "SpreadsheetMetadata",
    "SpreadsheetPayload",
    "SpreadsheetRowChunk",
    "TableSchema",
    "VideoDemuxer",
    "VideoMetadata",
    "VideoPayload",
    "VideoSceneChunk",
    "VisualFeaturePayload",
    "WordMetadata",
    "WordPayload",
    "WordSectionChunk",
    "__version__",
    "adf_to_markdown",
    "apply_change",
    "assess_text",
    "auto_detect_demuxer",
    "auto_detect_ocr_provider",
    "auto_detect_transcriber",
    "build_outline",
    "cap_document",
    "cap_record_values",
    "change_event_text",
    "chunk_mongo_collection",
    "chunk_mysql_table",
    "code_fence",
    "compact_json",
    "ddl_cleared_tables",
    "decode_text",
    "detect_language",
    "detect_script",
    "document_digest",
    "driver_jsonable",
    "estimate_tokens",
    "extract_pdf_pages",
    "find_record_array",
    "fit_text",
    "flatten_json",
    "flatten_mongo_document",
    "format_audio_timestamp",
    "format_timestamp",
    "github_file_markdown",
    "github_issue_markdown",
    "group_word_sections",
    "html_to_markdown",
    "is_easyocr_available",
    "is_faster_whisper_available",
    "is_markdown_path",
    "is_newer",
    "is_package_available",
    "is_pyav_available",
    "join_adjacent",
    "json_table",
    "looks_binary",
    "looks_like_slack_export",
    "markdown_links_absolute",
    "messages_to_chunks",
    "mongo_change_event",
    "mysql_row_event",
    "normalize_change_event",
    "normalize_change_events",
    "notion_blocks_to_markdown",
    "notion_page_title",
    "notion_property_value",
    "notion_rich_text",
    "parse_ddl",
    "parse_id3_metadata",
    "parse_slack_export",
    "plan_sections",
    "prepare_chunks",
    "process_audio_binary",
    "process_chat_dialog",
    "process_code",
    "process_email_binary",
    "process_image_binary",
    "process_openapi_spec",
    "process_pdf_binary",
    "process_polyglot_source",
    "process_presentation_binary",
    "process_python_source",
    "process_spreadsheet_binary",
    "process_sqlite_binary",
    "process_sqlite_file",
    "process_video_binary",
    "process_word_binary",
    "release_idle_models",
    "section_text",
    "serialize_bson_value",
    "serialize_mongo_document",
    "serialize_mysql_row",
    "sign_webhook_payload",
    "slack_event_message",
    "split_header",
    "stitch",
    "title_passages",
    "verify_slack_signature",
    "verify_webhook_signature",
]

__version__ = "0.1.0"
