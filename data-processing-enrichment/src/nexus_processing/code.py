# SPDX-License-Identifier: Apache-2.0
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

"""Pure-Python, zero-dependency Code AST, Polyglot, and OpenAPI Specification Engine.

Extracts syntax tree hierarchies, signatures, docstrings, classes, methods,
OpenAPI paths, operations and schemas into grounded chunks.
"""

from __future__ import annotations

import json
import os
import re
from typing import Any

from .code_coverage import uncovered_blocks  # noqa: F401 (re-export)
from .code_model import (  # noqa: F401 (re-export)
    CodeChunk,
    CodeMetadata,
    CodeProcessingPayload,
    CodeSymbol,
    _first_line,
    _module_chunks,
)
from .code_openapi import (
    process_openapi_spec,
)
from .code_polyglot import (  # noqa: F401 (re-export)
    _JAVA_MODIFIERS,
    _MEMBER_PATTERNS,
    _MODIFIERS,
    _NOT_MEMBERS,
    _POLYGLOT_PATTERNS,
    MAX_SIGNATURE_LINE,
    POLYGLOT_EXTENSIONS,
    _block_end,
    _class_members,
    _leading_doc,
    _strip_strings_and_comments,
    process_polyglot_source,
)
from .code_python import (  # noqa: F401 (re-export)
    _calc_py_complexity,
    _extract_py_signature,
    _format_py_arg,
    process_python_source,
)

_PY_DEF = re.compile(r"^[ \t]*(?:async[ \t]+)?def[ \t]+\w+[ \t]*\(.*\)[^:{;]*:", re.M)
_PY_IMPORT = re.compile(
    r"^(?:from[ \t]+[\w.]+[ \t]+import[ \t]|import[ \t]+[\w.]+(?:[ \t]+as[ \t]+\w+)?[ \t]*$)", re.M
)
_JS_IMPORT = re.compile(r"^import\b.*\bfrom[ \t]+['\"]|^import[ \t]+['\"]", re.M)


def _looks_python(text: str) -> bool:
    """Extensionless source is Python when it has a Python ``def`` or ``import`` line, not
    merely the word ``import`` (``import x from 'y'`` is JavaScript)."""
    if _PY_DEF.search(text):
        return True
    return bool(_PY_IMPORT.search(text)) and not _JS_IMPORT.search(text)


def process_code(
    code_input: str | bytes | dict[str, Any],
    file_name: str = "source.py",
    language: str | None = None,
) -> CodeProcessingPayload:
    """Dispatches code or API spec to the appropriate AST, Polyglot, or OpenAPI processor."""
    if isinstance(code_input, bytes):
        text = code_input.decode("utf-8", errors="replace")
    elif isinstance(code_input, dict):
        return process_openapi_spec(code_input, file_name=file_name)
    else:
        text = str(code_input)

    ext = os.path.splitext(file_name)[1].lower()

    # Detect OpenAPI
    if (
        ext in (".json", ".yaml", ".yml")
        or "openapi" in file_name.lower()
        or "swagger" in file_name.lower()
    ):
        try:
            parsed = json.loads(text)
            if isinstance(parsed, dict) and (
                "openapi" in parsed or "swagger" in parsed or "paths" in parsed
            ):
                return process_openapi_spec(parsed, file_name=file_name)
        except Exception:
            pass

    # Detect Python
    if ext == ".py" or (not ext and (language == "python" or _looks_python(text))):
        return process_python_source(text, file_name=file_name)

    # Detect Polyglot
    return process_polyglot_source(text, file_name=file_name, language=language)
