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

"""Source records rendered as Markdown pages (ServiceNow, Jira, cloud files)."""

from __future__ import annotations

from nexus_processing.record_pages import (
    field_text,
    file_page,
    file_page_header,
    jira_issue_page,
    servicenow_article_page,
    servicenow_generic_page,
    servicenow_task_page,
)

URL = "https://acme.service-now.com/x"


def test_field_text_reads_display_values_of_reference_fields():
    record = {
        "assigned_to": {"display_value": "Asha Rao", "link": "..."},
        "state": " New ",
        "n": None,
    }
    assert field_text(record, "assigned_to") == "Asha Rao"
    assert field_text(record, "state") == "New" and field_text(record, "n") == ""


def test_servicenow_task_page():
    record = {
        "sys_id": "abc",
        "number": "INC0010",
        "short_description": "VPN down",
        "state": "In Progress",
        "priority": "1 - Critical",
        "assigned_to": {"display_value": "Asha Rao"},
        "description": "Users cannot connect.",
        "close_notes": "",
        "resolution_notes": "Restarted the gateway.",
    }
    md, meta = servicenow_task_page(record, table="incident", label="Incident", url=URL)
    assert md == (
        "# Incident INC0010: VPN down\n\n"
        "State: In Progress · Priority: 1 - Critical · Assigned to: Asha Rao\n"
        f"Link: {URL}\n\n## Description\n\nUsers cannot connect.\n\n"
        "## Resolution notes\n\nRestarted the gateway.\n"
    )
    assert meta == {
        "kind": "incident",
        "number": "INC0010",
        "title": "VPN down",
        "state": "In Progress",
        "priority": "1 - Critical",
        "assigned_to": "Asha Rao",
        "servicenow_url": URL,
    }
    md, _ = servicenow_task_page({"sys_id": "s1"}, table="problem", label="Problem", url=URL)
    assert md.startswith("# Problem s1\n")


def test_servicenow_generic_page_lists_fields_and_caps_size():
    record = {"sys_id": "z9", "name": "Laptop", "sys_updated_on": "x", "b": "2", "a": "1", "c": ""}
    md, meta = servicenow_generic_page(record, table="alm_asset", label="Asset", url=URL)
    assert md == f"# Asset Laptop\n\nLink: {URL}\n\n- a: 1\n- b: 2\n- name: Laptop\n"
    assert meta["number"] == "z9" and meta["kind"] == "alm_asset"
    big = {"sys_id": "z", **{f"f{i:02d}": "v" * 50 for i in range(10)}}
    md, _ = servicenow_generic_page(big, table="t", label="T", url=URL, max_chars=120)
    assert md.rstrip().endswith("- …") and md.count("- f") == 2


def test_servicenow_article_page_renders_html_body():
    record = {
        "number": "KB001",
        "short_description": "Reset a password",
        "kb_knowledge_base": "IT",
        "text": "<p>Open <b>Settings</b>.</p><ul><li>Step one</li></ul>",
    }
    md, meta = servicenow_article_page(record, url=URL)
    assert md.startswith(
        f"# Reset a password\n\nKnowledge article KB001 · Knowledge base: IT\nLink: {URL}\n\n"
    )
    assert "Settings" in md and "- Step one" in md
    assert meta == {"kind": "knowledge_article", "number": "KB001", "title": "Reset a password",
                    "servicenow_url": URL}  # fmt: skip
    assert servicenow_article_page({"number": "KB2"}, url=URL)[0].endswith("_No text._\n")


def _adf(text: str) -> dict:
    return {
        "type": "doc",
        "content": [{"type": "paragraph", "content": [{"type": "text", "text": text}]}],
    }


def test_jira_issue_page_with_comments():
    issue = {
        "key": "OPS-7",
        "fields": {
            "summary": "Disk full",
            "issuetype": {"name": "Bug"},
            "status": {"name": "Open"},
            "priority": {"name": "High"},
            "assignee": {"displayName": "Ravi"},
            "labels": ["infra"],
            "created": "2026-11-01T10:00:00",
            "updated": "2026-11-02T10:00:00",
            "project": {"key": "OPS"},
            "description": _adf("The root volume is at 100%."),
        },
    }
    comments = [
        {
            "author": {"displayName": "Mei"},
            "created": "2026-11-02T09:00",
            "body": _adf("Cleared logs."),
        }
    ]
    md, meta = jira_issue_page(issue, comments, url="https://j/browse/OPS-7")
    assert md == (
        "# OPS-7: Disk full\n\nType: Bug · Status: Open · Priority: High\n"
        "Assignee: Ravi · Reporter: —\nLabels: infra\nCreated 2026-11-01 · Updated 2026-11-02\n"
        "Link: https://j/browse/OPS-7\n\n## Description\n\nThe root volume is at 100%.\n\n"
        "## Comments\n\n**Mei** (2026-11-02):\n\nCleared logs.\n"
    )
    assert meta["issue_key"] == "OPS-7" and meta["project"] == "OPS" and meta["labels"] == ["infra"]
    md, _ = jira_issue_page({"key": "A-1", "fields": {}}, [], url="u")
    assert "Assignee: Unassigned" in md and "_No description._" in md


def test_file_page_header_and_page():
    header = file_page_header(
        "Amazon S3 bucket docs", "hr/policies/leave.pdf", 5000, "2026-10-01T00:00", "s3://u"
    )
    assert header == (
        "# leave.pdf\n\nAmazon S3 bucket docs · Folder: hr/policies/ · 4 KB"
        " · Last modified 2026-10-01\n"
        "Link: s3://u\n"
    )
    assert (
        file_page("L", "a.txt", "  body \n", 10, "", "u")
        == "# a.txt\n\nL · 1 KB\nLink: u\n\nbody\n"
    )
