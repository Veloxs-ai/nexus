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
OpenAPI paths, operations, schemas, and projects them into 3072-dimensional
normalized vector space.
"""

from __future__ import annotations

import ast
import contextlib
import hashlib
import json
import math
import os
import re
from dataclasses import dataclass, field
from typing import Any

EMBEDDING_DIM = 3072


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
    embedding: list[float] = field(default_factory=list)


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


def _compute_l2_norm(vec: list[float]) -> list[float]:
    """Computes IEEE 754 L2 unit normalization."""
    sq_sum = sum(x * x for x in vec)
    if sq_sum <= 1e-12:
        val = 1.0 / math.sqrt(EMBEDDING_DIM)
        return [val] * EMBEDDING_DIM
    inv_norm = 1.0 / math.sqrt(sq_sum)
    return [x * inv_norm for x in vec]


def project_code_vector(
    symbol_name: str,
    symbol_type: str,
    language: str,
    signature: str,
    docstring: str,
    code_body: str,
    complexity: int,
    param_count: int,
) -> list[float]:
    """Projects AST structural tokens, signatures, and metrics into a normalized 3072D vector."""
    dim = EMBEDDING_DIM
    vec = [0.0] * dim

    # 1. Structural semantic hash distributions
    for token, weight in [
        (symbol_name, 3.0),
        (symbol_type, 2.0),
        (language, 2.5),
        (signature, 2.0),
        (docstring, 1.5),
        (code_body[:500], 1.0),
    ]:
        if not token:
            continue
        h = hashlib.sha256(token.encode("utf-8")).digest()
        for i in range(0, len(h), 2):
            idx = int.from_bytes(h[i : i + 2], "big") % dim
            val = ((h[i] / 255.0) * 2.0 - 1.0) * weight
            vec[idx] += val

    # 2. Syntactic and lexical complexity metrics (first 64 dimensions)
    vec[0] += math.log1p(max(0, complexity))
    vec[1] += math.log1p(max(0, param_count))
    vec[2] += math.log1p(len(code_body.splitlines()))
    vec[3] += 1.0 if "async" in symbol_type else 0.0
    vec[4] += 1.0 if symbol_type == "class" else 0.0
    vec[5] += 1.0 if symbol_type in ("function", "method") else 0.0
    vec[6] += 1.0 if symbol_type == "endpoint" else 0.0
    vec[7] += 1.0 if symbol_type == "schema" else 0.0

    # 3. Frequency profile of code keywords (64..256 dimensions)
    keywords = [
        "return",
        "if",
        "else",
        "for",
        "while",
        "try",
        "except",
        "catch",
        "class",
        "def",
        "func",
        "fn",
        "import",
        "export",
        "public",
        "private",
        "async",
        "await",
        "yield",
        "const",
        "let",
        "var",
        "struct",
        "interface",
        "type",
        "match",
        "case",
        "throw",
        "raise",
        "lambda",
        "get",
        "post",
        "put",
        "delete",
    ]
    code_lower = code_body.lower()
    for k_idx, kw in enumerate(keywords):
        target_idx = 64 + k_idx
        count = code_lower.count(kw)
        vec[target_idx] += math.log1p(count)

    # 4. Harmonize remaining dimensions via deterministic seed
    seed_str = f"{language}:{symbol_name}:{signature}:{len(code_body)}"
    seed_hash = hashlib.sha512(seed_str.encode("utf-8")).digest()
    for i in range(256, dim):
        byte_val = seed_hash[(i * 7) % len(seed_hash)]
        vec[i] += ((byte_val / 255.0) * 2.0 - 1.0) * 0.1

    return _compute_l2_norm(vec)


def _format_py_arg(arg: ast.arg) -> str:
    """Formats a Python AST argument with type annotation if present."""
    name = arg.arg
    if arg.annotation:
        with contextlib.suppress(Exception):
            name += f": {ast.unparse(arg.annotation)}"
    return name


def _extract_py_signature(node: ast.FunctionDef | ast.AsyncFunctionDef) -> str:
    """Constructs readable function signature with args and return annotation."""
    prefix = "async def " if isinstance(node, ast.AsyncFunctionDef) else "def "
    args_list: list[str] = []

    # Positional only args (Python 3.8+)
    if getattr(node.args, "posonlyargs", None):
        for a in node.args.posonlyargs:
            args_list.append(_format_py_arg(a))
        args_list.append("/")

    for a in node.args.args:
        args_list.append(_format_py_arg(a))

    if node.args.vararg:
        args_list.append(f"*{_format_py_arg(node.args.vararg)}")

    for a in node.args.kwonlyargs:
        args_list.append(_format_py_arg(a))

    if node.args.kwarg:
        args_list.append(f"**{_format_py_arg(node.args.kwarg)}")

    sig = f"{prefix}{node.name}({', '.join(args_list)})"
    if node.returns:
        with contextlib.suppress(Exception):
            sig += f" -> {ast.unparse(node.returns)}"
    return sig


def _calc_py_complexity(node: ast.AST) -> int:
    """Calculates cyclomatic branching complexity score for an AST node."""
    branches = 1
    for child in ast.walk(node):
        if isinstance(
            child,
            ast.If
            | ast.For
            | ast.AsyncFor
            | ast.While
            | ast.Try
            | ast.ExceptHandler
            | ast.With
            | ast.AsyncWith
            | ast.Assert,
        ):
            branches += 1
        elif isinstance(child, ast.BoolOp):
            branches += len(child.values) - 1
    return branches


def process_python_source(
    code_text: str,
    file_name: str = "source.py",
) -> CodeProcessingPayload:
    """Parses Python source code using standard library ast, extracting symbols and chunks."""
    lines = code_text.splitlines()
    total_lines = len(lines)

    symbols: list[CodeSymbol] = []
    chunks: list[CodeChunk] = []
    imports: list[str] = []

    try:
        tree = ast.parse(code_text, filename=file_name)
    except SyntaxError as e:
        # Fallback to plain chunking when unparseable snippet provided
        narrative = (
            f"[Code AST: {file_name} | Snippet (Unparsed) | Lines: 1-{total_lines}]\n"
            f"Error: {e}\n{code_text[:500]}"
        )
        vec = project_code_vector(
            symbol_name=file_name,
            symbol_type="snippet",
            language="python",
            signature="",
            docstring="",
            code_body=code_text,
            complexity=1,
            param_count=0,
        )
        c = CodeChunk(
            chunk_id=f"{file_name}_snippet",
            symbol_name=file_name,
            symbol_type="snippet",
            language="python",
            file_name=file_name,
            start_line=1,
            end_line=total_lines,
            signature="",
            docstring="",
            body_text=code_text,
            narrative_text=narrative,
            embedding=vec,
        )
        meta = CodeMetadata(
            file_name=file_name,
            language="python",
            format="python_ast",
            total_lines=total_lines,
            total_symbols=0,
            total_functions=0,
            total_classes=0,
        )
        return CodeProcessingPayload(metadata=meta, chunks=[c], symbols=[])

    # Extract imports
    for node in tree.body:
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            for alias in node.names:
                imports.append(f"{mod}.{alias.name}" if mod else alias.name)

    total_funcs = 0
    total_classes = 0

    def handle_function(
        fn_node: ast.FunctionDef | ast.AsyncFunctionDef, parent_class: str = ""
    ) -> None:
        nonlocal total_funcs
        total_funcs += 1
        fn_name = f"{parent_class}.{fn_node.name}" if parent_class else fn_node.name
        sym_type = (
            "method"
            if parent_class
            else ("async_function" if isinstance(fn_node, ast.AsyncFunctionDef) else "function")
        )
        sig = _extract_py_signature(fn_node)
        doc = ast.get_docstring(fn_node) or ""
        s_line = fn_node.lineno
        e_line = getattr(fn_node, "end_lineno", s_line)
        fn_lines = lines[s_line - 1 : e_line]
        body = "\n".join(fn_lines)
        complexity = _calc_py_complexity(fn_node)
        params = [a.arg for a in fn_node.args.args]
        decorators = [
            ast.unparse(d) if hasattr(ast, "unparse") else getattr(d, "id", "decorator")
            for d in fn_node.decorator_list
        ]

        ret_type = ""
        if fn_node.returns:
            with contextlib.suppress(Exception):
                ret_type = ast.unparse(fn_node.returns)

        sym = CodeSymbol(
            name=fn_name,
            symbol_type=sym_type,
            language="python",
            signature=sig,
            start_line=s_line,
            end_line=e_line,
            docstring=doc,
            parameters=params,
            return_type=ret_type,
            decorators=decorators,
            complexity_score=complexity,
            parent_scope=parent_class,
        )
        symbols.append(sym)

        narrative = (
            f"[Code AST: {file_name} | {sym_type.capitalize()}: {fn_name} "
            f"| Lines: {s_line}-{e_line}]\n"
            f"Signature: {sig}\n"
        )
        if doc:
            narrative += f'"""{doc}"""\n'
        narrative += body

        vec = project_code_vector(
            symbol_name=fn_name,
            symbol_type=sym_type,
            language="python",
            signature=sig,
            docstring=doc,
            code_body=body,
            complexity=complexity,
            param_count=len(params),
        )

        chunks.append(
            CodeChunk(
                chunk_id=f"{file_name}_{fn_name}_{s_line}",
                symbol_name=fn_name,
                symbol_type=sym_type,
                language="python",
                file_name=file_name,
                start_line=s_line,
                end_line=e_line,
                signature=sig,
                docstring=doc,
                body_text=body,
                narrative_text=narrative,
                metadata={
                    "complexity": complexity,
                    "decorators": decorators,
                    "parameters": params,
                    "parent_class": parent_class,
                },
                embedding=vec,
            )
        )

    for node in tree.body:
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            handle_function(node)
        elif isinstance(node, ast.ClassDef):
            total_classes += 1
            cls_name = node.name
            bases = [
                ast.unparse(b) if hasattr(ast, "unparse") else getattr(b, "id", "")
                for b in node.bases
            ]
            cls_sig = f"class {cls_name}({', '.join(bases)})" if bases else f"class {cls_name}"
            cls_doc = ast.get_docstring(node) or ""
            cls_s = node.lineno
            cls_e = getattr(node, "end_lineno", cls_s)
            cls_body = "\n".join(lines[cls_s - 1 : cls_e])

            # Class symbol
            symbols.append(
                CodeSymbol(
                    name=cls_name,
                    symbol_type="class",
                    language="python",
                    signature=cls_sig,
                    start_line=cls_s,
                    end_line=cls_e,
                    docstring=cls_doc,
                    complexity_score=len(node.body),
                )
            )

            # Class overview chunk
            cls_narrative = (
                f"[Code AST: {file_name} | Class: {cls_name} | Lines: {cls_s}-{cls_e}]\n"
                f"Signature: {cls_sig}\n"
            )
            if cls_doc:
                cls_narrative += f'"""{cls_doc}"""\n'

            method_names = [
                m.name for m in node.body if isinstance(m, ast.FunctionDef | ast.AsyncFunctionDef)
            ]
            if method_names:
                cls_narrative += f"Methods: {', '.join(method_names)}\n"

            cls_vec = project_code_vector(
                symbol_name=cls_name,
                symbol_type="class",
                language="python",
                signature=cls_sig,
                docstring=cls_doc,
                code_body=cls_body[:1000],
                complexity=len(node.body),
                param_count=len(bases),
            )

            chunks.append(
                CodeChunk(
                    chunk_id=f"{file_name}_{cls_name}_{cls_s}",
                    symbol_name=cls_name,
                    symbol_type="class",
                    language="python",
                    file_name=file_name,
                    start_line=cls_s,
                    end_line=cls_e,
                    signature=cls_sig,
                    docstring=cls_doc,
                    body_text=cls_body[:2000],
                    narrative_text=cls_narrative,
                    metadata={"bases": bases, "methods": method_names},
                    embedding=cls_vec,
                )
            )

            # Process nested methods
            for item in node.body:
                if isinstance(item, ast.FunctionDef | ast.AsyncFunctionDef):
                    handle_function(item, parent_class=cls_name)

    # If no functions or classes found (e.g. script), create module-level chunk
    if not chunks:
        doc = ast.get_docstring(tree) or ""
        narrative = (
            f"[Code AST: {file_name} | Module | Lines: 1-{total_lines}]\n"
            f"Imports: {', '.join(imports)}\n"
        )
        if doc:
            narrative += f'"""{doc}"""\n'
        narrative += code_text[:2000]

        vec = project_code_vector(
            symbol_name=file_name,
            symbol_type="module",
            language="python",
            signature=f"module {file_name}",
            docstring=doc,
            code_body=code_text,
            complexity=len(imports),
            param_count=0,
        )
        chunks.append(
            CodeChunk(
                chunk_id=f"{file_name}_module_1",
                symbol_name=file_name,
                symbol_type="module",
                language="python",
                file_name=file_name,
                start_line=1,
                end_line=total_lines,
                signature=f"module {file_name}",
                docstring=doc,
                body_text=code_text,
                narrative_text=narrative,
                metadata={"imports": imports},
                embedding=vec,
            )
        )

    metadata = CodeMetadata(
        file_name=file_name,
        language="python",
        format="python_ast",
        total_lines=total_lines,
        total_symbols=len(symbols),
        total_functions=total_funcs,
        total_classes=total_classes,
        imports=imports,
    )

    return CodeProcessingPayload(metadata=metadata, chunks=chunks, symbols=symbols)


POLYGLOT_EXTENSIONS = {
    ".js": "javascript",
    ".jsx": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".go": "go",
    ".rs": "rust",
    ".java": "java",
    ".cpp": "cpp",
    ".c": "c",
    ".h": "c",
    ".hpp": "cpp",
    ".cs": "csharp",
    ".rb": "ruby",
    ".php": "php",
    ".swift": "swift",
    ".kt": "kotlin",
}


def process_polyglot_source(
    code_text: str,
    file_name: str,
    language: str | None = None,
) -> CodeProcessingPayload:
    """Parses non-Python source code into grounded code chunks."""
    ext = os.path.splitext(file_name)[1].lower()
    if language:
        norm_key = f".{language.lstrip('.')}"
        lang = POLYGLOT_EXTENSIONS.get(norm_key, language)
    else:
        lang = POLYGLOT_EXTENSIONS.get(ext, "polyglot")
    lines = code_text.splitlines()
    total_lines = len(lines)

    symbols: list[CodeSymbol] = []
    chunks: list[CodeChunk] = []

    # Regex patterns for polyglot definition signatures
    patterns = [
        # TypeScript / JavaScript function or class / interface
        r"^(?:\s*(?:export\s+)?(?:default\s+)?(?:async\s+)?function\s+([A-Za-z0-9_$]+)\s*\((.*?)\)(?:\s*:\s*[^{]+)?)\s*\{",
        r"^(?:\s*(?:export\s+)?(?:abstract\s+)?class\s+([A-Za-z0-9_$]+)(?:<[^>]+>)?(?:\s+extends\s+[^{]+)?(?:\s+implements\s+[^{]+)?)\s*\{",
        r"^(?:\s*(?:export\s+)?interface\s+([A-Za-z0-9_$]+)(?:<[^>]+>)?(?:\s+extends\s+[^{]+)?)\s*\{",
        # Go func / type struct
        r"^(?:\s*func\s+(?:\([^)]+\)\s+)?([A-Za-z0-9_]+)\s*\((.*?)\)(?:\s*[^{]+)?)\s*\{",
        r"^(?:\s*type\s+([A-Za-z0-9_]+)\s+struct)\s*\{",
        # Rust fn / struct / impl
        r"^(?:\s*(?:pub\s+)?(?:async\s+)?fn\s+([A-Za-z0-9_]+)\s*(?:<[^>]+>)?\s*\((.*?)\)(?:\s*->\s*[^{]+)?)\s*\{",
        r"^(?:\s*(?:pub\s+)?struct\s+([A-Za-z0-9_]+)(?:<[^>]+>)?)\s*\{",
        r"^(?:\s*impl(?:<[^>]+>)?\s+([A-Za-z0-9_]+))\s*\{",
        # Java / C# / C++ methods and classes
        r"^(?:\s*(?:public|protected|private|static|final|abstract|async|\s)+\s*(?:class|interface)\s+([A-Za-z0-9_]+))\s*\{",
        r"^(?:\s*(?:public|protected|private|static|final|async|\s)+\s+[A-Za-z0-9_<>,\[\]]+\s+([A-Za-z0-9_]+)\s*\((.*?)\)(?:\s*throws\s+[^{]+)?)\s*\{",
    ]
    compiled_patterns = [re.compile(p) for p in patterns]

    total_funcs = 0
    total_classes = 0

    i = 0
    while i < total_lines:
        line = lines[i]
        matched_name = None
        matched_sig = None
        matched_type = "function"

        for _p_idx, pat in enumerate(compiled_patterns):
            m = pat.match(line)
            if m:
                matched_name = m.group(1)
                matched_sig = line.strip().rstrip("{").strip()
                if "class" in line or "struct" in line or "impl" in line:
                    matched_type = "class"
                    total_classes += 1
                elif "interface" in line:
                    matched_type = "interface"
                    total_classes += 1
                else:
                    matched_type = "function"
                    total_funcs += 1
                break

        if matched_name and matched_sig:
            start_line = i + 1
            # Find closing brace by tracking balance
            brace_count = line.count("{") - line.count("}")
            end_line = start_line
            j = i + 1
            while j < total_lines and brace_count > 0:
                brace_count += lines[j].count("{") - lines[j].count("}")
                end_line = j + 1
                j += 1
                if brace_count <= 0:
                    break

            body_slice = "\n".join(lines[start_line - 1 : end_line])

            # Extract leading doc comments (lines before start_line)
            doc_lines: list[str] = []
            d_idx = start_line - 2
            while d_idx >= 0:
                prev = lines[d_idx].strip()
                if prev.startswith(("//", "/*", "*", "///", "#")):
                    doc_lines.insert(0, prev)
                    d_idx -= 1
                else:
                    break
            docstring = "\n".join(doc_lines)

            sym = CodeSymbol(
                name=matched_name,
                symbol_type=matched_type,
                language=lang,
                signature=matched_sig,
                start_line=start_line,
                end_line=end_line,
                docstring=docstring,
            )
            symbols.append(sym)

            narrative = (
                f"[Code AST: {file_name} | {matched_type.capitalize()}: {matched_name} "
                f"| Lines: {start_line}-{end_line}]\n"
                f"Language: {lang} | Signature: {matched_sig}\n"
            )
            if docstring:
                narrative += f"{docstring}\n"
            narrative += body_slice

            vec = project_code_vector(
                symbol_name=matched_name,
                symbol_type=matched_type,
                language=lang,
                signature=matched_sig,
                docstring=docstring,
                code_body=body_slice,
                complexity=max(1, end_line - start_line),
                param_count=matched_sig.count(","),
            )

            chunks.append(
                CodeChunk(
                    chunk_id=f"{file_name}_{matched_name}_{start_line}",
                    symbol_name=matched_name,
                    symbol_type=matched_type,
                    language=lang,
                    file_name=file_name,
                    start_line=start_line,
                    end_line=end_line,
                    signature=matched_sig,
                    docstring=docstring,
                    body_text=body_slice,
                    narrative_text=narrative,
                    metadata={"language": lang},
                    embedding=vec,
                )
            )
            i = end_line
        else:
            i += 1

    # Fallback to windowed code chunks if no symbols identified
    if not chunks:
        window_size = 50
        for w_start in range(0, total_lines, window_size):
            w_end = min(total_lines, w_start + window_size)
            snippet = "\n".join(lines[w_start:w_end])
            narrative = (
                f"[Code AST: {file_name} | Snippet | Lines: {w_start + 1}-{w_end}]\n"
                f"Language: {lang}\n{snippet}"
            )
            vec = project_code_vector(
                symbol_name=f"{file_name}_L{w_start + 1}",
                symbol_type="snippet",
                language=lang,
                signature=f"lines {w_start + 1}-{w_end}",
                docstring="",
                code_body=snippet,
                complexity=1,
                param_count=0,
            )
            chunks.append(
                CodeChunk(
                    chunk_id=f"{file_name}_window_{w_start + 1}",
                    symbol_name=f"{file_name}_lines_{w_start + 1}",
                    symbol_type="snippet",
                    language=lang,
                    file_name=file_name,
                    start_line=w_start + 1,
                    end_line=w_end,
                    signature="",
                    docstring="",
                    body_text=snippet,
                    narrative_text=narrative,
                    metadata={"language": lang},
                    embedding=vec,
                )
            )

    meta = CodeMetadata(
        file_name=file_name,
        language=lang,
        format="polyglot_source",
        total_lines=total_lines,
        total_symbols=len(symbols),
        total_functions=total_funcs,
        total_classes=total_classes,
    )
    return CodeProcessingPayload(metadata=meta, chunks=chunks, symbols=symbols)


def process_openapi_spec(
    spec_data: str | dict[str, Any],
    file_name: str = "openapi.json",
) -> CodeProcessingPayload:
    """Parses OpenAPI 3.0 / 3.1 or Swagger 2.0 specifications into semantic chunks."""
    if isinstance(spec_data, str):
        try:
            doc = json.loads(spec_data)
        except json.JSONDecodeError:
            # Simple line fallback for YAML/invalid JSON
            doc = {"info": {"title": file_name}, "paths": {}}
    elif isinstance(spec_data, dict):
        doc = spec_data
    else:
        raise ValueError("spec_data must be JSON string or parsed dict")

    info = doc.get("info", {})
    api_title = info.get("title", file_name)
    api_version = info.get("version", "1.0.0")

    symbols: list[CodeSymbol] = []
    chunks: list[CodeChunk] = []

    paths = doc.get("paths", {})
    http_methods = {"get", "post", "put", "delete", "patch", "head", "options", "trace"}

    total_endpoints = 0

    for path_str, path_item in paths.items():
        if not isinstance(path_item, dict):
            continue
        for method, op in path_item.items():
            if method.lower() not in http_methods or not isinstance(op, dict):
                continue

            total_endpoints += 1
            op_id = op.get("operationId") or f"{method.upper()}_{path_str}"
            summary = op.get("summary", "")
            description = op.get("description", "")
            tags = op.get("tags", [])

            # Introspect parameters
            raw_params = op.get("parameters", [])
            param_labels: list[str] = []
            for p in raw_params:
                if isinstance(p, dict):
                    p_name = p.get("name", "")
                    p_in = p.get("in", "query")
                    p_req = "required" if p.get("required") else "optional"
                    p_type = p.get("schema", {}).get("type", "string")
                    param_labels.append(f"{p_name} ({p_in}, {p_type}, {p_req})")

            # Introspect requestBody
            req_body_label = ""
            rb = op.get("requestBody")
            if isinstance(rb, dict):
                content = rb.get("content", {})
                req_types = list(content.keys())
                req_body_label = f"Body: {', '.join(req_types)}"

            # Introspect responses
            responses = op.get("responses", {})
            resp_labels: list[str] = []
            for code, r_data in responses.items():
                if isinstance(r_data, dict):
                    r_desc = r_data.get("description", "")
                    resp_labels.append(f"{code}: {r_desc}")

            sig = f"{method.upper()} {path_str}"

            narrative = (
                f"[OpenAPI: {api_title} v{api_version} | Operation: {op_id} | {sig}]\n"
                f"Summary: {summary}\n"
            )
            if description:
                narrative += f"Description: {description}\n"
            if tags:
                narrative += f"Tags: {', '.join(tags)}\n"
            if param_labels:
                narrative += f"Parameters: {', '.join(param_labels)}\n"
            if req_body_label:
                narrative += f"{req_body_label}\n"
            if resp_labels:
                narrative += f"Responses: {', '.join(resp_labels)}\n"

            body_json = json.dumps(op, indent=2)

            sym = CodeSymbol(
                name=op_id,
                symbol_type="endpoint",
                language="openapi",
                signature=sig,
                start_line=1,
                end_line=1,
                docstring=summary or description,
                parameters=param_labels,
            )
            symbols.append(sym)

            vec = project_code_vector(
                symbol_name=op_id,
                symbol_type="endpoint",
                language="openapi",
                signature=sig,
                docstring=summary + " " + description,
                code_body=narrative,
                complexity=len(param_labels) + len(resp_labels),
                param_count=len(param_labels),
            )

            chunks.append(
                CodeChunk(
                    chunk_id=f"{api_title}_{op_id}",
                    symbol_name=op_id,
                    symbol_type="endpoint",
                    language="openapi",
                    file_name=file_name,
                    start_line=1,
                    end_line=1,
                    signature=sig,
                    docstring=summary or description,
                    body_text=body_json,
                    narrative_text=narrative,
                    metadata={
                        "path": path_str,
                        "method": method.upper(),
                        "tags": tags,
                        "operation_id": op_id,
                    },
                    embedding=vec,
                )
            )

    # Introspect schemas (OpenAPI 3 components.schemas or Swagger 2 definitions)
    schemas = doc.get("components", {}).get("schemas", {}) or doc.get("definitions", {})
    total_schemas = 0
    if isinstance(schemas, dict):
        for s_name, s_def in schemas.items():
            if not isinstance(s_def, dict):
                continue
            total_schemas += 1
            s_type = s_def.get("type", "object")
            props = s_def.get("properties", {})
            req_fields = s_def.get("required", [])

            prop_summaries: list[str] = []
            for p_name, p_schema in props.items():
                if isinstance(p_schema, dict):
                    ptype = p_schema.get("type", "any")
                    req_mark = " (required)" if p_name in req_fields else ""
                    prop_summaries.append(f"{p_name}: {ptype}{req_mark}")

            s_sig = f"model {s_name} ({s_type})"
            s_desc = s_def.get("description", "")
            narrative = f"[OpenAPI: {api_title} | Model Schema: {s_name}]\nType: {s_type}\n"
            if s_desc:
                narrative += f"Description: {s_desc}\n"
            if prop_summaries:
                narrative += f"Properties: {', '.join(prop_summaries)}\n"

            sym = CodeSymbol(
                name=s_name,
                symbol_type="schema",
                language="openapi",
                signature=s_sig,
                start_line=1,
                end_line=1,
                docstring=s_desc,
            )
            symbols.append(sym)

            vec = project_code_vector(
                symbol_name=s_name,
                symbol_type="schema",
                language="openapi",
                signature=s_sig,
                docstring=s_desc,
                code_body=narrative,
                complexity=len(prop_summaries),
                param_count=len(req_fields),
            )

            chunks.append(
                CodeChunk(
                    chunk_id=f"{api_title}_schema_{s_name}",
                    symbol_name=s_name,
                    symbol_type="schema",
                    language="openapi",
                    file_name=file_name,
                    start_line=1,
                    end_line=1,
                    signature=s_sig,
                    docstring=s_desc,
                    body_text=json.dumps(s_def, indent=2),
                    narrative_text=narrative,
                    metadata={"model_name": s_name, "required": req_fields},
                    embedding=vec,
                )
            )

    meta = CodeMetadata(
        file_name=file_name,
        language="openapi",
        format="openapi_spec",
        total_lines=len(json.dumps(doc, indent=2).splitlines()),
        total_symbols=len(symbols),
        total_functions=total_endpoints,
        total_classes=total_schemas,
        total_endpoints=total_endpoints,
    )
    return CodeProcessingPayload(metadata=meta, chunks=chunks, symbols=symbols)


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
    if ext == ".py" or (not ext and (language == "python" or "def " in text or "import " in text)):
        return process_python_source(text, file_name=file_name)

    # Detect Polyglot
    return process_polyglot_source(text, file_name=file_name, language=language)
