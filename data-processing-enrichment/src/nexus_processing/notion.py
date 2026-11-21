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

"""Notion content to Markdown and plain values (pure functions; fetching stays with the caller).

``notion_blocks_to_markdown`` renders a page's block tree. The caller passes
``list_children(block_id) -> iterable of blocks`` (its paging API client), so this
module never talks to Notion: it only turns block JSON into Markdown lines (headings,
paragraphs, bulleted/numbered/to-do lists, toggles, quotes and callouts, code,
equations, dividers, tables, sub-pages and inline databases, bookmarks and files).
``notion_property_value`` turns a database property into a plain value for records.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import Any

__all__ = [
    "MAX_BLOCKS_PER_PAGE",
    "MAX_DEPTH",
    "notion_blocks_to_markdown",
    "notion_page_title",
    "notion_property_value",
    "notion_rich_text",
]

MAX_DEPTH = 8
MAX_BLOCKS_PER_PAGE = 5000

ListChildren = Callable[[str], Iterable[dict[str, Any]]]


def notion_rich_text(items: list[dict[str, Any]] | None) -> str:
    """Notion rich-text items as Markdown (code, bold, italic, links)."""
    out = []
    for it in items or []:
        text = it.get("plain_text") or ""
        if not text:
            continue
        ann = it.get("annotations") or {}
        if ann.get("code"):
            text = f"`{text}`"
        if ann.get("bold"):
            text = f"**{text}**"
        if ann.get("italic"):
            text = f"*{text}*"
        if it.get("href") and it.get("type") == "text":
            text = f"[{text}]({it['href']})"
        out.append(text)
    return "".join(out)


def _caption(b: dict[str, Any]) -> str:
    return notion_rich_text(b.get("caption"))


def _table(list_children: ListChildren, block: dict[str, Any], indent: str) -> list[str]:
    rows = [
        [notion_rich_text(cell) for cell in (r.get("table_row") or {}).get("cells", [])]
        for r in list_children(block["id"])
        if r.get("type") == "table_row"
    ]
    if not rows:
        return []
    width = max(len(r) for r in rows)
    rows = [r + [""] * (width - len(r)) for r in rows]
    has_header = (block.get("table") or {}).get("has_column_header")
    header = rows[0] if has_header else [f"Column {i + 1}" for i in range(width)]
    body = rows[1:] if has_header else rows

    def esc(v: str) -> str:
        return v.replace("|", "\\|").replace("\n", " ")

    out = [
        f"{indent}| " + " | ".join(esc(h) for h in header) + " |",
        f"{indent}|" + " --- |" * width,
    ]
    out += [f"{indent}| " + " | ".join(esc(c) for c in r) + " |" for r in body]
    return ["", *out, ""]


def notion_blocks_to_markdown(
    block_id: str,
    list_children: ListChildren,
    *,
    depth: int = 0,
    budget: list[int] | None = None,
    databases: list[str] | None = None,
    max_depth: int = MAX_DEPTH,
    max_blocks: int = MAX_BLOCKS_PER_PAGE,
) -> list[str]:
    """Markdown lines for the children of ``block_id`` (recursive, list-aware).

    ``budget`` is a one-element list shared across the recursion (blocks left to render);
    ids of inline databases are appended to ``databases`` so the caller can read them.
    """
    budget = budget if budget is not None else [max_blocks]
    lines: list[str] = []
    if depth > max_depth:
        return lines
    indent = "  " * depth
    number = 0
    for block in list_children(block_id):
        if budget[0] <= 0:
            lines.append(f"{indent}…(page truncated)")
            return lines
        budget[0] -= 1
        btype = block.get("type") or ""
        data = block.get(btype) or {}
        number = number + 1 if btype == "numbered_list_item" else 0
        text = notion_rich_text(data.get("rich_text"))
        children = (
            notion_blocks_to_markdown(
                block["id"],
                list_children,
                depth=depth + 1,
                budget=budget,
                databases=databases,
                max_depth=max_depth,
                max_blocks=max_blocks,
            )
            if block.get("has_children") and btype not in ("child_page", "child_database", "table")
            else []
        )
        if btype.startswith("heading_"):
            level = min(6, int(btype[-1]) + depth)
            lines += ["", f"{'#' * level} {text}", ""]
            lines += [c[2:] if c.startswith("  ") else c for c in children]
            continue
        if btype == "paragraph":
            if text:
                lines.append(f"{indent}{text}")
            lines += children
        elif btype == "bulleted_list_item":
            lines.append(f"{indent}- {text}")
            lines += children
        elif btype == "numbered_list_item":
            lines.append(f"{indent}{number}. {text}")
            lines += children
        elif btype == "to_do":
            lines.append(f"{indent}- [{'x' if data.get('checked') else ' '}] {text}")
            lines += children
        elif btype == "toggle":
            lines.append(f"{indent}- {text}")
            lines += children
        elif btype in ("quote", "callout"):
            icon = (data.get("icon") or {}).get("emoji", "") if btype == "callout" else ""
            lines.append(f"{indent}> {(icon + ' ') if icon else ''}{text}")
            lines += [f"{indent}> {c.strip()}" for c in children if c.strip()]
        elif btype == "code":
            lines += [
                f"{indent}```{data.get('language') or ''}",
                *(f"{indent}{ln}" for ln in text.splitlines()),
                f"{indent}```",
            ]
        elif btype == "equation":
            lines.append(f"{indent}$$ {data.get('expression', '')} $$")
        elif btype == "divider":
            lines.append(f"{indent}---")
        elif btype == "table":
            lines += _table(list_children, block, indent)
        elif btype == "child_page":
            lines.append(f"{indent}Sub-page: {data.get('title', '')}")
        elif btype == "child_database":
            lines.append(f"{indent}Database: {data.get('title', '')}")
            if databases is not None:
                databases.append(block["id"])
        elif btype in ("bookmark", "embed", "link_preview"):
            url = data.get("url", "")
            lines.append(f"{indent}[{_caption(data) or url}]({url})" if url else "")
        elif btype in ("image", "file", "pdf", "video", "audio"):
            name = data.get("name") or _caption(data)
            lines.append(f"{indent}[{btype}{': ' + name if name else ''}]")
        elif btype in ("column_list", "column", "synced_block", "template", "meeting_notes"):
            title = notion_rich_text(data.get("title")) if btype == "meeting_notes" else ""
            if title:
                lines.append(f"{indent}{title}")
            lines += [c[2:] if c.startswith("  ") else c for c in children]
        # unsupported / breadcrumb / table_of_contents carry no text
    return lines


def notion_property_value(prop: dict[str, Any]) -> Any:
    """A database property as a plain value (text, number, date range, names, counts...)."""
    ptype = prop.get("type") or ""
    v = prop.get(ptype)
    if ptype in ("title", "rich_text"):
        return "".join(t.get("plain_text", "") for t in v or [])
    if ptype in ("select", "status"):
        return (v or {}).get("name")
    if ptype == "multi_select":
        return ", ".join(o.get("name", "") for o in v or [])
    if ptype == "date":
        if not v:
            return None
        return f"{v.get('start')} → {v['end']}" if v.get("end") else v.get("start")
    if ptype == "people":
        return ", ".join(p.get("name") or p.get("id", "") for p in v or [])
    if ptype in ("created_by", "last_edited_by"):
        return (v or {}).get("name") or (v or {}).get("id")
    if ptype == "files":
        return ", ".join(f.get("name", "") for f in v or [])
    if ptype == "formula":
        return (v or {}).get((v or {}).get("type", ""))
    if ptype == "relation":
        return len(v or [])
    if ptype == "rollup":
        r = v or {}
        inner = r.get(r.get("type", ""))
        return len(inner) if isinstance(inner, list) else inner
    if ptype == "unique_id":
        prefix = (v or {}).get("prefix") or ""
        return f"{prefix}{'-' if prefix else ''}{(v or {}).get('number')}"
    if ptype == "verification":
        return (v or {}).get("state")
    return v  # number, checkbox, url, email, phone_number, created_time, last_edited_time


def notion_page_title(page: dict[str, Any]) -> str:
    """The title property of a page or database row ("Untitled" when empty)."""
    for prop in (page.get("properties") or {}).values():
        if prop.get("type") == "title":
            return notion_property_value(prop) or "Untitled"
    return "Untitled"
