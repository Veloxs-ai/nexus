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
    change_event_text,
    normalize_change_event,
    normalize_change_events,
    sign_webhook_payload,
    verify_webhook_signature,
)
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
from .images import ImageMetadata, VisualFeaturePayload, process_image_binary
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
from .pdf import PDFMetadata, PDFPage, PDFPayload, process_pdf_binary
from .pgoutput import (
    PgOutputDecoder,
    PgOutputError,
    PgTransaction,
    PostgresLogicalStream,
    PublishedTable,
    SlotInfo,
)
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
    "EasyOCRProvider",
    "EmailChunk",
    "EmailMetadata",
    "EmailPayload",
    "FasterWhisperTranscriber",
    "ForeignKeyInfo",
    "ImageMetadata",
    "OCRProvider",
    "PDFMetadata",
    "PDFPage",
    "PDFPayload",
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
    "auto_detect_demuxer",
    "auto_detect_ocr_provider",
    "auto_detect_transcriber",
    "change_event_text",
    "chunk_mongo_collection",
    "chunk_mysql_table",
    "flatten_mongo_document",
    "format_audio_timestamp",
    "format_timestamp",
    "group_word_sections",
    "is_easyocr_available",
    "is_faster_whisper_available",
    "is_package_available",
    "is_pyav_available",
    "looks_like_slack_export",
    "messages_to_chunks",
    "normalize_change_event",
    "normalize_change_events",
    "parse_id3_metadata",
    "parse_slack_export",
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
    "serialize_bson_value",
    "serialize_mongo_document",
    "serialize_mysql_row",
    "sign_webhook_payload",
    "slack_event_message",
    "verify_slack_signature",
    "verify_webhook_signature",
]

__version__ = "0.1.0"
