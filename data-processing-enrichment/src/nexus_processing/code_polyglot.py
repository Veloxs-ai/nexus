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

"""Other languages (JavaScript, TypeScript, Go, Rust, Java, C-family, ...) by signature patterns
and brace matching."""

from __future__ import annotations

import os
import re

from .code_model import CodeChunk, CodeMetadata, CodeProcessingPayload, CodeSymbol, _module_chunks

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


def _strip_strings_and_comments(line: str) -> str:
    """Remove string literals and single-line comments for accurate brace counting."""
    # Remove single-line comments (// style)
    line = re.sub(r"//.*$", "", line)
    # Remove double-quoted string contents
    line = re.sub(r'"(?:[^"\\]|\\.)*"', '""', line)
    # Remove single-quoted string contents
    line = re.sub(r"'(?:[^'\\]|\\.)*'", "''", line)
    # Remove backtick template literal contents
    line = re.sub(r"`(?:[^`\\]|\\.)*`", "``", line)
    return line


_MODIFIERS = r"(?:public|protected|private|static|final|abstract|async)"


_JAVA_MODIFIERS = r"(?:public|protected|private|static|final|async)"


# Polyglot definition signatures, compiled once. The Java/C# modifier prefixes match the
# same lines as ``(?:mods|\s)+`` but without the overlap between the modifier list and
# ``\s`` that made a long run of spaces backtrack quadratically (ReDoS).
_POLYGLOT_PATTERNS = [
    re.compile(p)
    for p in (
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
        rf"^(?:(?:(?:\s*{_MODIFIERS})+\s*|\s+)(?:class|interface)\s+([A-Za-z0-9_]+))\s*\{{",
        rf"^(?:(?:(?:\s*{_JAVA_MODIFIERS})+\s+|\s\s+)[A-Za-z0-9_<>,\[\]]+\s+([A-Za-z0-9_]+)\s*\((.*?)\)(?:\s*throws\s+[^{{]+)?)\s*\{{",
    )
]


# Members inside a class body: TS/JS methods (no return type before the name) and the
# Java/C#/Rust method shapes above.
_MEMBER_PATTERNS = [
    re.compile(
        r"^\s*(?:(?:public|private|protected|static|readonly|async|override|abstract|get|set)\s+)*"
        r"(?:\*\s*)?([A-Za-z_$][\w$]*)\s*(?:<[^>]*>\s*)?\((.*?)\)(?:\s*:\s*[^{;=]+)?\s*\{"
    ),
    _POLYGLOT_PATTERNS[9],
    _POLYGLOT_PATTERNS[5],
]


_NOT_MEMBERS = frozenset(
    {
        "if", "for", "while", "switch", "catch", "return", "function", "new", "else", "do",
        "try", "with", "typeof", "delete", "await", "yield", "throw", "case", "super", "this",
    }
)  # fmt: skip


MAX_SIGNATURE_LINE = 2000  # longer lines (minified code) are not matched as signatures


def _block_end(lines: list[str], start: int) -> int:
    """1-based last line of the brace block opening on 0-based line ``start``."""
    stripped = _strip_strings_and_comments(lines[start])
    balance = stripped.count("{") - stripped.count("}")
    end = start + 1
    j = start + 1
    while j < len(lines) and balance > 0:
        stripped = _strip_strings_and_comments(lines[j])
        balance += stripped.count("{") - stripped.count("}")
        end = j + 1
        j += 1
    return end


def _leading_doc(lines: list[str], start: int) -> str:
    """Comment lines directly above 0-based line ``start``."""
    doc: list[str] = []
    k = start - 1
    while k >= 0:
        prev = lines[k].strip()
        if not prev.startswith(("//", "/*", "*", "///", "#")):
            break
        doc.insert(0, prev)
        k -= 1
    return "\n".join(doc)


def _class_members(lines: list[str], first: int, last: int) -> list[tuple[str, str, int, int]]:
    """``(name, signature, start, end)`` (1-based lines) of the methods directly inside a
    class body spanning 0-based lines ``first``..``last``."""
    members: list[tuple[str, str, int, int]] = []
    k = first
    while k < last:
        line = lines[k]
        found = None
        if len(line) <= MAX_SIGNATURE_LINE:
            for pattern in _MEMBER_PATTERNS:
                m = pattern.match(line)
                if m and m.group(1) not in _NOT_MEMBERS:
                    found = m.group(1)
                    break
        if found is None:
            k += 1
            continue
        end = min(_block_end(lines, k), last + 1)
        members.append((found, line.strip().rstrip("{").strip(), k + 1, end))
        k = end
    return members


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

    compiled_patterns = _POLYGLOT_PATTERNS

    total_funcs = 0
    total_classes = 0

    i = 0
    while i < total_lines:
        line = lines[i]
        matched_name = None
        matched_sig = None
        matched_type = "function"

        for _p_idx, pat in enumerate(compiled_patterns):
            if len(line) > MAX_SIGNATURE_LINE:
                break
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
            stripped_line = _strip_strings_and_comments(line)
            brace_count = stripped_line.count("{") - stripped_line.count("}")
            end_line = start_line
            j = i + 1
            while j < total_lines and brace_count > 0:
                stripped_j = _strip_strings_and_comments(lines[j])
                brace_count += stripped_j.count("{") - stripped_j.count("}")
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
                )
            )
            if matched_type == "class":  # methods get their own chunks, as in Python
                members = _class_members(lines, start_line, end_line - 1)
                if members:
                    chunks[-1].metadata["methods"] = [name for name, _, _, _ in members]
                for name, signature, m_start, m_end in members:
                    total_funcs += 1
                    qualified = f"{matched_name}.{name}"
                    m_body = "\n".join(lines[m_start - 1 : m_end])
                    m_doc = _leading_doc(lines, m_start - 1)
                    symbols.append(
                        CodeSymbol(
                            name=qualified,
                            symbol_type="method",
                            language=lang,
                            signature=signature,
                            start_line=m_start,
                            end_line=m_end,
                            docstring=m_doc,
                            parent_scope=matched_name,
                        )
                    )
                    m_narrative = (
                        f"[Code AST: {file_name} | Method: {qualified} "
                        f"| Lines: {m_start}-{m_end}]\n"
                        f"Language: {lang} | Signature: {signature}\n"
                        + (f"{m_doc}\n" if m_doc else "")
                        + m_body
                    )
                    chunks.append(
                        CodeChunk(
                            chunk_id=f"{file_name}_{qualified}_{m_start}",
                            symbol_name=qualified,
                            symbol_type="method",
                            language=lang,
                            file_name=file_name,
                            start_line=m_start,
                            end_line=m_end,
                            signature=signature,
                            docstring=m_doc,
                            body_text=m_body,
                            narrative_text=m_narrative,
                            metadata={"language": lang, "parent_class": matched_name},
                        )
                    )
            i = end_line
        else:
            i += 1

    if chunks:  # code outside the matched symbols (imports, constants, statements)
        spans = [(c.start_line, c.end_line) for c in chunks]
        chunks.extend(_module_chunks(lines, spans, file_name, lang))

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
