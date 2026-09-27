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

"""Zero-dependency RFC 5322 Email MIME and Threaded Chat conversation processors."""

from __future__ import annotations

import email
import email.utils
import json
import re
from dataclasses import dataclass, field
from email import policy
from html.parser import HTMLParser
from typing import Any

__all__ = [
    "AttachmentInfo",
    "ChatConversationMetadata",
    "ChatConversationPayload",
    "ChatMessage",
    "ChatThread",
    "EmailChunk",
    "EmailMetadata",
    "EmailPayload",
    "process_chat_dialog",
    "process_email_binary",
]


class _HTMLTagStripper(HTMLParser):
    """Fast standard-library HTML parser that extracts clean plaintext."""

    def __init__(self) -> None:
        super().__init__()
        self._parts: list[str] = []

    def handle_data(self, data: str) -> None:
        self._parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag in ("p", "div", "h1", "h2", "h3", "h4", "h5", "h6", "li", "br", "tr"):
            self._parts.append(" ")

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "br":
            self._parts.append(" ")

    def get_text(self) -> str:
        raw = "".join(self._parts)
        # Normalize whitespace
        return re.sub(r"[ \t]+", " ", raw).strip()


def strip_html_tags(html_content: str) -> str:
    """Converts HTML markup into clean plaintext."""
    if not html_content:
        return ""
    stripper = _HTMLTagStripper()
    try:
        stripper.feed(html_content)
        return stripper.get_text()
    except Exception:
        # Fallback to regex tag stripping
        return re.sub(r"<[^>]+>", " ", html_content).strip()


@dataclass
class AttachmentInfo:
    """Metadata describing an attached document or media file."""

    filename: str
    content_type: str
    size_bytes: int


@dataclass
class EmailMetadata:
    """RFC 5322 email headers and container attributes."""

    filename: str
    format: str  # "eml"
    sender: str
    recipients: list[str]
    cc: list[str]
    bcc: list[str]
    subject: str
    date: str
    message_id: str
    in_reply_to: str
    references: list[str]
    attachments: list[AttachmentInfo]
    file_size_bytes: int


@dataclass
class EmailChunk:
    """Contextually grounded email text segment."""

    chunk_index: int
    text: str
    narrative_text: str


@dataclass
class EmailPayload:
    """Comprehensive parsed email container payload."""

    metadata: EmailMetadata
    body_plain: str
    body_html: str
    chunks: list[EmailChunk] = field(default_factory=list)
    attachments: list[AttachmentInfo] = field(default_factory=list)


@dataclass
class ChatMessage:
    """A single dialogue turn within a chat conversation."""

    message_id: str
    author: str
    text: str
    timestamp: str
    thread_id: str | None = None
    reply_to: str | None = None


@dataclass
class ChatThread:
    """A group of chronologically correlated messages sharing a thread root."""

    thread_id: str
    messages: list[ChatMessage]
    total_messages: int
    narrative_text: str


@dataclass
class ChatConversationMetadata:
    """Metadata describing a chat export or conversation channel."""

    conversation_name: str
    format: str  # "chat"
    total_threads: int
    total_messages: int
    unique_participants: list[str]
    file_size_bytes: int


@dataclass
class ChatConversationPayload:
    """Comprehensive processed chat conversation payload."""

    metadata: ChatConversationMetadata
    threads: list[ChatThread] = field(default_factory=list)


def process_email_binary(
    raw_bytes: bytes,
    filename: str = "message.eml",
    chunk_char_limit: int = 1500,
    ocr_provider: Any = None,
    auto_extract: bool = True,
) -> EmailPayload:
    """Parses an RFC 5322 MIME email message into headers, attachments, and narrative chunks.

    Args:
        raw_bytes: Raw binary email bytes.
        filename: Optional descriptive filename for grounding citations.
        chunk_char_limit: Maximum characters per body chunk (default: 1500).
        ocr_provider: Optional OCRProvider for extracting text from image attachments.
        auto_extract: When True (default), attempts OCR on image attachments.

    Returns:
        EmailPayload containing parsed headers, plain/HTML bodies, and grounded chunks.

    Raises:
        ValueError: If raw_bytes is empty or invalid.
    """
    if not raw_bytes:
        raise ValueError("Cannot process empty email bytes.")

    try:
        msg = email.message_from_bytes(raw_bytes, policy=policy.default)
    except Exception as exc:
        raise ValueError(f"Corrupted or invalid MIME email data: {exc}") from exc

    # 1. Extract Headers
    sender = str(msg.get("From", "")).strip()
    to_header = str(msg.get("To", "")).strip()
    cc_header = str(msg.get("Cc", "")).strip()
    bcc_header = str(msg.get("Bcc", "")).strip()
    subject = str(msg.get("Subject", "")).strip()
    date_str = str(msg.get("Date", "")).strip()
    msg_id = str(msg.get("Message-ID", "")).strip()
    in_reply_to = str(msg.get("In-Reply-To", "")).strip()
    references_header = str(msg.get("References", "")).strip()

    recipients = [addr for _, addr in email.utils.getaddresses([to_header]) if addr]
    cc = [addr for _, addr in email.utils.getaddresses([cc_header]) if addr]
    bcc = [addr for _, addr in email.utils.getaddresses([bcc_header]) if addr]
    references = [ref.strip() for ref in references_header.split() if ref.strip()]

    # 2. Extract Multipart Content & Attachments
    plain_parts: list[str] = []
    html_parts: list[str] = []
    attachments: list[AttachmentInfo] = []
    forwarded_chunks: list[EmailChunk] = []
    calendar_chunks: list[str] = []

    for part in msg.walk():
        content_disposition = str(part.get_content_disposition() or "").lower()
        content_type = part.get_content_type().lower()

        if part.is_attachment() or content_disposition == "attachment":
            att_name = part.get_filename() or "unnamed_attachment"
            payload_data = part.get_payload(decode=True)
            att_size = len(payload_data) if payload_data else 0
            attachments.append(
                AttachmentInfo(
                    filename=att_name,
                    content_type=content_type,
                    size_bytes=att_size,
                )
            )
            if content_type == "message/rfc822":
                nested_bytes = part.get_payload(decode=True)
                if nested_bytes is None:
                    # message/rfc822 may have sub-parts
                    sub = part.get_payload()
                    if isinstance(sub, list) and sub:
                        nested_bytes = sub[0].as_bytes()
                    elif hasattr(sub, 'as_bytes'):
                        nested_bytes = sub.as_bytes()
                if nested_bytes:
                    try:
                        nested_result = process_email_binary(
                            nested_bytes,
                            filename=f"forwarded_{att_name or 'message.eml'}",
                            chunk_char_limit=chunk_char_limit,
                        )
                        # Prefix forwarded chunks
                        for fwd_chunk in nested_result.chunks:
                            fwd_chunk.text = f"[Forwarded] {fwd_chunk.text}"
                            fwd_chunk.narrative_text = (
                                f"[Forwarded] {fwd_chunk.narrative_text}"
                            )
                            forwarded_chunks.append(fwd_chunk)
                    except Exception:
                        pass
            # Image attachments: extract text via process_image_binary
            elif (
                content_type.startswith("image/")
                and payload_data
                and auto_extract
            ):
                try:
                    from .images import process_image_binary

                    img_payload = process_image_binary(
                        payload_data,
                        filename=att_name,
                        ocr_provider=ocr_provider,
                        auto_extract=auto_extract,
                    )
                    parts_list: list[str] = []
                    if img_payload.metadata.ocr_text:
                        parts_list.append(img_payload.metadata.ocr_text)
                    if img_payload.metadata.caption:
                        parts_list.append(img_payload.metadata.caption)
                    if parts_list:
                        forwarded_chunks.append(
                            EmailChunk(
                                chunk_index=len(forwarded_chunks),
                                text=(
                                    f"[Image: {att_name}] "
                                    + " ".join(parts_list)
                                ),
                                narrative_text=(
                                    f"[Image Attachment: {att_name}] "
                                    + " ".join(parts_list)
                                ),
                            )
                        )
                except Exception:
                    pass
        elif content_type == "text/plain":
            try:
                content = part.get_content()
                if isinstance(content, str):
                    plain_parts.append(content.strip())
            except Exception:
                raw_p = part.get_payload(decode=True)
                if raw_p:
                    plain_parts.append(raw_p.decode("utf-8", errors="replace").strip())
        elif content_type == "text/html":
            try:
                content = part.get_content()
                if isinstance(content, str):
                    html_parts.append(content.strip())
            except Exception:
                raw_p = part.get_payload(decode=True)
                if raw_p:
                    html_parts.append(raw_p.decode("utf-8", errors="replace").strip())
        elif content_type == "text/calendar":
            cal_bytes = part.get_payload(decode=True)
            if cal_bytes:
                cal_text = cal_bytes.decode("utf-8", errors="replace")
                # Extract basic iCalendar fields
                summary_m = re.search(r'SUMMARY:(.*?)$', cal_text, re.M)
                dtstart_m = re.search(r'DTSTART[^:]*:(.*?)$', cal_text, re.M)
                dtend_m = re.search(r'DTEND[^:]*:(.*?)$', cal_text, re.M)
                organizer_m = re.search(r'ORGANIZER[^:]*:(?:mailto:)?(.*?)$', cal_text, re.M)
                location_m = re.search(r'LOCATION:(.*?)$', cal_text, re.M)
                description_m = re.search(r'DESCRIPTION:(.*?)$', cal_text, re.M)
                
                cal_parts = []
                summary = summary_m.group(1).strip() if summary_m else "Calendar Event"
                cal_parts.append(f"[Calendar Event: {summary}]")
                if organizer_m:
                    cal_parts.append(f"Organizer: {organizer_m.group(1).strip()}")
                if dtstart_m:
                    cal_parts.append(f"Start: {dtstart_m.group(1).strip()}")
                if dtend_m:
                    cal_parts.append(f"End: {dtend_m.group(1).strip()}")
                if location_m:
                    cal_parts.append(f"Location: {location_m.group(1).strip()}")
                if description_m:
                    cal_parts.append(f"Description: {description_m.group(1).strip()}")
                
                calendar_text = " | ".join(cal_parts)
                calendar_chunks.append(calendar_text)

    body_plain = "\n\n".join(plain_parts).strip()
    body_html = "\n\n".join(html_parts).strip()

    # Fallback to HTML stripping if plain text is empty
    if not body_plain and body_html:
        body_plain = strip_html_tags(body_html)

    # 3. Build Attachment Manifest Summary
    att_manifest = ""
    if attachments:
        att_items = [f"{a.filename} ({a.content_type}, {a.size_bytes}B)" for a in attachments]
        att_manifest = f"\nAttachments: {', '.join(att_items)}"

    # 4. Generate Narrative Header Citation
    header_citation = (
        f"[Email: {filename} | From: {sender} | To: {', '.join(recipients)} "
        f"| Subject: {subject} | Date: {date_str}]"
    )

    # 5. Chunking
    chunks: list[EmailChunk] = []
    if not body_plain:
        full_text = f"{header_citation}{att_manifest}".strip()
        chunks.append(
            EmailChunk(
                chunk_index=0,
                text="",
                narrative_text=full_text,
            )
        )
    else:
        # Split body if longer than chunk_char_limit
        lines = body_plain.split("\n")
        current_chunk_lines: list[str] = []
        current_len = 0
        chunk_idx = 0

        for line in lines:
            line_len = len(line) + 1
            if current_chunk_lines and (current_len + line_len > chunk_char_limit):
                chunk_body = "\n".join(current_chunk_lines).strip()
                narrative = (
                    f"{header_citation}\n{chunk_body}{att_manifest if chunk_idx == 0 else ''}"
                ).strip()
                chunks.append(
                    EmailChunk(
                        chunk_index=chunk_idx,
                        text=chunk_body,
                        narrative_text=narrative,
                    )
                )
                chunk_idx += 1
                current_chunk_lines = [line]
                current_len = line_len
            else:
                current_chunk_lines.append(line)
                current_len += line_len

        if current_chunk_lines:
            chunk_body = "\n".join(current_chunk_lines).strip()
            narrative = (
                f"{header_citation}\n{chunk_body}{att_manifest if chunk_idx == 0 else ''}"
            ).strip()
            chunks.append(
                EmailChunk(
                    chunk_index=chunk_idx,
                    text=chunk_body,
                    narrative_text=narrative,
                )
            )

    # 6. Safety split for overflow chunks
    MAX_CHUNK_CHARS = 3000
    final_chunks: list[EmailChunk] = []
    final_idx = 0
    for c in chunks:
        if len(c.text) <= MAX_CHUNK_CHARS:
            c.chunk_index = final_idx
            final_chunks.append(c)
            final_idx += 1
        else:
            # Split at word boundaries
            words = c.text.split()
            current = ""
            for word in words:
                if len(current) + len(word) + 1 > MAX_CHUNK_CHARS:
                    if current:
                        narr = (
                            c.narrative_text.replace(c.text, current.strip())
                            if c.text in c.narrative_text
                            else c.narrative_text
                        )
                        final_chunks.append(
                            EmailChunk(
                                chunk_index=final_idx,
                                text=current.strip(),
                                narrative_text=narr,
                            )
                        )
                        final_idx += 1
                    current = word
                else:
                    current = f"{current} {word}" if current else word
            if current:
                narr = (
                    c.narrative_text.replace(c.text, current.strip())
                    if c.text in c.narrative_text
                    else c.narrative_text
                )
                final_chunks.append(
                    EmailChunk(
                        chunk_index=final_idx,
                        text=current.strip(),
                        narrative_text=narr,
                    )
                )
                final_idx += 1

    for cal_text in calendar_chunks:
        final_chunks.append(
            EmailChunk(
                chunk_index=final_idx,
                text=cal_text,
                narrative_text=f"{header_citation}\n{cal_text}"
            )
        )
        final_idx += 1
        
    for fwd in forwarded_chunks:
        fwd.chunk_index = final_idx
        final_chunks.append(fwd)
        final_idx += 1
    
    chunks = final_chunks

    meta = EmailMetadata(
        filename=filename,
        format="eml",
        sender=sender,
        recipients=recipients,
        cc=cc,
        bcc=bcc,
        subject=subject,
        date=date_str,
        message_id=msg_id,
        in_reply_to=in_reply_to,
        references=references,
        attachments=attachments,
        file_size_bytes=len(raw_bytes),
    )

    return EmailPayload(
        metadata=meta,
        body_plain=body_plain,
        body_html=body_html,
        chunks=chunks,
        attachments=attachments,
    )


def process_chat_dialog(
    raw_input: bytes | str | list[dict[str, Any]],
    conversation_name: str = "chat_export",
    turns_per_window: int = 8,
) -> ChatConversationPayload:
    """Parses a multi-turn chat export (Slack, Microsoft Teams, JSON dialog)
    into structured threads.

    Args:
        raw_input: Raw JSON bytes/str or a pre-parsed list of message dictionaries.
        conversation_name: Channel or conversation descriptor for grounding citations.
        turns_per_window: Number of message turns to bundle per narrative chunk.

    Returns:
        ChatConversationPayload containing organized threads and grounded dialogue chunks.

    Raises:
        ValueError: If input cannot be parsed as a chat list or is empty.
    """
    raw_size = 0
    if isinstance(raw_input, bytes):
        raw_size = len(raw_input)
        try:
            parsed = json.loads(raw_input.decode("utf-8"))
        except json.JSONDecodeError as exc:
            raise ValueError(f"Corrupted or invalid JSON chat payload: {exc}") from exc
    elif isinstance(raw_input, str):
        raw_size = len(raw_input.encode("utf-8"))
        try:
            parsed = json.loads(raw_input)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Corrupted or invalid JSON chat string: {exc}") from exc
    elif isinstance(raw_input, list):
        parsed = raw_input
        raw_size = len(json.dumps(raw_input).encode("utf-8"))
    elif isinstance(raw_input, dict):
        raw_size = len(json.dumps(raw_input).encode("utf-8"))
        # Support Slack channel history wrap {"messages": [...]}
        parsed = raw_input.get("messages", [raw_input])
    else:
        raise ValueError(f"Unsupported chat input type: {type(raw_input)}")

    if not isinstance(parsed, list) or not parsed:
        raise ValueError("Chat payload must contain a non-empty list of message turns.")

    # 1. Normalize Message Turns
    messages: list[ChatMessage] = []
    participants: set[str] = set()

    for idx, item in enumerate(parsed, 1):
        if not isinstance(item, dict):
            continue

        author = (
            item.get("author")
            or item.get("user_name")
            or item.get("user")
            or item.get("sender")
            or "Unknown"
        )
        text = (
            item.get("text") or item.get("message") or item.get("content") or item.get("body") or ""
        )
        timestamp = str(item.get("timestamp") or item.get("ts") or item.get("date") or "")
        msg_id = str(item.get("message_id") or item.get("id") or item.get("client_msg_id") or idx)
        thread_id = item.get("thread_ts") or item.get("thread_id")
        reply_to = item.get("reply_to") or item.get("parent_id")

        if thread_id:
            thread_id = str(thread_id)
        if reply_to:
            reply_to = str(reply_to)

        participants.add(str(author))
        messages.append(
            ChatMessage(
                message_id=msg_id,
                author=str(author),
                text=str(text).strip(),
                timestamp=timestamp,
                thread_id=thread_id,
                reply_to=reply_to,
            )
        )

    # 2. Corroborate Thread Graph
    thread_map: dict[str, list[ChatMessage]] = {}
    standalone_counter = 0

    for msg in messages:
        if msg.thread_id:
            target_thread = msg.thread_id
        elif msg.reply_to:
            target_thread = msg.reply_to
        else:
            # Standalone sequential conversation
            standalone_counter += 1
            target_thread = f"thread_{standalone_counter // max(1, turns_per_window)}"
        thread_map.setdefault(target_thread, []).append(msg)

    # 3. Build Grounded Thread Dialogs
    threads: list[ChatThread] = []

    for t_id, t_messages in thread_map.items():
        dialogue_lines: list[str] = []
        for m in t_messages:
            time_tag = f" ({m.timestamp})" if m.timestamp else ""
            dialogue_lines.append(f"{m.author}{time_tag}: {m.text}")

        narrative = (
            f"[Chat: {conversation_name} | Thread: {t_id} | Turns: {len(t_messages)}]\n"
            + "\n".join(dialogue_lines)
        )
        threads.append(
            ChatThread(
                thread_id=t_id,
                messages=t_messages,
                total_messages=len(t_messages),
                narrative_text=narrative,
            )
        )

    meta = ChatConversationMetadata(
        conversation_name=conversation_name,
        format="chat",
        total_threads=len(threads),
        total_messages=len(messages),
        unique_participants=sorted(participants),
        file_size_bytes=raw_size,
    )

    return ChatConversationPayload(
        metadata=meta,
        threads=threads,
    )
