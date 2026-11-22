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

"""GitHub repository files, issues and pull requests as Markdown documents.

``github_file_markdown(repo, branch, path, text)`` gives one file (a README, a ``docs/`` page,
a text file) a header (path, repository, branch, link) and a body:

* Markdown (``.md``, ``.mdx``, ``.markdown``, ``.mdown``): the text, with YAML front matter
  turned into plain ``key: value`` lines (its ``---`` closing line would otherwise make the line
  above it a heading), MDX ``import`` / ``export`` lines dropped, and relative links and
  images made absolute (``docs/guide.md`` -> ``https://github.com/<repo>/blob/<branch>/...``,
  images -> ``raw.githubusercontent.com``) so they work outside the repository; code blocks are
  left alone.
* anything else: one fenced code block whose fence is longer than any backtick run inside
  (a file that contains a fence cannot close it early), with a language from the extension.

``github_issue_markdown(repo, item, comments, reviews, review_comments)`` renders an issue or a
pull request (GitHub REST ``/issues`` item) with its comments, reviews and review comments.
"""

from __future__ import annotations

import posixpath
import re
from collections.abc import Mapping, Sequence
from typing import Any
from urllib.parse import quote

__all__ = [
    "code_fence",
    "github_file_markdown",
    "github_issue_markdown",
    "is_markdown_path",
    "markdown_links_absolute",
]

MARKDOWN_EXTENSIONS = (".md", ".mdx", ".markdown", ".mdown")
_LANGUAGES = {
    "py": "python", "js": "javascript", "ts": "typescript", "tsx": "tsx", "jsx": "jsx",
    "rb": "ruby", "go": "go", "rs": "rust", "java": "java", "kt": "kotlin", "sh": "bash",
    "yml": "yaml", "yaml": "yaml", "json": "json", "toml": "toml", "sql": "sql", "rst": "rst",
    "html": "html", "css": "css", "c": "c", "h": "c", "cpp": "cpp", "cs": "csharp",
    "php": "php", "swift": "swift", "scala": "scala", "r": "r", "ini": "ini", "xml": "xml",
}  # fmt: skip
_FENCE_LINE = re.compile(r"^ {0,3}(`{3,}|~{3,})")
_BACKTICKS = re.compile(r"`{3,}")
_FRONT_MATTER = re.compile(r"\A---[ \t]*\r?\n(.*?)\r?\n(?:---|\.\.\.)[ \t]*(?:\r?\n|\Z)", re.S)
_MDX_LINE = re.compile(r"^(?:import\s.+\sfrom\s|import\s+['\"]|export\s+(?:const|default|\{))")
_LINK = re.compile(r"(!?)\[((?:[^\[\]]|\[[^\]]*\])*)\]\(\s*<?([^)\s>]+)>?((?:\s+\"[^\"]*\")?)\s*\)")
_ABSOLUTE = re.compile(r"^(?:[a-z][a-z0-9+.-]*:|//|#|mailto:)", re.I)


def is_markdown_path(path: str) -> bool:
    return path.lower().endswith(MARKDOWN_EXTENSIONS)


def code_fence(text: str, language: str = "") -> str:
    """``text`` as one fenced code block that nothing inside can close."""
    longest = max((len(m.group()) for m in _BACKTICKS.finditer(text)), default=0)
    fence = "`" * max(3, longest + 1)
    body = text if text.endswith("\n") else text + "\n"
    return f"{fence}{language}\n{body}{fence}"


def _resolve(target: str, base_dir: str) -> str | None:
    path, sep, frag = target.partition("#")
    path, qs_sep, qs = path.partition("?")
    joined = path.lstrip("/") if path.startswith("/") else posixpath.join(base_dir, path)
    normal = posixpath.normpath(joined)
    if normal.startswith("..") or normal == ".":
        return None  # outside the repository: left as written
    return quote(normal) + (qs_sep + qs) + (sep + frag)


def markdown_links_absolute(text: str, repo: str, branch: str, path: str) -> str:
    """Relative links and images of a Markdown file at ``path`` made absolute (outside code)."""
    base_dir = posixpath.dirname(path)
    blob = f"https://github.com/{repo}/blob/{branch}/"
    raw = f"https://raw.githubusercontent.com/{repo}/{branch}/"

    def link(m: re.Match[str]) -> str:
        bang, label, target, title = m.groups()
        if _ABSOLUTE.match(target):
            return m.group(0)
        resolved = _resolve(target, base_dir)
        if resolved is None:
            return m.group(0)
        return f"{bang}[{label}]({(raw if bang else blob) + resolved}{title})"

    out: list[str] = []
    fence = ""
    for line in text.split("\n"):
        mark = _FENCE_LINE.match(line)
        if fence:
            if mark and mark.group(1)[0] == fence[0] and len(mark.group(1)) >= len(fence):
                fence = ""
            out.append(line)
        elif mark:
            fence = mark.group(1)
            out.append(line)
        else:
            out.append(_LINK.sub(link, line) if "](" in line else line)
    return "\n".join(out)


def _markdown_body(text: str, path: str, repo: str, branch: str, absolute_links: bool) -> str:
    text = text.lstrip("﻿")
    front = _FRONT_MATTER.match(text)
    if front:
        fields = [line.rstrip() for line in front.group(1).splitlines() if line.strip()]
        text = ("\n".join(fields) + "\n\n" if fields else "") + text[front.end() :]
    if path.lower().endswith(".mdx"):
        text = "\n".join(line for line in text.split("\n") if not _MDX_LINE.match(line))
    if absolute_links and "](" in text:
        text = markdown_links_absolute(text, repo, branch, path)
    return text


def github_file_markdown(
    repo: str,
    branch: str,
    path: str,
    text: str,
    *,
    url: str | None = None,
    absolute_links: bool = True,
) -> str:
    """One repository file as a Markdown document (module doc)."""
    url = url or f"https://github.com/{repo}/blob/{branch}/{path}"
    if is_markdown_path(path):
        body = _markdown_body(text, path, repo, branch, absolute_links)
    else:
        ext = path.rsplit(".", 1)[-1].lower() if "." in posixpath.basename(path) else ""
        body = code_fence(text, _LANGUAGES.get(ext, ""))
    return f"# {path}\n\nRepository: {repo} · Branch: {branch}\nLink: {url}\n\n{body}\n"


def _login(obj: Mapping[str, Any]) -> str:
    return str((obj.get("user") or {}).get("login", ""))


def _day(value: Any) -> str:
    return str(value or "")[:10]


def github_issue_markdown(
    repo: str,
    item: Mapping[str, Any],
    comments: Sequence[Mapping[str, Any]] = (),
    reviews: Sequence[Mapping[str, Any]] = (),
    review_comments: Sequence[Mapping[str, Any]] = (),
    *,
    state: str | None = None,
    labels: Sequence[str] | None = None,
    url: str | None = None,
) -> str:
    """An issue or pull request (``/issues`` item) with its discussion, as Markdown."""
    number, is_pr = item.get("number"), "pull_request" in item
    if state is None:
        merged = (item.get("pull_request") or {}).get("merged_at")
        state = "merged" if is_pr and merged else str(item.get("state", ""))
    if labels is None:
        labels = [
            str(lab["name"])
            for lab in item.get("labels") or ()
            if isinstance(lab, Mapping) and lab.get("name")
        ]
    kind = "Pull request" if is_pr else "Issue"
    url = (
        url
        or item.get("html_url")
        or (f"https://github.com/{repo}/{'pull' if is_pr else 'issues'}/{number}")
    )
    closed_at = item.get("closed_at")
    lines = [
        f"# {kind} #{number}: {item.get('title', '')}",
        "",
        f"Repository: {repo} · State: {state}"
        + (f" · Labels: {', '.join(labels)}" if labels else ""),
        f"Opened by {_login(item)} on {_day(item.get('created_at'))}"
        + (f" · Closed {_day(closed_at)}" if closed_at else ""),
        f"Link: {url}",
        "",
        str(item.get("body") or "").strip() or "_No description._",
    ]
    if comments:
        lines += ["", "## Comments", ""]
        for c in comments:
            lines += [f"**{_login(c)}** ({_day(c.get('created_at'))}):", "",
                      str(c.get("body") or "").strip(), ""]  # fmt: skip
    written = [r for r in reviews if str(r.get("body") or "").strip()]
    if written:
        lines += ["", "## Reviews", ""]
        for r in written:
            verdict = str(r.get("state") or "").lower().replace("_", " ")
            lines += [f"**{_login(r)}** ({verdict}, {_day(r.get('submitted_at'))}):", "",
                      str(r.get("body") or "").strip(), ""]  # fmt: skip
    if review_comments:
        lines += ["", "## Review comments", ""]
        for c in review_comments:
            where = c.get("path") or ""
            line = c.get("line") or c.get("original_line")
            lines += [
                f"**{_login(c)}** on `{where}`"
                + (f" line {line}" if line else "")
                + f" ({_day(c.get('created_at'))}):",
                "",
                str(c.get("body") or "").strip(),
                "",
            ]
    return "\n".join(lines).strip() + "\n"
