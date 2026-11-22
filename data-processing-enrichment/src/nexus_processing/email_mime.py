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

"""RFC 5322 e-mail (MIME) messages to header, body and attachment chunks."""

from __future__ import annotations

import email
import email.utils
import re
from dataclasses import dataclass, field
from email import policy
from html.parser import HTMLParser
from typing import Any


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
                    elif hasattr(sub, "as_bytes"):
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
                            fwd_chunk.narrative_text = f"[Forwarded] {fwd_chunk.narrative_text}"
                            forwarded_chunks.append(fwd_chunk)
                    except Exception:
                        pass
            # Image attachments: extract text via process_image_binary
            elif content_type.startswith("image/") and payload_data and auto_extract:
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
                                text=(f"[Image: {att_name}] " + " ".join(parts_list)),
                                narrative_text=(
                                    f"[Image Attachment: {att_name}] " + " ".join(parts_list)
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
                summary_m = re.search(r"SUMMARY:(.*?)$", cal_text, re.M)
                dtstart_m = re.search(r"DTSTART[^:]*:(.*?)$", cal_text, re.M)
                dtend_m = re.search(r"DTEND[^:]*:(.*?)$", cal_text, re.M)
                organizer_m = re.search(r"ORGANIZER[^:]*:(?:mailto:)?(.*?)$", cal_text, re.M)
                location_m = re.search(r"LOCATION:(.*?)$", cal_text, re.M)
                description_m = re.search(r"DESCRIPTION:(.*?)$", cal_text, re.M)

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
                narrative_text=f"{header_citation}\n{cal_text}",
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
