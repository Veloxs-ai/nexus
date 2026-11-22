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

"""Source records rendered as Markdown pages (one page per ticket, article or file).

Connectors fetch records from an API (ServiceNow Table API rows, Jira issues with their
comments, objects in a cloud bucket); these functions turn the already-fetched values into
the Markdown page that is chunked and stored: a title line, a facts line, the link, then the
body sections. Each returns ``(markdown, metadata)`` where the metadata names the record.
Rich-text bodies go through ``markup_html.html_to_markdown`` (ServiceNow article HTML) and
``markup_adf.adf_to_markdown`` (Jira's document format). Standard library only.
"""

from __future__ import annotations

from typing import Any

from .markup_adf import adf_to_markdown
from .markup_html import html_to_markdown

__all__ = [
    "field_text",
    "file_page",
    "file_page_header",
    "jira_issue_page",
    "servicenow_article_page",
    "servicenow_generic_page",
    "servicenow_task_page",
]

SERVICENOW_GENERIC_MAX_CHARS = 20_000

# (label, field) facts of a ServiceNow task record, in page order.
_TASK_FACTS = (
    ("State", "state"),
    ("Priority", "priority"),
    ("Impact", "impact"),
    ("Urgency", "urgency"),
    ("Category", "category"),
    ("Assigned to", "assigned_to"),
    ("Group", "assignment_group"),
    ("Caller", "caller_id"),
    ("Opened", "opened_at"),
    ("Resolved", "resolved_at"),
    ("Closed", "closed_at"),
)


def field_text(record: dict[str, Any], name: str) -> str:
    """A field as text. Reference fields come as ``{"display_value", "value"}`` objects."""
    value = record.get(name)
    if isinstance(value, dict):
        value = value.get("display_value") or value.get("value") or ""
    return str(value or "").strip()


def servicenow_article_page(record: dict[str, Any], *, url: str) -> tuple[str, dict[str, Any]]:
    """A ServiceNow knowledge article (``kb_knowledge`` row; its body is HTML)."""
    v = record
    number = field_text(v, "number")
    title = field_text(v, "short_description") or number
    facts = (
        f"Knowledge article {number}",
        field_text(v, "kb_knowledge_base")
        and f"Knowledge base: {field_text(v, 'kb_knowledge_base')}",
        field_text(v, "kb_category") and f"Category: {field_text(v, 'kb_category')}",
        field_text(v, "sys_updated_on") and f"Updated {field_text(v, 'sys_updated_on')}",
    )
    meta = " · ".join(p for p in facts if p)
    body = html_to_markdown(field_text(v, "text"), dialect="confluence") or "_No text._"
    return (
        f"# {title}\n\n{meta}\nLink: {url}\n\n{body}\n",
        {"kind": "knowledge_article", "number": number, "title": title, "servicenow_url": url},
    )


def servicenow_generic_page(
    record: dict[str, Any],
    *,
    table: str,
    label: str,
    url: str,
    max_chars: int = SERVICENOW_GENERIC_MAX_CHARS,
) -> tuple[str, dict[str, Any]]:
    """A row of a table that is not a task table: every filled-in non-``sys_`` field as a
    ``- field: value`` line, in name order, until ``max_chars`` (then ``- …``)."""
    sys_id = str(record.get("sys_id") or "")
    number = field_text(record, "number") or sys_id
    title = (
        field_text(record, "short_description")
        or field_text(record, "name")
        or field_text(record, "title")
        or number
    )
    lines, size = [f"# {label} {title}", "", f"Link: {url}", ""], 0
    for key in sorted(record):
        value = field_text(record, key)
        if key.startswith("sys_") or not value:
            continue
        line = f"- {key}: {value}"
        size += len(line)
        if size > max_chars:
            lines.append("- …")
            break
        lines.append(line)
    meta = {"kind": table, "number": number, "title": title, "servicenow_url": url}
    return "\n".join(lines).strip() + "\n", meta


def servicenow_task_page(
    record: dict[str, Any], *, table: str, label: str, url: str
) -> tuple[str, dict[str, Any]]:
    """A ServiceNow task record (incident, problem, change, request item, ...)."""
    v = record
    number = field_text(v, "number") or v.get("sys_id", "")
    title = field_text(v, "short_description")
    facts = [(name, field_text(v, f)) for name, f in _TASK_FACTS]
    lines = [
        f"# {label} {number}: {title}".rstrip(": "),
        "",
        " · ".join(f"{k}: {val}" for k, val in facts if val),
        f"Link: {url}",
    ]
    if field_text(v, "description"):
        lines += ["", "## Description", "", field_text(v, "description")]
    notes = field_text(v, "close_notes") or field_text(v, "resolution_notes")
    if notes:
        lines += ["", "## Resolution notes", "", notes]
    meta = {
        "kind": table,
        "number": number,
        "title": title,
        "state": field_text(v, "state"),
        "priority": field_text(v, "priority"),
        "assigned_to": field_text(v, "assigned_to"),
        "servicenow_url": url,
    }
    return "\n".join(lines).strip() + "\n", meta


def _person(value: dict[str, Any] | None) -> str:
    return (value or {}).get("displayName") or ""


def jira_issue_page(
    issue: dict[str, Any], comments: list[dict[str, Any]], *, url: str
) -> tuple[str, dict[str, Any]]:
    """A Jira issue (REST v3 ``fields``; description and comments in Atlassian Document
    Format) with its comments, oldest first."""
    f, key = issue.get("fields") or {}, issue.get("key", "")
    labels = [str(x) for x in f.get("labels") or []]
    meta = {
        "issue_key": key,
        "summary": f.get("summary") or "",
        "type": (f.get("issuetype") or {}).get("name", ""),
        "status": (f.get("status") or {}).get("name", ""),
        "priority": (f.get("priority") or {}).get("name", ""),
        "assignee": _person(f.get("assignee")),
        "reporter": _person(f.get("reporter")),
        "labels": labels,
        "created": f.get("created") or "",
        "updated": f.get("updated") or "",
        "project": (f.get("project") or {}).get("key", ""),
        "jira_url": url,
    }
    priority = f" · Priority: {meta['priority']}" if meta["priority"] else ""
    lines = [
        f"# {key}: {meta['summary']}",
        "",
        f"Type: {meta['type']} · Status: {meta['status']}{priority}",
        f"Assignee: {meta['assignee'] or 'Unassigned'} · Reporter: {meta['reporter'] or '—'}",
    ]
    if labels:
        lines.append(f"Labels: {', '.join(labels)}")
    lines += [
        f"Created {meta['created'][:10]} · Updated {meta['updated'][:10]}",
        f"Link: {url}",
        "",
        "## Description",
        "",
        adf_to_markdown(f.get("description")) or "_No description._",
    ]
    if comments:
        lines += ["", "## Comments", ""]
        for c in comments:
            author, created = _person(c.get("author")), (c.get("created") or "")[:10]
            lines += [f"**{author}** ({created}):", "", adf_to_markdown(c.get("body")), ""]
    return "\n".join(lines).strip() + "\n", meta


def file_page_header(location: str, key: str, size: int, modified: str, url: str) -> str:
    """Title, location facts and link of a file read from a bucket or drive (``key`` is
    its path there; ``size`` in bytes; ``modified`` an ISO timestamp)."""
    folder = key.rsplit("/", 1)[0] + "/" if "/" in key else ""
    facts = location + (f" · Folder: {folder}" if folder else "") + f" · {max(1, size // 1024)} KB"
    if modified:
        facts += f" · Last modified {modified[:10]}"
    return f"# {key.rsplit('/', 1)[-1]}\n\n{facts}\nLink: {url}\n"


def file_page(location: str, key: str, text: str, size: int, modified: str, url: str) -> str:
    """``file_page_header`` followed by the file's extracted text."""
    return f"{file_page_header(location, key, size, modified, url)}\n{text.strip()}\n"
