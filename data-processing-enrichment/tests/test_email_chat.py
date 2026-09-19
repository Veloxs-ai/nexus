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

import json

import pytest

from nexus_processing.email_chat import (
    process_chat_dialog,
    process_email_binary,
    strip_html_tags,
)


def make_test_eml(
    sender: str = "alice@example.com",
    subject: str = "Architecture Review",
    body: str = "Please review the updated 3072D vector specifications.",
    include_attachment: bool = True,
) -> bytes:
    """Constructs a valid RFC 5322 MIME email message."""
    parts = [
        f"From: {sender}",
        "To: bob@example.com, charlie@example.com",
        "Cc: lead@example.com",
        f"Subject: {subject}",
        "Date: Mon, 15 Sep 2026 09:00:00 +0000",
        "Message-ID: <msg_001@example.com>",
        "In-Reply-To: <parent_msg@example.com>",
        "References: <root_msg@example.com> <parent_msg@example.com>",
        'Content-Type: multipart/mixed; boundary="NEXUS_BOUNDARY"',
        "",
        "--NEXUS_BOUNDARY",
        'Content-Type: text/plain; charset="utf-8"',
        "",
        body,
        "",
    ]
    if include_attachment:
        parts.extend(
            [
                "--NEXUS_BOUNDARY",
                "Content-Type: application/pdf",
                'Content-Disposition: attachment; filename="spec.pdf"',
                "",
                "BINARY_PDF_MOCK_DATA",
                "",
            ]
        )
    parts.extend(["--NEXUS_BOUNDARY--", ""])
    return "\r\n".join(parts).encode("utf-8")


def make_test_html_eml() -> bytes:
    """Constructs a valid HTML-only MIME email message."""
    parts = [
        "From: notifications@corp.internal",
        "To: team@corp.internal",
        "Subject: Weekly Status Digest",
        "Date: Tue, 16 Sep 2026 12:00:00 +0000",
        'Content-Type: text/html; charset="utf-8"',
        "",
        "<html><body><h1>Status Report</h1><p>All pipeline stages are healthy.</p></body></html>",
        "",
    ]
    return "\r\n".join(parts).encode("utf-8")


def test_strip_html_tags():
    """Validates fast HTML tag removal into clean plaintext."""
    assert strip_html_tags("<p>Hello <b>World</b>!</p>") == "Hello World!"
    assert strip_html_tags("") == ""


def test_process_email_validation():
    """Validates error handling on invalid or empty email payloads."""
    with pytest.raises(ValueError, match="Cannot process empty email bytes"):
        process_email_binary(b"")


def test_process_email_multipart_plain_and_attachment():
    """Validates RFC 5322 MIME multipart parsing, attachments, and narrative chunks."""
    raw = make_test_eml()
    payload = process_email_binary(raw, filename="review.eml")

    assert payload.metadata.format == "eml"
    assert payload.metadata.sender == "alice@example.com"
    assert payload.metadata.recipients == ["bob@example.com", "charlie@example.com"]
    assert payload.metadata.cc == ["lead@example.com"]
    assert payload.metadata.subject == "Architecture Review"
    assert payload.metadata.in_reply_to == "<parent_msg@example.com>"
    assert len(payload.metadata.references) == 2

    # Attachments
    assert len(payload.attachments) == 1
    att = payload.attachments[0]
    assert att.filename == "spec.pdf"
    assert att.content_type == "application/pdf"
    assert att.size_bytes > 0

    # Chunks and narrative citation
    assert len(payload.chunks) == 1
    chk = payload.chunks[0]
    assert "[Email: review.eml | From: alice@example.com" in chk.narrative_text
    assert "Please review the updated 3072D vector specifications." in chk.narrative_text
    assert "Attachments: spec.pdf" in chk.narrative_text


def test_process_email_html_fallback():
    """Validates fallback to HTML parsing when plain text is absent."""
    raw = make_test_html_eml()
    payload = process_email_binary(raw, filename="status.eml")

    assert payload.metadata.subject == "Weekly Status Digest"
    assert "All pipeline stages are healthy." in payload.body_plain
    assert len(payload.chunks) == 1
    assert "Status Report All pipeline stages are healthy." in payload.chunks[0].narrative_text


def test_process_chat_dialog_validation():
    """Validates error handling for empty or malformed chat exports."""
    with pytest.raises(ValueError, match="Chat payload must contain a non-empty list"):
        process_chat_dialog([])

    with pytest.raises(ValueError, match="Corrupted or invalid JSON chat payload"):
        process_chat_dialog(b"INVALID_JSON{")


def test_process_chat_dialog_slack_and_teams():
    """Validates thread grouping, reply linking, and narrative dialogue generation."""
    chat_events = [
        {
            "user_name": "Alice",
            "text": "Starting cluster deployment v2",
            "ts": "1726000000.001000",
            "thread_ts": "1726000000.001000",
        },
        {
            "user_name": "Bob",
            "text": "Nodes 1-4 provisioned successfully",
            "ts": "1726000010.002000",
            "thread_ts": "1726000000.001000",
        },
        {
            "user_name": "Carol",
            "text": "Standup reminder at 10 AM",
            "ts": "1726000020.003000",
        },
        {
            "user_name": "Bob",
            "text": "Load balancer health checks passed",
            "ts": "1726000030.004000",
            "thread_ts": "1726000000.001000",
        },
    ]

    payload = process_chat_dialog(
        chat_events,
        conversation_name="#engineering",
        turns_per_window=5,
    )

    assert payload.metadata.format == "chat"
    assert payload.metadata.conversation_name == "#engineering"
    assert payload.metadata.total_messages == 4
    assert sorted(payload.metadata.unique_participants) == ["Alice", "Bob", "Carol"]
    assert payload.metadata.total_threads == 2

    # Thread 1: 3 turns (Alice -> Bob -> Bob)
    t1 = next(t for t in payload.threads if t.thread_id == "1726000000.001000")
    assert t1.total_messages == 3
    assert "[Chat: #engineering | Thread: 1726000000.001000 | Turns: 3]" in t1.narrative_text
    assert "Alice (1726000000.001000): Starting cluster deployment v2" in t1.narrative_text
    assert "Bob (1726000010.002000): Nodes 1-4 provisioned successfully" in t1.narrative_text

    # Also test JSON string input
    payload_json = process_chat_dialog(
        json.dumps(chat_events),
        conversation_name="#engineering",
    )
    assert payload_json.metadata.total_messages == 4
