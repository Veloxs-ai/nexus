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

"""Chunks ready for storage: token-bounded, row-aware, packed, plus a document digest.

``prepare_chunks`` is the last processing step before chunks are embedded and stored,
whatever produced them (a ``NexusClient.process_*`` method, a connector, a CDC stream):

- empty chunks are dropped, and so are metadata keys the caller owns (``drop_keys``);
- a chunk over the token budget is split into header-led parts (``token_budget.fit_text``).
  A table row keeps its source record (``record`` / ``records``) on the **first** part only,
  so one source row is still one record; every part gets ``part`` / ``parts`` and keeps the
  row's ``record_key``, so a record-level delete removes every part;
- runs of tiny row-style chunks (``pack_min_chunks`` or more chunks, median under
  ``pack_median_chars`` characters) are packed into groups of about ``pack_target_tokens``
  tokens; their records go to ``metadata.records`` with ``packed_rows`` and ``row_range``.
  A chunk carrying a ``record_key`` (a live, record-level chunk) is never packed.

``document_digest`` is the text embedded as a document's summary vector: name, type, chunk
count, the section structure every processor records (Markdown breadcrumbs, headings,
sheets, pages, slides) and the opening content.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import Any

from .token_budget import DEFAULT_MAX_TOKENS, estimate_tokens, fit_text

__all__ = ["document_digest", "prepare_chunks", "title_passages"]

TokenCounter = Callable[[str], int]

ROW_KEYS = ("record", "records")


def _clean(text: Any) -> str:
    return str(text or "").replace("\x00", "").strip()


def _split(
    text: str, meta: dict[str, Any], budget: int, count: TokenCounter, row_keys: tuple[str, ...]
) -> list[dict[str, Any]]:
    if len(text) <= budget or count(text) <= budget:
        return [{"text": text, "metadata": meta}]
    parts = [p for p in fit_text(text, budget, count) if p.strip()] or [text]
    if len(parts) == 1:
        return [{"text": parts[0], "metadata": meta}]
    rest = {k: v for k, v in meta.items() if k not in row_keys}
    out = []
    for n, part in enumerate(parts):
        part_meta = dict(meta) if n == 0 else dict(rest)
        part_meta["part"], part_meta["parts"] = n + 1, len(parts)
        out.append({"text": part, "metadata": part_meta})
    return out


def _pack(group: list[dict[str, Any]], row_keys: tuple[str, ...]) -> dict[str, Any]:
    meta = {k: v for k, v in group[0]["metadata"].items() if k not in row_keys}
    meta["packed_rows"] = len(group)
    records: list[dict[str, Any]] = []
    for g in group:
        if isinstance(g["metadata"].get("record"), dict):
            records.append(g["metadata"]["record"])
        records.extend(r for r in g["metadata"].get("records") or [] if isinstance(r, dict))
    if records:
        meta["records"] = records
    first, last = group[0]["metadata"].get("row_index"), group[-1]["metadata"].get("row_index")
    if first is not None:
        meta["row_range"] = [first, last]
        meta.pop("row_index", None)
    return {"text": "\n".join(g["text"] for g in group), "metadata": meta}


def prepare_chunks(
    chunks: Iterable[dict[str, Any]],
    *,
    max_tokens: int | None = None,
    count_tokens: TokenCounter | None = None,
    title: str = "",
    drop_keys: Iterable[str] = ("data",),
    row_keys: tuple[str, ...] = ROW_KEYS,
    keep_whole_key: str = "record_key",
    pack_min_chunks: int = 20,
    pack_median_chars: int = 300,
    pack_target_tokens: int = 350,
    pack_max_chars: int = 1500,
) -> list[dict[str, Any]]:
    """Normalise ``chunks`` (``{"text", "metadata"}`` dicts) for storage; see the module docstring.

    ``max_tokens`` is the embedder's chunk budget (``NexusClient`` passes its limiter's,
    ``DEFAULT_MAX_TOKENS`` otherwise). When ``title`` is given (it is prefixed to each chunk
    at embedding time) and it is longer than the headroom the budget already leaves, the
    budget shrinks by the difference so the title never pushes text out of the window.
    """
    count = count_tokens or estimate_tokens
    budget = int(max_tokens or DEFAULT_MAX_TOKENS)
    if title:
        headroom = max(8, budget // 8)  # what a 0.88 x window budget leaves for a prefix
        over = count(title) + 1 - headroom
        if over > 0:
            budget = max(64, budget - over)
    dropped = set(drop_keys)
    items: list[dict[str, Any]] = []
    for chunk in chunks:
        text = _clean(chunk.get("text", ""))
        if not text:
            continue
        raw_meta = chunk.get("metadata")
        meta = {
            k: v
            for k, v in (raw_meta if isinstance(raw_meta, dict) else {}).items()
            if k not in dropped
        }
        items.extend(_split(text, meta, budget, count, row_keys))

    lengths = sorted(len(i["text"]) for i in items)
    if len(items) < pack_min_chunks or lengths[len(lengths) // 2] >= pack_median_chars:
        return items

    target = min(pack_target_tokens, budget)
    packed: list[dict[str, Any]] = []
    buf: list[dict[str, Any]] = []
    used = chars = 0
    for item in items:
        if item["metadata"].get(keep_whole_key) is not None:  # record-level chunk: stays its own
            if buf:
                packed.append(_pack(buf, row_keys))
                buf, used, chars = [], 0, 0
            packed.append(item)
            continue
        cost = count(item["text"]) + 1
        size = len(item["text"]) + 1
        if buf and (used + cost > target or chars + size > pack_max_chars):
            packed.append(_pack(buf, row_keys))
            buf, used, chars = [], 0, 0
        buf.append(item)
        used += cost
        chars += size
    if buf:
        packed.append(_pack(buf, row_keys))
    return packed


_STRUCTURE_KEYS = ("heading_path", "section_title", "section", "sheet_name", "slide_title")


def _structure(chunk: dict[str, Any]) -> str | None:
    text = str(chunk.get("text") or "")
    first = text.split("\n", 1)[0]
    if first.startswith("Section: "):
        return first.removeprefix("Section: ").strip()
    meta = chunk.get("metadata") if isinstance(chunk.get("metadata"), dict) else {}
    for key in _STRUCTURE_KEYS:
        value = meta.get(key)
        if isinstance(value, list | tuple):
            value = " > ".join(str(v) for v in value if v)
        if value:
            return str(value).strip()
    return None


def document_digest(
    name: str,
    file_type: str,
    chunks: list[dict[str, Any]],
    *,
    max_chars: int = 1200,
    max_sections: int = 40,
) -> str:
    """Summary text for a document's summary vector (see the module docstring)."""
    sections: list[str] = []
    for chunk in chunks:
        crumb = _structure(chunk)
        if crumb and crumb not in sections:
            sections.append(crumb)
    opening = " ".join(str(c.get("text") or "") for c in chunks[:3])[:max_chars]
    parts = [f"Document: {name} (type: {file_type}, {len(chunks)} chunks)."]
    if sections:
        parts.append("Sections: " + "; ".join(sections[:max_sections]) + ".")
    parts.append("Opening content: " + opening)
    return "\n".join(parts)


def title_passages(
    texts: list[str],
    titles: list[str] | str | None,
    *,
    count_tokens: TokenCounter | None = None,
    window: int | None = None,
    reserved: int = 2,
) -> list[str]:
    """Embedding inputs ``f"{title}\\n{text}"`` that fit a ``window``-token model.

    The title gives a passage its document context. When title and passage together
    would exceed the window (minus ``reserved`` special tokens), the title is shortened
    word by word, or dropped; the passage is never cut. Without a ``window`` the title is
    prefixed as is.
    """
    texts = list(texts)
    if titles is None:
        return texts
    names = [titles] * len(texts) if isinstance(titles, str) else list(titles)
    if len(names) != len(texts):
        raise ValueError("titles must be one string or one per text")
    if not window:
        return [f"{n}\n{t}" if n else t for t, n in zip(texts, names, strict=True)]
    count = count_tokens or estimate_tokens
    out = []
    for text, title in zip(texts, names, strict=True):
        if not title:
            out.append(text)
            continue
        room = window - reserved - count(text) - 1
        words = title.split()
        while words and count(" ".join(words)) > room:
            words.pop()
        out.append(f"{' '.join(words)}\n{text}" if words else text)
    return out
