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

"""Atlassian Document Format (Jira / Confluence rich-text JSON) to Markdown.

Paragraphs, headings (starting at ``##``: the issue title is the ``#`` heading), lists
with nesting and ``order``, code blocks, quotes, panels, rules, tables, task and
decision lists, expands, mentions, emoji, status lozenges, dates and cards. Media and
extensions carry no text and are noted or skipped.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any

__all__ = ["adf_to_markdown"]

_PANEL = {
    "info": "Info",
    "note": "Note",
    "warning": "Warning",
    "error": "Error",
    "success": "Success",
    "tip": "Tip",
}


def _marks(text: str, marks: list[dict[str, Any]]) -> str:
    if not text:
        return text
    link = None
    for m in marks or []:
        kind = m.get("type")
        if kind == "code":
            text = f"`{text}`"
        elif kind == "strong":
            text = f"**{text}**"
        elif kind == "em":
            text = f"*{text}*"
        elif kind == "strike":
            text = f"~~{text}~~"
        elif kind == "link":
            link = (m.get("attrs") or {}).get("href")
    return f"[{text}]({link})" if link and not str(link).startswith("javascript:") else text


def _inline(nodes: list[dict[str, Any]] | None) -> str:
    out = []
    for n in nodes or []:
        t, attrs = n.get("type"), n.get("attrs") or {}
        if t == "text":
            out.append(_marks(n.get("text", ""), n.get("marks") or []))
        elif t == "hardBreak":
            out.append("  \n")
        elif t == "mention":
            out.append(attrs.get("text") or "@user")
        elif t == "emoji":
            out.append(attrs.get("text") or attrs.get("shortName") or "")
        elif t in ("inlineCard", "blockCard", "embedCard"):
            url = attrs.get("url") or ""
            out.append(f"<{url}>" if url else "")
        elif t == "status":
            out.append(f"[{attrs.get('text', '')}]")
        elif t == "date":
            try:
                stamp = datetime.fromtimestamp(int(attrs.get("timestamp")) / 1000, tz=UTC)
                out.append(stamp.strftime("%Y-%m-%d"))
            except (TypeError, ValueError):
                pass
        elif t in ("media", "mediaInline"):
            out.append("[attachment]")
        else:
            out.append(_inline(n.get("content")))
    return "".join(out)


def _cell(node: dict[str, Any]) -> str:
    text = " ".join(ln.strip() for ln in _blocks(node.get("content"), 0) if ln.strip())
    return text.replace("|", "\\|").replace("\n", " ")


def _table(node: dict[str, Any]) -> list[str]:
    rows = []
    for row in node.get("content") or []:
        cells = [
            c for c in row.get("content") or [] if c.get("type") in ("tableCell", "tableHeader")
        ]
        if cells:
            rows.append(
                ([_cell(c) for c in cells], all(c.get("type") == "tableHeader" for c in cells))
            )
    if not rows:
        return []
    width = max(len(r) for r, _ in rows)

    def pad(r: list[str]) -> list[str]:
        return r + [""] * (width - len(r))

    header, rest = (rows[0][0], rows[1:]) if rows[0][1] else ([""] * width, rows)
    lines = ["| " + " | ".join(pad(header)) + " |", "|" + " --- |" * width]
    return lines + ["| " + " | ".join(pad(r)) + " |" for r, _ in rest] + [""]


def _list(node: dict[str, Any], depth: int) -> list[str]:
    out: list[str] = []
    ordered = node.get("type") == "orderedList"
    start = int((node.get("attrs") or {}).get("order") or 1)
    for i, item in enumerate(node.get("content") or []):
        marker = f"{start + i}." if ordered else "-"
        text: list[str] = []
        nested: list[str] = []
        for c in item.get("content") or []:
            if c.get("type") in ("bulletList", "orderedList"):
                nested += _list(c, depth + 1)
            else:
                text.append(" ".join(ln.strip() for ln in _blocks([c], depth) if ln.strip()))
        out.append(f"{'  ' * depth}{marker} {' '.join(t for t in text if t)}".rstrip())
        out += nested
    return out


def _blocks(nodes: list[dict[str, Any]] | None, depth: int = 0) -> list[str]:
    out: list[str] = []
    for n in nodes or []:
        t, attrs = n.get("type"), n.get("attrs") or {}
        if t == "paragraph":
            text = _inline(n.get("content")).strip()
            if text:
                out += [text, ""]
        elif t == "heading":
            text = _inline(n.get("content")).strip()
            if text:
                out += [f"{'#' * min(6, int(attrs.get('level') or 1) + 1)} {text}", ""]
        elif t in ("bulletList", "orderedList"):
            out += [*_list(n, depth), ""]
        elif t == "codeBlock":
            code = "".join(c.get("text", "") for c in n.get("content") or [])
            out += [f"```{attrs.get('language') or ''}", code, "```", ""]
        elif t == "blockquote":
            out += [f"> {ln}" for ln in _blocks(n.get("content"), depth) if ln.strip()] + [""]
        elif t == "panel":
            inner = [ln for ln in _blocks(n.get("content"), depth) if ln.strip()]
            label = _PANEL.get(attrs.get("panelType", ""), "")
            if label and inner:
                inner[0] = f"**{label}:** {inner[0]}"
            out += [f"> {ln}" for ln in inner] + [""]
        elif t == "rule":
            out += ["---", ""]
        elif t == "table":
            out += _table(n)
        elif t == "taskList":
            for item in n.get("content") or []:
                done = "x" if (item.get("attrs") or {}).get("state") == "DONE" else " "
                out.append(f"- [{done}] {_inline(item.get('content')).strip()}".rstrip())
            out.append("")
        elif t == "decisionList":
            out += [
                f"- Decision: {_inline(d.get('content')).strip()}" for d in n.get("content") or []
            ] + [""]
        elif t in ("expand", "nestedExpand"):
            title = attrs.get("title")
            out += ([f"**{title}**", ""] if title else []) + _blocks(n.get("content"), depth)
        elif t in ("mediaSingle", "mediaGroup"):
            out += ["[attachment]", ""]
        elif t in ("extension", "bodiedExtension", "inlineExtension"):
            continue
        elif n.get("content"):
            out += _blocks(n.get("content"), depth)
    return out


def adf_to_markdown(doc: Any) -> str:
    """Atlassian Document Format as readable Markdown. Plain strings pass through."""
    if not doc:
        return ""
    if isinstance(doc, str):
        return doc.strip()
    text = "\n".join(_blocks(doc.get("content") if isinstance(doc, dict) else doc))
    return re.sub(r"\n{3,}", "\n\n", text).strip()
