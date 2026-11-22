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

"""HTML parsing into a small node tree, with the HTML5 implied-end-tag rules
``html_to_markdown`` relies on."""

from __future__ import annotations

from html.parser import HTMLParser

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
