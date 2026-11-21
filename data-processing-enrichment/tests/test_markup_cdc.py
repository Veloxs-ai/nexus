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

# ruff: noqa: E501 - fixtures copied verbatim from the Nexora connector tests

"""Markup (HTML, Confluence storage, Atlassian Document Format), Notion blocks and CDC helpers."""

from __future__ import annotations

from nexus_processing.cdc import (
    ChangeEvent,
    apply_change,
    is_newer,
    mongo_change_event,
    mysql_row_event,
    normalize_change_event,
)
from nexus_processing.markup_adf import adf_to_markdown
from nexus_processing.markup_html import html_to_markdown
from nexus_processing.notion import (
    notion_blocks_to_markdown,
    notion_property_value,
    notion_rich_text,
)

STORAGE = """<h1>Deploy runbook</h1><p>Read <strong>this</strong> first. See <a href="https://status.acme.io">status</a>.</p>
<ul><li><p>Check CI</p><ul><li>All green</li></ul></li><li>Tag the release</li></ul><ol><li>Merge</li><li>Deploy</li></ol>
<table><tbody><tr><th><p>Service</p></th><th><p>Owner</p></th></tr><tr><td><p>API</p></td><td><p>Tom | Platform</p></td></tr></tbody></table>
<ac:structured-macro ac:name="code"><ac:parameter ac:name="language">bash</ac:parameter><ac:plain-text-body><![CDATA[acme deploy --env prod
acme verify]]></ac:plain-text-body></ac:structured-macro>
<ac:structured-macro ac:name="warning"><ac:rich-text-body><p>No deploys on Fridays after 15:00.</p></ac:rich-text-body></ac:structured-macro>
<ac:task-list><ac:task><ac:task-status>complete</ac:task-status><ac:task-body>Notify #deploys</ac:task-body></ac:task>
<ac:task><ac:task-status>incomplete</ac:task-status><ac:task-body>Update changelog</ac:task-body></ac:task></ac:task-list>
<p>See <ac:link><ri:page ri:content-title="Rollback guide" /></ac:link> — <ac:structured-macro ac:name="status"><ac:parameter ac:name="title">DONE</ac:parameter></ac:structured-macro></p>
<ac:structured-macro ac:name="toc" /><p><ac:image><ri:attachment ri:filename="arch.png" /></ac:image></p>"""


def t(text, *marks):
    return {
        "type": "text",
        "text": text,
        **({"marks": [m if isinstance(m, dict) else {"type": m} for m in marks]} if marks else {}),
    }


def p(*content):
    return {"type": "paragraph", "content": list(content)}


ADF = {
    "type": "doc",
    "version": 1,
    "content": [
        {"type": "heading", "attrs": {"level": 2}, "content": [t("Steps to reproduce")]},
        p(
            t("Open "),
            t("Settings", "strong"),
            t(" then "),
            t("Billing", "em"),
            t(". See "),
            t("runbook", {"type": "link", "attrs": {"href": "https://wiki.acme.io/rb"}}),
            t("."),
        ),
        {
            "type": "orderedList",
            "attrs": {"order": 1},
            "content": [
                {
                    "type": "listItem",
                    "content": [
                        p(t("Sign in")),
                        {
                            "type": "bulletList",
                            "content": [{"type": "listItem", "content": [p(t("as admin"))]}],
                        },
                    ],
                },
                {"type": "listItem", "content": [p(t("Click "), t("Export", "code"))]},
            ],
        },
        {
            "type": "codeBlock",
            "attrs": {"language": "python"},
            "content": [t("export(report)\nprint('ok')")],
        },
        {
            "type": "table",
            "content": [
                {
                    "type": "tableRow",
                    "content": [
                        {"type": "tableHeader", "content": [p(t("Env"))]},
                        {"type": "tableHeader", "content": [p(t("Result"))]},
                    ],
                },
                {
                    "type": "tableRow",
                    "content": [
                        {"type": "tableCell", "content": [p(t("staging"))]},
                        {"type": "tableCell", "content": [p(t("fails | 500"))]},
                    ],
                },
            ],
        },
        {
            "type": "panel",
            "attrs": {"panelType": "warning"},
            "content": [p(t("Customers are affected."))],
        },
        p(
            {"type": "mention", "attrs": {"text": "@Priya Shah"}},
            t(" please check "),
            {"type": "status", "attrs": {"text": "BLOCKED"}},
            t(" by "),
            {"type": "date", "attrs": {"timestamp": "1792540800000"}},
            {"type": "hardBreak"},
            t("Thanks"),
        ),
        {
            "type": "taskList",
            "content": [
                {"type": "taskItem", "attrs": {"state": "DONE"}, "content": [t("Reproduce")]},
                {"type": "taskItem", "attrs": {"state": "TODO"}, "content": [t("Fix")]},
            ],
        },
        {"type": "mediaSingle", "content": [{"type": "media", "attrs": {"id": "x"}}]},
        p({"type": "inlineCard", "attrs": {"url": "https://acme.atlassian.net/browse/ABC-2"}}),
    ],
}


def test_confluence_storage_format_becomes_markdown():
    md = html_to_markdown(STORAGE, dialect="confluence")
    assert "## Deploy runbook" in md
    assert "Read **this** first. See [status](https://status.acme.io)." in md
    assert "- Check CI\n  - All green\n- Tag the release" in md
    assert "1. Merge\n2. Deploy" in md
    assert "| Service | Owner |\n| --- | --- |\n| API | Tom \\| Platform |" in md
    assert "```bash\nacme deploy --env prod\nacme verify\n```" in md
    assert "> **Warning:** No deploys on Fridays after 15:00." in md
    assert "- [x] Notify #deploys" in md and "- [ ] Update changelog" in md
    assert "See Rollback guide — [DONE]" in md
    assert "[image: arch.png]" in md
    assert "toc" not in md and "ac:" not in md and "language" not in md


def test_html_drops_chrome_and_keeps_structure():
    html = (
        "<html><head><title>T</title><style>p{}</style><script>alert(1)</script></head><body>"
        "<nav>Home | About</nav><article><h1>Title</h1><p>Hello <b>world</b> and <a href='/x'>link</a>.</p>"
        "<div><p>Nested para</p><ul><li>one</li><li>two</li></ul></div>"
        "<table><tr><th>a</th><th>b</th></tr><tr><td>1</td><td>2</td></tr></table>"
        "<img src='x.png' alt='diagram'></article><footer>(c) 2026</footer><aside>ads</aside></body></html>"
    )
    md = html_to_markdown(html)
    assert md.startswith("# Title")
    assert "Hello **world** and [link](/x)." in md
    assert "Nested para\n\n- one\n- two" in md
    assert "| a | b |\n| --- | --- |\n| 1 | 2 |" in md
    assert "[image: diagram]" in md
    assert all(x not in md for x in ("alert", "Home | About", "(c) 2026", "ads", "p{}"))


def test_adf_becomes_markdown():
    md = adf_to_markdown(ADF)
    assert "### Steps to reproduce" in md
    assert "Open **Settings** then *Billing*. See [runbook](https://wiki.acme.io/rb)." in md
    assert "1. Sign in\n  - as admin\n2. Click `Export`" in md
    assert "```python\nexport(report)\nprint('ok')\n```" in md
    assert "| Env | Result |\n| --- | --- |\n| staging | fails \\| 500 |" in md
    assert "> **Warning:** Customers are affected." in md
    assert "@Priya Shah please check [BLOCKED] by 2026-10-21" in md and "Thanks" in md
    assert "- [x] Reproduce" in md and "- [ ] Fix" in md
    assert "[attachment]" in md and "<https://acme.atlassian.net/browse/ABC-2>" in md
    assert adf_to_markdown(None) == "" and adf_to_markdown("plain text") == "plain text"


def _rt(text):
    return [{"type": "text", "plain_text": text}]


def test_notion_blocks_render_through_a_children_callback():
    tree = {
        "page": [
            {"id": "h", "type": "heading_1", "heading_1": {"rich_text": _rt("Week one")}},
            {
                "id": "l",
                "type": "bulleted_list_item",
                "has_children": True,
                "bulleted_list_item": {"rich_text": _rt("Accounts")},
            },
            {
                "id": "n1",
                "type": "numbered_list_item",
                "numbered_list_item": {"rich_text": _rt("Slack")},
            },
            {
                "id": "n2",
                "type": "numbered_list_item",
                "numbered_list_item": {"rich_text": _rt("Email")},
            },
            {
                "id": "tb",
                "type": "table",
                "has_children": True,
                "table": {"has_column_header": True},
            },
            {"id": "db", "type": "child_database", "child_database": {"title": "Tasks"}},
        ],
        "l": [
            {
                "id": "l1",
                "type": "bulleted_list_item",
                "bulleted_list_item": {"rich_text": _rt("GitHub")},
            }
        ],
        "tb": [
            {"id": "r0", "type": "table_row", "table_row": {"cells": [_rt("Tool"), _rt("Owner")]}},
            {"id": "r1", "type": "table_row", "table_row": {"cells": [_rt("Jira"), _rt("Ops")]}},
        ],
    }
    databases: list[str] = []
    lines = notion_blocks_to_markdown(
        "page", lambda block_id: tree.get(block_id, []), databases=databases
    )
    text = "\n".join(lines)
    assert (
        "# Week one" in text and "- Accounts\n  - GitHub" in text and "1. Slack\n2. Email" in text
    )
    assert "| Tool | Owner |\n| --- | --- |\n| Jira | Ops |" in text and databases == ["db"]
    budget = [2]
    assert (
        "…(page truncated)"
        in notion_blocks_to_markdown("page", lambda b: tree.get(b, []), budget=budget)[-1]
    )


def test_notion_values():
    assert (
        notion_rich_text(
            [
                {
                    "type": "text",
                    "plain_text": "x",
                    "annotations": {"bold": True},
                    "href": "https://a",
                }
            ]
        )
        == "[**x**](https://a)"
    )
    pv = notion_property_value
    assert (
        pv({"type": "date", "date": {"start": "2026-01-01", "end": "2026-01-03"}})
        == "2026-01-01 → 2026-01-03"
    )
    assert pv({"type": "unique_id", "unique_id": {"prefix": "TASK", "number": 7}}) == "TASK-7"
    assert pv({"type": "relation", "relation": [{"id": "a"}, {"id": "b"}]}) == 2


def test_change_event_positions_order_redeliveries():
    old = normalize_change_event(
        {"payload": {"op": "u", "after": {"id": 1}, "source": {"lsn": "0/16B3748"}}}
    )
    new = normalize_change_event(
        {"payload": {"op": "u", "after": {"id": 1}, "source": {"lsn": 23803800}}}
    )
    assert old.source_position == "lsn:23803720" and is_newer(new, old) and not is_newer(old, new)
    a = normalize_change_event(
        mysql_row_event("db", "t", "update", {"id": 1}, ["id"], position="mysql-bin.000009:500")
    )
    b = normalize_change_event(
        mysql_row_event("db", "t", "update", {"id": 1}, ["id"], position="mysql-bin.000010:4")
    )
    assert (
        a.source_position == "binlog:mysql-bin.000009:500" and is_newer(b, a) and not is_newer(a, b)
    )
    m = normalize_change_event(
        mongo_change_event(
            {
                "_id": {"_data": "tok"},
                "operationType": "insert",
                "clusterTime": {"$timestamp": {"t": 5, "i": 2}},
                "documentKey": {"_id": "x"},
                "fullDocument": {"_id": "x"},
            }
        )
    )
    assert m.source_position == "clustertime:5:2"
    assert is_newer(m, None) and is_newer(m, "lsn:5")  # incomparable kinds: apply (at-least-once)


def test_apply_change_merges_partial_updates_and_deletes():
    partial = ChangeEvent(
        "UPDATE", "mongodb", "db", "c", "1", {"b": 2}, removed_fields=["c"], partial=True
    )
    assert apply_change({"a": 1, "c": 3}, partial) == {"a": 1, "b": 2}
    assert apply_change({"a": 1}, ChangeEvent("DELETE", "generic", "", "t", "1")) is None
    full = ChangeEvent("UPDATE", "generic", "", "t", "1", {"z": 1})
    assert apply_change({"a": 1}, full) == {"z": 1}
    assert mysql_row_event("db", "t", "insert", {"id": 7, "v": b"ab"}, ["id"])["primary_key"] == {
        "id": 7
    }
