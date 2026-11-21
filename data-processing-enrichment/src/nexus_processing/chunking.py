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

from __future__ import annotations

import csv
import io
import json
import re

from .json_table import compact_json


def pack_rows(rows: list[str], header: str = "", max_chars: int = 1500) -> list[str]:
    """Pack consecutive row narratives into row-group chunks.

    One-row-per-chunk floods top-k retrieval with near-identical fragments and
    wastes one vector per ~80 characters. Row groups keep rows verbatim, repeat
    the column header in every group so each chunk is self-describing, and stay
    well inside embedding-model context limits.
    """
    chunks: list[str] = []
    prefix = f"{header}\n" if header else ""
    current: list[str] = []
    size = len(prefix)
    for row in rows:
        row = row.strip()
        if not row:
            continue
        if current and size + len(row) + 1 > max_chars:
            chunks.append(prefix + "\n".join(current))
            current, size = [], len(prefix)
        current.append(row)
        size += len(row) + 1
    if current:
        chunks.append(prefix + "\n".join(current))
    return chunks


def chunk_csv(csv_str: str, max_chars: int = 1500) -> list[str]:
    """Transforms tabular CSV rows into row-group narratives with explicit Row IDs."""
    try:
        clean_input = csv_str.replace("\r\n", "\n").replace("\r", "\n")
        lines = [line for line in clean_input.strip().splitlines() if line.strip()]
        if not lines:
            return []
        start_idx = 0
        for idx, line in enumerate(lines):
            if "," in line:
                start_idx = idx
                break
        clean_csv = "\n".join(lines[start_idx:])
        reader = csv.DictReader(io.StringIO(clean_csv))
        rows: list[str] = []
        for row_idx, row in enumerate(reader, start=1):
            row_items = [
                f"{k.strip()}: {v.strip()}" for k, v in row.items() if k and isinstance(v, str)
            ]
            if row_items:
                rows.append(f"[Row ID: {row_idx}] " + " | ".join(row_items))
        columns = [c.strip() for c in (reader.fieldnames or []) if c]
        header = f"Columns: {', '.join(columns)}" if columns else ""
        chunks = pack_rows(rows, header=header, max_chars=max_chars)
    except Exception:
        chunks = []
    return chunks if chunks else chunk_smart_text(csv_str)


def chunk_json(json_str: str) -> list[str]:
    """Parses structural JSON payloads and extracts discrete object/array records (compact
    JSON). Record arrays inside a document are better read as rows: ``json_table``."""
    try:
        cleaned = json_str.strip()
        if cleaned.startswith("```"):
            cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
            cleaned = re.sub(r"\s*```$", "", cleaned)
        start_arr = cleaned.find("[")
        end_arr = cleaned.rfind("]")
        start_obj = cleaned.find("{")
        end_obj = cleaned.rfind("}")

        if start_arr != -1 and end_arr != -1 and (start_obj == -1 or start_arr < start_obj):
            json_payload = cleaned[start_arr : end_arr + 1]
        elif start_obj != -1 and end_obj != -1:
            json_payload = cleaned[start_obj : end_obj + 1]
        else:
            json_payload = cleaned

        data = json.loads(json_payload)
        chunks: list[str] = []
        # Compact: indent=2 spent ~40% of a chunk's characters (and tokens) on spaces.
        if isinstance(data, list):
            for item in data:
                chunks.append(compact_json(item))
        elif isinstance(data, dict):
            chunks.append(compact_json(data))
        return chunks if chunks else [json_str]
    except Exception:
        return chunk_smart_text(json_str)


def chunk_smart_text(text: str, chunk_size: int = 1000, chunk_overlap: int = 200) -> list[str]:
    """Slice text along paragraph (\n\n) and sentence (. ) boundaries,
    preserving semantic cohesion.

    Linear time: the window advances over one string by index instead of re-slicing the
    remaining text after every chunk (8 MB of text: ~0.1 s instead of ~4.4 s).
    """
    clean_text = text.replace("\r\n", "\n").replace("\r", "\n").strip()
    if not clean_text:
        return []

    chunks: list[str] = []
    n = len(clean_text)
    pos = 0
    floor = chunk_size * 0.4
    while pos < n:
        if n - pos <= chunk_size:
            tail = clean_text[pos:].strip()
            if tail:
                chunks.append(tail)
            break
        limit = pos + chunk_size

        # Priority 1: Double newline (paragraph boundary)
        split_point = clean_text.rfind("\n\n", pos, limit)
        split_point = split_point - pos if split_point != -1 else -1
        # Priority 2: Sentence period followed by space
        if split_point == -1 or split_point < floor:
            found = clean_text.rfind(". ", pos, limit)
            split_point = found - pos + 1 if found != -1 else -1
        # Priority 3: Word space
        if split_point == -1 or split_point < floor:
            found = clean_text.rfind(" ", pos, limit)
            split_point = found - pos if found != -1 else -1
        # Fallback: Hard character cutoff
        if split_point == -1 or split_point < floor:
            split_point = chunk_size

        chunk = clean_text[pos : pos + split_point].strip()
        if chunk:
            chunks.append(chunk)

        next_start = max(0, split_point - chunk_overlap)
        if 0 < next_start < split_point:
            # Start the overlap window on a word boundary, never mid-word.
            boundary = clean_text.find(" ", pos + next_start, pos + split_point)
            if boundary != -1:
                next_start = boundary - pos + 1
        if next_start <= 0:  # an overlap as long as the chunk would never advance
            next_start = split_point
        pos += next_start
        while pos < n and clean_text[pos].isspace():
            pos += 1

    return chunks


_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*#*\s*$")


_TABLE_ROW_RE = re.compile(r"^\s*\|.*\|\s*$")
_TABLE_SEP_RE = re.compile(r"^\s*\|?\s*:?-{3,}:?\s*(?:\|\s*:?-{3,}:?\s*)*\|?\s*$")


def _blocks_with_tables(body: str) -> list[tuple[bool, list[str]]]:
    """``body`` as consecutive ``(is_table, lines)`` blocks; a table is a pipe header row,
    a ``|---|`` separator row and the pipe rows that follow."""
    lines = body.split("\n")
    blocks: list[tuple[bool, list[str]]] = []
    text: list[str] = []
    i = 0
    while i < len(lines):
        if (
            i + 1 < len(lines)
            and _TABLE_ROW_RE.match(lines[i])
            and _TABLE_SEP_RE.match(lines[i + 1])
        ):
            end = i + 2
            while end < len(lines) and _TABLE_ROW_RE.match(lines[end]):
                end += 1
            if text:
                blocks.append((False, text))
                text = []
            blocks.append((True, lines[i:end]))
            i = end
            continue
        text.append(lines[i])
        i += 1
    if text:
        blocks.append((False, text))
    return blocks


def split_table(lines: list[str], max_chars: int) -> list[str]:
    """A Markdown table as pieces of at most ``max_chars`` (when rows allow), split only
    between rows; every piece repeats the header and separator rows."""
    header = "\n".join(lines[:2])
    pieces: list[str] = []
    rows: list[str] = []
    size = len(header)
    for row in lines[2:]:
        if rows and size + len(row) + 1 > max_chars:
            pieces.append(header + "\n" + "\n".join(rows))
            rows, size = [], len(header)
        rows.append(row)
        size += len(row) + 1
    if rows or not pieces:
        pieces.append(header + ("\n" + "\n".join(rows) if rows else ""))
    return pieces


def _section_pieces(body: str, budget: int, overlap: int) -> list[str]:
    """Pieces of one Markdown section; a table that has to be split keeps its header on
    every piece (sections without an oversized table are cut by ``chunk_smart_text``)."""
    blocks = _blocks_with_tables(body) if len(body) > budget else []
    if not any(is_table for is_table, _ in blocks):
        return chunk_smart_text(body, chunk_size=budget, chunk_overlap=overlap)
    pieces: list[str] = []
    for is_table, lines in blocks:
        block = "\n".join(lines).strip()
        if not block:
            continue
        if not is_table:
            pieces.extend(chunk_smart_text(block, chunk_size=budget, chunk_overlap=overlap))
        elif len(block) <= budget:
            pieces.append(block)
        else:
            pieces.extend(split_table([ln.strip() for ln in lines], budget))
    merged: list[str] = []
    for piece in pieces:  # keep short neighbours together (a caption with its table)
        if merged and len(merged[-1]) + 2 + len(piece) <= budget:
            merged[-1] = f"{merged[-1]}\n\n{piece}"
        else:
            merged.append(piece)
    return merged


def chunk_markdown(text: str, chunk_size: int = 1000, chunk_overlap: int = 150) -> list[str]:
    """Heading-aware chunking for Markdown / structured text.

    Splits on headings first so a chunk never straddles two sections, then
    applies paragraph/sentence-aware sizing inside long sections. Every chunk
    is prefixed with its heading breadcrumb (``Section: A > B``) so that it is
    self-describing for both the embedding model and the LLM - retrieving
    "3. Refund window" out of context otherwise loses which policy it belongs to.
    """
    clean_text = text.replace("\r\n", "\n").replace("\r", "\n").strip()
    if not clean_text:
        return []
    lines = clean_text.split("\n")
    if not any(_HEADING_RE.match(line) for line in lines):
        return chunk_smart_text(clean_text, chunk_size=chunk_size, chunk_overlap=chunk_overlap)

    sections: list[tuple[list[str], str]] = []
    path: list[tuple[int, str]] = []
    buf: list[str] = []
    in_code = False

    def flush() -> None:
        body = "\n".join(buf).strip()
        if body:
            sections.append(([t for _, t in path], body))
        buf.clear()

    for line in lines:
        if line.strip().startswith("```"):
            in_code = not in_code
        match = None if in_code else _HEADING_RE.match(line)
        if match:
            flush()
            level = len(match.group(1))
            path = [(lvl, t) for lvl, t in path if lvl < level]
            path.append((level, match.group(2).strip()))
            buf.append(line)
        else:
            buf.append(line)
    flush()

    chunks: list[str] = []
    for heading_path, body in sections:
        crumb = " > ".join(heading_path)
        prefix = f"Section: {crumb}\n" if crumb else ""
        budget = max(200, chunk_size - len(prefix))
        # Heading-only sections are merged into the next chunk via the breadcrumb.
        if len(body.split("\n")) == 1 and _HEADING_RE.match(body):
            continue
        for piece in _section_pieces(body, budget, chunk_overlap):
            chunks.append(prefix + piece)
    return chunks or chunk_smart_text(clean_text, chunk_size=chunk_size, chunk_overlap=chunk_overlap)


def chunk_words(text: str, max_tokens: int, overlap_tokens: int) -> list[str]:
    """Word-based sliding window chunking with preserved token overlap."""
    tokens = text.split()
    if not tokens:
        return []
    if len(tokens) <= max_tokens:
        return [" ".join(tokens)]

    chunks: list[str] = []
    start = 0
    step = max_tokens - overlap_tokens
    if step <= 0:
        step = 1

    while start < len(tokens):
        end = min(start + max_tokens, len(tokens))
        chunks.append(" ".join(tokens[start:end]))
        if end == len(tokens):
            break
        start += step
    return chunks


def chunk_text(text: str, max_tokens: int = 1000, overlap_tokens: int = 200) -> list[str]:
    """Universal format-aware chunking router.

    Automatically detects CSV, JSON, and document text to apply optimal chunking strategy.
    """
    stripped = text.strip()
    if not stripped:
        return []

    # Detect JSON
    if (stripped.startswith("{") and stripped.endswith("}")) or (
        stripped.startswith("[") and stripped.endswith("]")
    ):
        try:
            json.loads(stripped)
            return chunk_json(stripped)
        except Exception:
            pass

    # Detect CSV (has commas, newlines, and consistent columns)
    lines = [line for line in stripped.splitlines() if line.strip()]
    if len(lines) >= 2 and all("," in line for line in lines[:5]):
        try:
            reader = list(csv.reader(lines[:5]))
            if (
                len(reader) >= 2
                and len(reader[0]) > 1
                and all(len(r) == len(reader[0]) for r in reader)
            ):
                return chunk_csv(stripped)
        except Exception:
            pass

    # Standard word-based chunking with overlap
    return chunk_words(text, max_tokens=max_tokens, overlap_tokens=overlap_tokens)
