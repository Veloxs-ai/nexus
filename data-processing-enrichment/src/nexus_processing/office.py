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

"""Zero-dependency Microsoft Office OpenXML (XLSX & PPTX) processors."""

from __future__ import annotations

from .docx_text import (  # noqa: F401 (re-export)
    block_texts,
    cell_span,
    cell_text,
    heading_levels,
    outline_level,
    paragraph_text,
)
from .office_docx import (
    process_word_binary,
)
from .office_pptx import (
    PresentationMetadata,
    PresentationPayload,
    SlideData,
    process_presentation_binary,
)
from .office_sheet import (  # noqa: F401 (re-export)
    SheetData,
    SpreadsheetMetadata,
    SpreadsheetPayload,
    SpreadsheetRowChunk,
    _display,
    _is_legacy_xls,
    _process_legacy_xls,
    _process_legacy_xls_fallback,
    spreadsheet_row_text,
)
from .office_word import (  # noqa: F401 (re-export)
    WordMetadata,
    WordPayload,
    WordSectionChunk,
    _body_blocks,
    group_word_sections,
)
from .office_xlsx import (
    process_spreadsheet_binary,
)
from .office_zip import (  # noqa: F401 (re-export)
    _IMAGE_EXTENSIONS,
    _extract_images_from_zip,
    _get_rel_id,
    _local_tag,
)
from .spreadsheet_values import WorkbookStyles, xls_cell_value  # noqa: F401 (re-export)
from .xlsx_stream import iter_rows as xlsx_iter_rows  # noqa: F401 (re-export)
from .xlsx_stream import pick_header  # noqa: F401 (re-export)
from .xlsx_stream import shared_strings as xlsx_shared_strings  # noqa: F401 (re-export)

__all__ = [
    "PresentationMetadata",
    "PresentationPayload",
    "SheetData",
    "SlideData",
    "SpreadsheetMetadata",
    "SpreadsheetPayload",
    "SpreadsheetRowChunk",
    "WordMetadata",
    "WordPayload",
    "WordSectionChunk",
    "process_presentation_binary",
    "process_spreadsheet_binary",
    "process_word_binary",
    "spreadsheet_row_text",
]
