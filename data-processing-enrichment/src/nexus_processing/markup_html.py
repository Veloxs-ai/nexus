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

"""HTML and Confluence storage format (XHTML) to Markdown, standard library only.

``html_to_markdown`` keeps the structure retrieval needs: headings become ``#`` lines (so
``chunk_markdown`` breadcrumbs apply), tables become pipe tables, lists keep their
nesting, code keeps its fences. Scripts, styles, navigation, footers and asides are
dropped. ``dialect="confluence"`` also understands Confluence storage macros (code,
panels, expand, status, task lists, links to pages/attachments/users, CDATA bodies) and
starts page headings at ``##`` because the page title is the ``#`` heading.
"""

from __future__ import annotations

import re
from html.parser import HTMLParser
from typing import Literal

__all__ = ["html_to_markdown"]

_VOID = {
    "br",
    "hr",
    "img",
    "col",
    "ri:page",
    "ri:attachment",
    "ri:url",
    "ri:user",
    "ri:space",
    "ri:blog-post",
    "ac:emoticon",
    "ri:shortcut",
    "meta",
    "link",
    "input",
    "source",
    "wbr",
    "area",
    "base",
    "embed",
    "param",
    "track",
}
_PANELS = {
    "info": "Info",
    "note": "Note",
    "warning": "Warning",
    "tip": "Tip",
    "panel": "",
    "success": "Success",
    "error": "Error",
}
_SKIP_MACROS = {
    "toc",
    "children",
    "anchor",
    "recently-updated",
    "pagetree",
    "attachments",
    "livesearch",
    "include",
    "excerpt-include",
    "contentbylabel",
    "jira",
    "gallery",
    "profile",
}
_DROP_TAGS = {
    "script",
    "style",
    "head",
    "noscript",
    "template",
    "nav",
    "footer",
    "aside",
    "iframe",
    "svg",
    "button",
    "select",
    "option",
    "title",
}
_CONTAINERS = {
    "p",
    "div",
    "section",
    "article",
    "main",
    "header",
    "body",
    "html",
    "figure",
    "form",
    "details",
    "center",
    "span-block",
}


class _Node:
    __slots__ = ("attrs", "children", "tag")

    def __init__(self, tag: str, attrs: dict[str, str] | None = None) -> None:
        self.tag, self.attrs, self.children = tag, attrs or {}, []

    def find(self, tag: str, **attrs: str) -> _Node | None:
        for c in self.children:
            if (
                isinstance(c, _Node)
                and c.tag == tag
                and all(c.attrs.get(k) == v for k, v in attrs.items())
            ):
                return c
        return None

    def param(self, name: str) -> str:
        p = self.find("ac:parameter", **{"ac:name": name})
        return _text(p).strip() if p else ""


def _text(node: _Node | str | None) -> str:
    if node is None:
        return ""
    if isinstance(node, str):
        return node
    return "".join(_text(c) for c in node.children)


# HTML5 implied end tags (end tags HTML lets authors omit): a start tag listed here
# closes the open element named in ``targets`` unless a ``stops`` element is nearer.
_P_CLOSERS = frozenset(
    [
        "address",
        "article",
        "aside",
        "blockquote",
        "center",
        "details",
        "dialog",
        "dir",
        "div",
        "dl",
        "fieldset",
        "figcaption",
        "figure",
        "footer",
        "form",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "header",
        "hgroup",
        "hr",
        "main",
        "menu",
        "nav",
        "ol",
        "p",
        "pre",
        "section",
        "table",
        "ul",
        "li",
        "dd",
        "dt",
    ]
)
_P_STOPS = frozenset(
    ["table", "td", "th", "caption", "marquee", "object", "applet", "template", "button"]
)
_TABLE_STOPS = frozenset({"table"})
_P_ONLY = frozenset({"p"})
_IMPLIED: dict[str, tuple[frozenset[str], frozenset[str]]] = {
    "li": (frozenset({"li"}), frozenset({"ul", "ol", "menu", "dir", *_P_STOPS})),
    "dt": (frozenset({"dt", "dd"}), frozenset({"dl", *_P_STOPS})),
    "dd": (frozenset({"dt", "dd"}), frozenset({"dl", *_P_STOPS})),
    "td": (frozenset({"td", "th"}), frozenset({"tr", *_TABLE_STOPS})),
    "th": (frozenset({"td", "th"}), frozenset({"tr", *_TABLE_STOPS})),
    "tr": (frozenset({"tr"}), frozenset({"thead", "tbody", "tfoot", *_TABLE_STOPS})),
    "thead": (frozenset({"thead", "tbody", "tfoot"}), _TABLE_STOPS),
    "tbody": (frozenset({"thead", "tbody", "tfoot"}), _TABLE_STOPS),
    "tfoot": (frozenset({"thead", "tbody", "tfoot"}), _TABLE_STOPS),
    "option": (frozenset({"option"}), frozenset({"select", "datalist", "optgroup"})),
}
# Every (targets, stops) rule a start tag triggers, in order: one lookup per start tag.
_START_RULES: dict[str, tuple[tuple[frozenset[str], frozenset[str]], ...]] = {
    tag: (((_P_ONLY, _P_STOPS),) if tag in _P_CLOSERS else ())
    + ((_IMPLIED[tag],) if tag in _IMPLIED else ())
    for tag in _P_CLOSERS | _IMPLIED.keys()
}
# Deeper nesting is flattened into the element at this depth, so rendering (recursive)
# never hits Python's recursion limit and a document is never lost.
_MAX_DEPTH = 200


class _TreeBuilder(HTMLParser):
    def __init__(self, implied_ends: bool = True) -> None:
        super().__init__(convert_charrefs=True)
        self.root = _Node("root")
        self.stack = [self.root]
        self.implied_ends = implied_ends

    def handle_starttag(self, tag, attrs):
        stack = self.stack
        if self.implied_ends:
            rules = _START_RULES.get(tag)
            if rules:
                for targets, stops in rules:  # close the nearest target unless a stop is nearer
                    for i in range(len(stack) - 1, 0, -1):
                        open_tag = stack[i].tag
                        if open_tag in targets:
                            del stack[i:]
                            break
                        if open_tag in stops:
                            break
        node = _Node(tag, {k: (v or "") for k, v in attrs})
        stack[-1].children.append(node)
        if tag not in _VOID and len(stack) < _MAX_DEPTH:
            stack.append(node)

    def handle_startendtag(self, tag, attrs):
        self.stack[-1].children.append(_Node(tag, {k: (v or "") for k, v in attrs}))

    def handle_endtag(self, tag):
        for i in range(len(self.stack) - 1, 0, -1):
            if self.stack[i].tag == tag:
                del self.stack[i:]
                return

    def handle_data(self, data):
        self.stack[-1].children.append(data)

    def unknown_decl(self, data):  # <![CDATA[ ... ]]> (code macro bodies)
        if data.startswith("CDATA["):
            self.stack[-1].children.append(data[6:])


_CONFLUENCE_CONTAINERS = {"p", "div", "section"}


class _Renderer:
    def __init__(self, html: bool) -> None:
        self.html = html
        self.offset = 0 if html else 1
        self.drop = _DROP_TAGS if html else {"style", "script"}
        self.containers = _CONTAINERS if html else _CONFLUENCE_CONTAINERS
        self.extra_blocks = {"hr", *_CONTAINERS} if html else set()

    def inline(self, node: _Node | str) -> str:
        if isinstance(node, str):
            return re.sub(r"\s+", " ", node)
        tag = node.tag
        if tag == "br":
            return "  \n"
        if tag in ("ac:parameter", "ac:placeholder") or tag in self.drop:
            return ""
        inner = "".join(self.inline(c) for c in node.children)
        if tag in ("strong", "b"):
            return f"**{inner.strip()}**" if inner.strip() else ""
        if tag in ("em", "i"):
            return f"*{inner.strip()}*" if inner.strip() else ""
        if tag in ("s", "del") or (self.html and tag == "strike"):
            return f"~~{inner.strip()}~~" if inner.strip() else ""
        if tag == "code":
            return f"`{_text(node).strip()}`"
        if tag == "a":
            href = node.attrs.get("href", "")
            label = inner.strip() or href
            return f"[{label}]({href})" if href and not href.startswith("javascript:") else label
        if tag == "img" and self.html:
            alt = node.attrs.get("alt", "").strip()
            return f"[image: {alt}]" if alt else ""
        if tag == "ac:link":
            body = node.find("ac:link-body") or node.find("ac:plain-text-link-body")
            target = (
                node.find("ri:page")
                or node.find("ri:blog-post")
                or node.find("ri:attachment")
                or node.find("ri:space")
            )
            if node.find("ri:user") is not None and body is None:
                return "@user"
            label = _text(body).strip() if body else ""
            if target is not None:
                label = (
                    label
                    or target.attrs.get("ri:content-title")
                    or target.attrs.get("ri:filename")
                    or target.attrs.get("ri:space-key", "")
                )
            return label
        if tag == "ac:image":
            att = node.find("ri:attachment")
            url = node.find("ri:url")
            name = (att.attrs.get("ri:filename") if att else "") or (
                url.attrs.get("ri:value") if url else ""
            )
            return f"[image: {name or 'image'}]"
        if tag == "ac:emoticon":
            return node.attrs.get("ac:emoji-fallback", "")
        if tag == "time":
            return node.attrs.get("datetime", inner)
        if tag == "ac:structured-macro":
            name = node.attrs.get("ac:name", "")
            if name == "status":
                return f"[{node.param('title') or 'status'}]"
            if name in _SKIP_MACROS:
                return ""
            body = node.find("ac:rich-text-body") or node.find("ac:plain-text-body")
            return self.inline(body) if body else ""
        return inner

    def cell(self, node: _Node) -> str:
        lines = [ln.strip() for ln in self.blocks(node) if ln.strip()]
        text = " ".join(lines) if lines else self.inline(node).strip()
        return text.replace("|", "\\|").replace("\n", " ")

    def table(self, node: _Node) -> list[str]:
        rows: list[tuple[list[str], bool]] = []

        def collect(n: _Node) -> None:
            for c in n.children:
                if isinstance(c, _Node):
                    if c.tag == "tr":
                        cells = [
                            x for x in c.children if isinstance(x, _Node) and x.tag in ("td", "th")
                        ]
                        rows.append(
                            (
                                [self.cell(x) for x in cells],
                                bool(cells) and all(x.tag == "th" for x in cells),
                            )
                        )
                    elif c.tag in ("thead", "tbody", "tfoot", "colgroup"):
                        collect(c)

        collect(node)
        rows = [r for r in rows if r[0]]
        if not rows:
            return []
        width = max(len(r) for r, _ in rows)

        def pad(r: list[str]) -> list[str]:
            return r + [""] * (width - len(r))

        header, rest = (rows[0][0], rows[1:]) if rows[0][1] else ([""] * width, rows)
        out = ["| " + " | ".join(pad(header)) + " |", "|" + " --- |" * width]
        out += ["| " + " | ".join(pad(r)) + " |" for r, _ in rest]
        return [*out, ""]

    def list_(self, node: _Node, depth: int) -> list[str]:
        out: list[str] = []
        n = 0
        ordered = node.tag == "ol"
        for li in node.children:
            if not isinstance(li, _Node) or li.tag != "li":
                continue
            n += 1
            marker = f"{n}." if ordered else "-"
            inline_parts: list[str] = []
            nested: list[str] = []
            for c in li.children:
                if isinstance(c, _Node) and c.tag in ("ul", "ol"):
                    nested += self.list_(c, depth + 1)
                elif isinstance(c, _Node) and c.tag in ("p", "div"):
                    inline_parts.append(self.inline(c).strip())
                else:
                    inline_parts.append(self.inline(c))
            text = " ".join(p.strip() for p in inline_parts if p and p.strip())
            out.append(f"{'  ' * depth}{marker} {text}".rstrip())
            out += nested
        return out

    def macro(self, node: _Node, depth: int) -> list[str]:
        name = node.attrs.get("ac:name", "")
        if name in _SKIP_MACROS:
            return []
        if name in ("code", "noformat"):
            body = node.find("ac:plain-text-body")
            code = _text(body).strip("\n") if body else ""
            title = node.param("title")
            return ([f"**{title}**"] if title else []) + [
                f"```{node.param('language')}",
                code,
                "```",
                "",
            ]
        if name in _PANELS:
            body = node.find("ac:rich-text-body")
            label = _PANELS[name] or node.param("title")
            inner = [ln for ln in (self.blocks(body, depth) if body else []) if ln.strip()]
            if label and inner:
                inner[0] = f"**{label}:** {inner[0]}"
            return [f"> {ln}" for ln in inner] + [""]
        if name == "expand":
            body = node.find("ac:rich-text-body")
            title = node.param("title")
            return ([f"**{title}**", ""] if title else []) + (
                self.blocks(body, depth) if body else []
            )
        body = node.find("ac:rich-text-body")
        if body is not None:
            return self.blocks(body, depth)
        text = self.inline(node).strip()
        return [text, ""] if text else []

    def is_block(self, node: _Node | str) -> bool:
        if not isinstance(node, _Node):
            return False
        if node.tag == "ac:structured-macro":
            return node.attrs.get("ac:name", "") in _BLOCK_MACROS
        if node.tag in self.extra_blocks:
            return True
        return node.tag in ("ul", "ol", "table", "pre", "blockquote", "ac:task-list") or bool(
            re.fullmatch(r"h[1-6]", node.tag)
        )

    def blocks(self, node: _Node | None, depth: int = 0) -> list[str]:
        if node is None:
            return []
        out: list[str] = []
        buf: list[str] = []

        def flush() -> None:
            text = "".join(buf).strip()
            if text:
                out.extend([text, ""])
            buf.clear()

        for c in node.children:
            if isinstance(c, str):
                buf.append(self.inline(c))
                continue
            tag = c.tag
            if tag in self.drop:
                continue
            if re.fullmatch(r"h[1-6]", tag):
                flush()
                title = self.inline(c).strip()
                if title:
                    out += [f"{'#' * min(6, int(tag[1]) + self.offset)} {title}", ""]
            elif tag in self.containers:
                flush()
                if any(self.is_block(x) for x in c.children):
                    out += self.blocks(c, depth)
                elif self.inline(c).strip():
                    out += [self.inline(c).strip(), ""]
            elif tag in ("ul", "ol"):
                flush()
                out += [*self.list_(c, depth), ""]
            elif tag == "table":
                flush()
                out += self.table(c)
            elif tag == "pre":
                flush()
                out += ["```", _text(c).strip("\n"), "```", ""]
            elif tag == "blockquote":
                flush()
                out += [f"> {ln}" for ln in self.blocks(c, depth) if ln.strip()] + [""]
            elif tag == "hr":
                flush()
                out += ["---", ""]
            elif tag == "ac:structured-macro" and self.is_block(c):
                flush()
                out += self.macro(c, depth)
            elif tag == "ac:structured-macro" and c.attrs.get("ac:name", "") in _SKIP_MACROS:
                continue
            elif tag == "ac:task-list":
                flush()
                for task in c.children:
                    if isinstance(task, _Node) and task.tag == "ac:task":
                        status = task.find("ac:task-status")
                        body = task.find("ac:task-body")
                        done = (
                            "x"
                            if status is not None and _text(status).strip() == "complete"
                            else " "
                        )
                        out.append(
                            f"- [{done}] {self.inline(body).strip() if body else ''}".rstrip()
                        )
                out.append("")
            elif tag in (
                "ac:layout",
                "ac:layout-section",
                "ac:layout-cell",
                "ac:rich-text-body",
                "tbody",
            ):
                flush()
                out += self.blocks(c, depth)
            else:
                buf.append(self.inline(c))
        flush()
        return out


_BLOCK_MACROS = {"code", "noformat", "expand", *_PANELS}


def html_to_markdown(html: str, *, dialect: Literal["html", "confluence"] = "html") -> str:
    """HTML (or Confluence storage XHTML) as readable Markdown; see the module docstring."""
    # Confluence storage is XHTML (every element closed), so only HTML gets implied ends.
    builder = _TreeBuilder(implied_ends=dialect != "confluence")
    builder.feed(html or "")
    builder.close()
    renderer = _Renderer(html=dialect != "confluence")
    text = "\n".join(renderer.blocks(builder.root))
    return re.sub(r"\n{3,}", "\n\n", text).strip()
