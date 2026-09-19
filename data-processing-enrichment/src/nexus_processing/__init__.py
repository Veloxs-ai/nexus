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

from .engine import ProcessingEngine
from .images import ImageMetadata, VisualFeaturePayload, process_image_binary
from .pdf import PDFMetadata, PDFPage, PDFPayload, process_pdf_binary
from .video import (
    VideoMetadata,
    VideoPayload,
    VideoSceneChunk,
    format_timestamp,
    process_video_binary,
)

__all__ = [
    "ImageMetadata",
    "PDFMetadata",
    "PDFPage",
    "PDFPayload",
    "ProcessingEngine",
    "VideoMetadata",
    "VideoPayload",
    "VideoSceneChunk",
    "VisualFeaturePayload",
    "__version__",
    "format_timestamp",
    "process_image_binary",
    "process_pdf_binary",
    "process_video_binary",
]

__version__ = "0.1.0"
