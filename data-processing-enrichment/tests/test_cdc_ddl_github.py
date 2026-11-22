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

"""CDC DDL statements that empty tables, and GitHub files / issues as Markdown (3.4.0)."""

from __future__ import annotations

from nexus_processing import (
    code_fence,
    ddl_cleared_tables,
    github_file_markdown,
    github_issue_markdown,
    is_markdown_path,
    parse_ddl,
)


def test_truncate_drop_and_rename_name_the_cleared_tables():
    assert ddl_cleared_tables("TRUNCATE TABLE orders", []) == ["orders"]
    assert ddl_cleared_tables("truncate `shop`.`orders`;", []) == ["orders"]
    assert ddl_cleared_tables("DROP TABLE IF EXISTS a, `b`, shop.c CASCADE", []) == ["a", "b", "c"]
    assert ddl_cleared_tables("DROP TEMPORARY TABLE tmp_x", []) == ["tmp_x"]
    assert ddl_cleared_tables("RENAME TABLE old1 TO new1, db.old2 to db.new2", []) == [
        "old1",
        "old2",
    ]
    assert ddl_cleared_tables('ALTER TABLE IF EXISTS ONLY "Orders" RENAME TO orders_v2') == [
        "Orders"
    ]
    assert ddl_cleared_tables("TRUNCATE ONLY t1, t2 RESTART IDENTITY", []) == ["t1", "t2"]


def test_comments_hints_quotes_and_several_statements():
    q = "/* app */ -- note\n# mysql comment\nTRUNCATE orders; DROP TABLE `odd,name`; SELECT 1"
    assert ddl_cleared_tables(q) == ["orders", "odd,name"]
    assert ddl_cleared_tables("/*!40101 TRUNCATE TABLE x */", []) == ["x"]
    assert ddl_cleared_tables("[dbo].[x]".join(["DROP TABLE ", ""]), []) == ["x"]
    assert ddl_cleared_tables('DROP TABLE "we""ird"', []) == ['we"ird']


def test_wanted_filter_and_non_ddl():
    q = "DROP TABLE orders, customers"
    assert ddl_cleared_tables(q, ["shop.Orders"]) == ["orders"]
    assert ddl_cleared_tables(q, ["invoices"]) == []
    for query in ("", "INSERT INTO t VALUES (1)", "ALTER TABLE t ADD COLUMN c int", "BEGIN"):
        assert ddl_cleared_tables(query, []) == []
    change = parse_ddl("RENAME TABLE a TO b")[0]
    assert change.verb == "rename" and change.renames == ((("a",), ("b",)),)


def test_markdown_files_keep_text_with_header_and_absolute_links():
    text = (
        "---\ntitle: Setup\n---\n# Setup\nSee [the guide](docs/guide.md#install) and "
        '![logo](../img/logo.png "Logo"), [site](https://x.io), [top](#setup).\n'
        "```md\n[raw](not/rewritten.md)\n```\n"
    )
    md = github_file_markdown("acme/app", "main", "docs/README.md", text)
    assert md.startswith("# docs/README.md\n\nRepository: acme/app · Branch: main\n")
    assert "Link: https://github.com/acme/app/blob/main/docs/README.md\n" in md
    assert "title: Setup\n\n# Setup" in md and "\n---\n" not in md
    assert "(https://github.com/acme/app/blob/main/docs/docs/guide.md#install)" in md
    assert '(https://raw.githubusercontent.com/acme/app/main/img/logo.png "Logo")' in md
    assert "[site](https://x.io)" in md and "[top](#setup)" in md
    assert "[raw](not/rewritten.md)" in md  # code is left alone
    plain = github_file_markdown("acme/app", "main", "README.md", "[a](b.md)", absolute_links=False)
    assert plain.endswith("[a](b.md)\n")


def test_mdx_and_code_files():
    mdx = "import Tabs from '@theme/Tabs';\nexport const x = 1;\n# Title\nBody\n"
    md = github_file_markdown("a/b", "dev", "docs/page.mdx", mdx)
    assert "import Tabs" not in md and "export const" not in md and "# Title\nBody" in md
    code = 'print("```")\n'
    md = github_file_markdown("a/b", "dev", "tools/run.py", code)
    assert "````python\n" + code + "````" in md
    assert code_fence("x") == "```\nx\n```"
    assert is_markdown_path("A/READ.ME.Markdown") and not is_markdown_path("notes.txt")


def test_issue_and_pull_request_markdown():
    item = {
        "number": 7,
        "title": "Login fails",
        "state": "closed",
        "user": {"login": "ann"},
        "created_at": "2026-01-02T03:04:05Z",
        "closed_at": "2026-01-05T00:00:00Z",
        "labels": [{"name": "bug"}, {"name": "p1"}],
        "html_url": "https://github.com/a/b/issues/7",
        "body": "Steps...",
    }
    comments = [{"user": {"login": "bob"}, "created_at": "2026-01-03", "body": "Repro'd"}]
    md = github_issue_markdown("a/b", item, comments)
    assert md.startswith("# Issue #7: Login fails\n\nRepository: a/b · State: closed")
    assert "Labels: bug, p1" in md and "Opened by ann on 2026-01-02 · Closed 2026-01-05" in md
    assert "## Comments\n\n**bob** (2026-01-03):\n\nRepro'd" in md
    pr = dict(item, pull_request={"merged_at": "2026-01-05"}, body="")
    reviews = [{"user": {"login": "cy"}, "state": "CHANGES_REQUESTED", "body": "Fix",
                "submitted_at": "2026-01-04"}, {"user": {"login": "dd"}, "body": ""}]  # fmt: skip
    notes = [{"user": {"login": "cy"}, "path": "app.py", "line": 3, "body": "typo"}]
    md = github_issue_markdown("a/b", pr, (), reviews, notes)
    assert md.startswith("# Pull request #7") and "State: merged" in md
    assert "_No description._" in md and "(changes requested, 2026-01-04)" in md
    assert "**dd**" not in md and "**cy** on `app.py` line 3" in md
