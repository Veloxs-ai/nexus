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

from __future__ import annotations

import json
import math

from nexus.client import NexusClient


def make_test_eml() -> bytes:
    """Generates a valid MIME email message containing PII."""
    parts = [
        "From: Alice Cooper <alice.cooper@example.com>",
        "To: Bob Marley <bob.marley@example.com>",
        "Subject: Project Confidential Briefing",
        "Date: Mon, 15 Sep 2026 10:00:00 +0000",
        "Message-ID: <briefing_01@example.com>",
        'Content-Type: text/plain; charset="utf-8"',
        "",
        "Hello Bob, please send the contract to contact.lawyer@example.com immediately.",
        "",
    ]
    return "\r\n".join(parts).encode("utf-8")


def make_test_chat() -> list[dict[str, str]]:
    """Generates a multi-turn chat dialog containing PII."""
    return [
        {
            "user": "Dave",
            "text": "Hey team, reaching out from dave.ops@example.com",
            "ts": "1726000000",
            "thread_ts": "1726000000",
        },
        {
            "user": "Eve",
            "text": "Acknowledged Dave, deployment running smoothly.",
            "ts": "1726000060",
            "thread_ts": "1726000000",
        },
    ]


def test_nexus_client_process_email():
    """Validates NexusClient.process_email 5-stage telemetry traces and 3072D vector projections."""
    client = NexusClient()
    raw = make_test_eml()

    doc = client.process_email(
        email_id="doc_email_1",
        name="briefing.eml",
        email_bytes=raw,
        metadata={"confidential": True},
        enable_guardrails=True,
    )

    assert doc.document_id == "doc_email_1"
    assert doc.file_type == "email"
    assert doc.metadata["sender"] == "Alice Cooper <alice.cooper@example.com>"
    assert doc.metadata["subject"] == "Project Confidential Briefing"
    assert len(doc.chunks) == 1

    # 5-stage trace validation
    assert len(doc.execution_trace) == 5
    stage_names = [t.stage_name for t in doc.execution_trace]
    assert stage_names == [
        "MIME Container & Header Graph Parsing",
        "Multipart Body & Attachment Graph Extraction",
        "Thread Reference & Chronological Reconstruction",
        "Safety Guardrails & PII Sanitization",
        "Email-Grounded 3072D Vector Projection",
    ]
    for t in doc.execution_trace:
        assert t.status == "completed"
        assert t.duration_ms >= 0.0

    # 3072D vector norm verification
    chunk = doc.chunks[0]
    assert chunk.metadata["subject"] == "Project Confidential Briefing"
    assert chunk.embedding is not None
    assert len(chunk.embedding) == 3072
    l2_norm = math.sqrt(sum(x * x for x in chunk.embedding))
    assert math.isclose(l2_norm, 1.0, rel_tol=1e-5)

    # PII sanitization (email masked)
    assert "contact.lawyer@example.com" not in chunk.text
    assert "[EMAIL]" in chunk.text


def test_nexus_client_process_chat():
    """Validates NexusClient.process_chat 5-stage telemetry traces and 3072D vector projections."""
    client = NexusClient()
    dialog = make_test_chat()

    doc = client.process_chat(
        chat_id="doc_chat_1",
        conversation_name="#infrastructure",
        chat_data=dialog,
        metadata={"environment": "production"},
        enable_guardrails=True,
    )

    assert doc.document_id == "doc_chat_1"
    assert doc.file_type == "chat"
    assert doc.metadata["total_messages"] == 2
    assert doc.metadata["total_threads"] == 1
    assert len(doc.chunks) == 1

    # 5-stage trace validation
    assert len(doc.execution_trace) == 5
    stage_names = [t.stage_name for t in doc.execution_trace]
    assert stage_names == [
        "Chat Schema Discovery & Turn Ingestion",
        "Thread Graph & Reply Corroboration",
        "Chronological Dialogue Window Framing",
        "Safety Guardrails & PII Sanitization",
        "Dialogue-Grounded 3072D Vector Projection",
    ]
    for t in doc.execution_trace:
        assert t.status == "completed"

    chunk = doc.chunks[0]
    assert chunk.metadata["thread_id"] == "1726000000"
    assert chunk.embedding is not None
    assert len(chunk.embedding) == 3072
    l2_norm = math.sqrt(sum(x * x for x in chunk.embedding))
    assert math.isclose(l2_norm, 1.0, rel_tol=1e-5)

    # PII sanitization check
    assert "dave.ops@example.com" not in chunk.text
    assert "[EMAIL]" in chunk.text


def test_nexus_client_process_document_email_and_chat_routing():
    """Validates auto-routing in NexusClient.process_document for eml and chat formats."""
    client = NexusClient()

    eml_bytes = make_test_eml()
    doc_eml = client.process_document(
        document_id="auto_eml",
        text=eml_bytes,
        name="email.eml",
    )
    assert doc_eml.file_type == "email"
    assert len(doc_eml.chunks) == 1

    chat_events = make_test_chat()
    doc_chat = client.process_document(
        document_id="auto_chat",
        text=json.dumps(chat_events),
        name="export.chat",
    )
    assert doc_chat.file_type == "chat"
    assert len(doc_chat.chunks) == 1
