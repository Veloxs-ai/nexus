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
    """Parses structural JSON payloads and extracts discrete, readable object/array records."""
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
        if isinstance(data, list):
            for item in data:
                chunks.append(json.dumps(item, indent=2))
        elif isinstance(data, dict):
            chunks.append(json.dumps(data, indent=2))
        return chunks if chunks else [json_str]
    except Exception:
        return chunk_smart_text(json_str)


def chunk_smart_text(text: str, chunk_size: int = 1000, chunk_overlap: int = 200) -> list[str]:
    """Slice text along paragraph (\n\n) and sentence (. ) boundaries,
    preserving semantic cohesion.
    """
    clean_text = text.replace("\r\n", "\n").replace("\r", "\n").strip()
    if not clean_text:
        return []

    chunks: list[str] = []
    remaining_text = clean_text

    while len(remaining_text) > 0:
        if len(remaining_text) <= chunk_size:
            if remaining_text.strip():
                chunks.append(remaining_text.strip())
            break

        # Priority 1: Double newline (paragraph boundary)
        split_point = remaining_text.rfind("\n\n", 0, chunk_size)
        # Priority 2: Sentence period followed by space
        if split_point == -1 or split_point < chunk_size * 0.4:
            split_point = remaining_text.rfind(". ", 0, chunk_size)
            if split_point != -1:
                split_point += 1
        # Priority 3: Word space
        if split_point == -1 or split_point < chunk_size * 0.4:
            split_point = remaining_text.rfind(" ", 0, chunk_size)
        # Fallback: Hard character cutoff
        if split_point == -1 or split_point < chunk_size * 0.4:
            split_point = chunk_size

        chunk = remaining_text[:split_point].strip()
        if chunk:
            chunks.append(chunk)

        next_start = max(0, split_point - chunk_overlap)
        if 0 < next_start < split_point:
            # Start the overlap window on a word boundary, never mid-word.
            boundary = remaining_text.find(" ", next_start, split_point)
            if boundary != -1:
                next_start = boundary + 1
        remaining_text = remaining_text[next_start:].strip()

    return chunks


_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*#*\s*$")


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
        for piece in chunk_smart_text(body, chunk_size=budget, chunk_overlap=chunk_overlap):
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
