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

"""Source code payload model shared by the Python, polyglot and OpenAPI processors."""

from __future__ import annotations

import ast
from dataclasses import dataclass, field
from typing import Any

from .code_coverage import uncovered_blocks


@dataclass
class CodeSymbol:
    """Represents a discovered symbol (function, method, class, interface, model)."""

    name: str
    symbol_type: str  # function, async_function, class, method, endpoint, schema
    language: str
    signature: str
    start_line: int
    end_line: int
    docstring: str = ""
    parameters: list[str] = field(default_factory=list)
    return_type: str = ""
    decorators: list[str] = field(default_factory=list)
    complexity_score: int = 1
    parent_scope: str = ""


@dataclass
class CodeChunk:
    """A grounded code or API specification chunk for semantic retrieval."""

    chunk_id: str
    symbol_name: str
    symbol_type: str
    language: str
    file_name: str
    start_line: int
    end_line: int
    signature: str
    docstring: str
    body_text: str
    narrative_text: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class CodeMetadata:
    """Metadata summary of processed source code or API spec."""

    file_name: str
    language: str
    format: str  # "python_ast", "polyglot_source", "openapi_spec"
    total_lines: int
    total_symbols: int
    total_functions: int
    total_classes: int
    total_endpoints: int = 0
    imports: list[str] = field(default_factory=list)


@dataclass
class CodeProcessingPayload:
    """Container for processed source code and OpenAPI specification output."""

    metadata: CodeMetadata
    chunks: list[CodeChunk]
    symbols: list[CodeSymbol]


def _first_line(node: ast.AST) -> int:
    """First source line of a definition, decorators included."""
    decorators = getattr(node, "decorator_list", None) or []
    return min([node.lineno, *(d.lineno for d in decorators)])


def _module_chunks(
    lines: list[str], spans: list[tuple[int, int]], file_name: str, language: str
) -> list[CodeChunk]:
    chunks: list[CodeChunk] = []
    for start, end, text in uncovered_blocks(lines, spans):
        chunks.append(
            CodeChunk(
                chunk_id=f"{file_name}_module_{start}",
                symbol_name=file_name,
                symbol_type="module",
                language=language,
                file_name=file_name,
                start_line=start,
                end_line=end,
                signature=f"module {file_name}",
                docstring="",
                body_text=text,
                narrative_text=(
                    f"[Code AST: {file_name} | Module-level code | Lines: {start}-{end}]\n{text}"
                ),
                metadata={"language": language},
            )
        )
    return chunks
