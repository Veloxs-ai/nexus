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

"""Python source through the ast module: classes, functions, signatures, complexity."""

from __future__ import annotations

import ast
import contextlib

from .code_coverage import uncovered_blocks
from .code_model import (
    CodeChunk,
    CodeMetadata,
    CodeProcessingPayload,
    CodeSymbol,
    _first_line,
    _module_chunks,
)


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
            f"Error: {e}\n{code_text}"
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
            # Class-level statements (attributes, fields, constants) outside the methods.
            method_spans = [
                (_first_line(m), getattr(m, "end_lineno", m.lineno))
                for m in node.body
                if isinstance(m, ast.FunctionDef | ast.AsyncFunctionDef)
            ]
            class_lines = lines[cls_s - 1 : cls_e]
            spans = [(1, 1)] + [(a - cls_s + 1, b - cls_s + 1) for a, b in method_spans]
            members = uncovered_blocks(class_lines, spans)
            if members:
                cls_narrative += "Body:\n" + "\n".join(text for _s, _e, text in members) + "\n"

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
                    body_text=cls_body,
                    narrative_text=cls_narrative,
                    metadata={"bases": bases, "methods": method_names},
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
        narrative += code_text

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
            )
        )

    else:
        # Module-level code between the symbols (imports, constants, script statements).
        spans = [
            (_first_line(n), getattr(n, "end_lineno", n.lineno))
            for n in tree.body
            if isinstance(n, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef)
        ]
        chunks.extend(_module_chunks(lines, spans, file_name, "python"))

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
