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

"""Zero-dependency, pure-Python ISO 32000-1 PDF binary parser and text extractor.

Parses PDF object dictionaries, decompresses /FlateDecode content streams using
standard library `zlib`, decodes PostScript text operators (BT, ET, Tj, TJ, Td),
and extracts page-by-page text with grounded point dimensions.
"""

from __future__ import annotations

import re
import zlib
from dataclasses import dataclass, field
from typing import Any


@dataclass
class PDFPage:
    page_number: int
    text: str
    page_label: str
    width_pts: float
    height_pts: float
    word_count: int
    char_count: int


@dataclass
class PDFMetadata:
    format: str
    version: str
    page_count: int
    title: str
    author: str
    is_encrypted: bool
    file_size_bytes: int
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class PDFPayload:
    metadata: PDFMetadata
    pages: list[PDFPage]

    @property
    def full_text(self) -> str:
        return "\n\n".join(p.text for p in self.pages if p.text.strip())


# =============================================================================
# 1. PostScript Text String & Operator Decoders
# =============================================================================
def decode_pdf_literal_string(raw: str) -> str:
    """Decodes PDF literal string with standard escape sequences (\\(, \\), \\n, etc.)."""
    out: list[str] = []
    i = 0
    raw_len = len(raw)
    while i < raw_len:
        c = raw[i]
        if c == "\\" and i + 1 < raw_len:
            nxt = raw[i + 1]
            if nxt == "n":
                out.append("\n")
                i += 2
            elif nxt == "r":
                out.append("\r")
                i += 2
            elif nxt == "t":
                out.append("\t")
                i += 2
            elif nxt == "b":
                out.append("\b")
                i += 2
            elif nxt == "f":
                out.append("\f")
                i += 2
            elif nxt in ("(", ")", "\\"):
                out.append(nxt)
                i += 2
            elif nxt.isdigit():
                # Octal sequence \ddd
                octal_digits = raw[i + 1 : min(raw_len, i + 4)]
                oct_val = 0
                count = 0
                for d in octal_digits:
                    if "0" <= d <= "7":
                        oct_val = oct_val * 8 + int(d)
                        count += 1
                    else:
                        break
                out.append(chr(oct_val))
                i += 1 + count
            else:
                out.append(nxt)
                i += 2
        else:
            out.append(c)
            i += 1
    return "".join(out)


def decode_pdf_hex_string(raw: str) -> str:
    """Decodes PDF hexadecimal string enclosed in <...>."""
    cleaned = re.sub(r"\s+", "", raw)
    if len(cleaned) % 2 != 0:
        cleaned += "0"
    try:
        raw_bytes = bytes.fromhex(cleaned)
        # Check for UTF-16BE BOM
        if raw_bytes.startswith(b"\xfe\xff"):
            return raw_bytes[2:].decode("utf-16-be", errors="replace")
        return raw_bytes.decode("latin1", errors="replace")
    except Exception:
        return ""


def extract_text_from_content_stream(content: bytes) -> str:
    """Parses decompressed PDF content stream tokens and extracts text operators."""
    try:
        stream_text = content.decode("latin1", errors="replace")
    except Exception:
        return ""

    lines: list[str] = []
    current_line: list[str] = []

    # Match text objects: BT ... ET
    bt_blocks = re.findall(r"BT\s*(.*?)\s*ET", stream_text, re.DOTALL)
    if not bt_blocks:
        # Fallback: parse operators across the entire stream
        bt_blocks = [stream_text]

    for block in bt_blocks:
        # Tokens can be:
        # 1. (string) Tj
        # 2. [(array)] TJ
        # 3. Td, TD, T*, ', " operators
        # Match TJ arrays: \[ (.*?) \] \s* TJ
        # Match Tj strings: \((.*?)\)\s*Tj or <(.*?)>\s*Tj
        pos = 0
        block_len = len(block)

        while pos < block_len:
            # Check for line breaks / positioning: Td, TD, T*
            m_break = re.match(
                r"(?:-?\d+(?:\.\d+)?\s+-?\d+(?:\.\d+)?\s+[Tt][Dd]|T\*|['\"])", block[pos:]
            )
            if m_break:
                if current_line:
                    lines.append(" ".join(current_line).strip())
                    current_line = []
                pos += m_break.end()
                continue

            # Check for array TJ: [...] TJ
            m_tj_arr = re.match(r"\[(.*?)\]\s*TJ", block[pos:], re.DOTALL)
            if m_tj_arr:
                inner = m_tj_arr.group(1)
                # Extract literal strings (...) and hex strings <...>
                parts: list[str] = []
                for lit in re.findall(r"\((.*?)(?<!\\)\)", inner, re.DOTALL):
                    decoded = decode_pdf_literal_string(lit).strip()
                    if decoded:
                        parts.append(decoded)
                for hx in re.findall(r"<([0-9a-fA-F]+)>", inner):
                    decoded = decode_pdf_hex_string(hx).strip()
                    if decoded:
                        parts.append(decoded)
                if parts:
                    current_line.append("".join(parts))
                pos += m_tj_arr.end()
                continue

            # Check for single string Tj: (...) Tj
            m_tj_lit = re.match(r"\((.*?)(?<!\\)\)\s*Tj", block[pos:], re.DOTALL)
            if m_tj_lit:
                decoded = decode_pdf_literal_string(m_tj_lit.group(1)).strip()
                if decoded:
                    current_line.append(decoded)
                pos += m_tj_lit.end()
                continue

            # Check for hex Tj: <...> Tj
            m_tj_hex = re.match(r"<([0-9a-fA-F]+)>\s*Tj", block[pos:])
            if m_tj_hex:
                decoded = decode_pdf_hex_string(m_tj_hex.group(1)).strip()
                if decoded:
                    current_line.append(decoded)
                pos += m_tj_hex.end()
                continue

            pos += 1

        if current_line:
            lines.append(" ".join(current_line).strip())
            current_line = []

    clean_lines = [line for line in lines if line]
    return "\n".join(clean_lines)


# =============================================================================
# 2. Pure-Python ISO 32000-1 Object Graph Scanner & Stream Decompressor
# =============================================================================
def parse_pdf_objects(data: bytes) -> dict[int, dict[str, Any]]:
    """Extracts indirect objects: N M obj << ... >> [stream ... endstream] endobj."""
    objects: dict[int, dict[str, Any]] = {}
    pattern = re.compile(rb"(\d+)\s+(\d+)\s+obj\s*(.*?)\s*endobj", re.DOTALL)

    for m in pattern.finditer(data):
        obj_num = int(m.group(1))
        body = m.group(3)

        # Check for stream
        stream_bytes = b""
        m_stream = re.search(rb"stream\r?\n(.*?)\r?\nendstream", body, re.DOTALL)
        if m_stream:
            stream_bytes = m_stream.group(1)
            dict_part = body[: m_stream.start()]
        else:
            dict_part = body

        dict_str = dict_part.decode("latin1", errors="replace")

        # Extract attributes from dictionary
        is_page = "/Type /Page" in dict_str and "/Type /Pages" not in dict_str
        is_catalog = "/Type /Catalog" in dict_str
        is_image_xobj = (
            "/Subtype /Image" in dict_str
            or "/Subtype/Image" in dict_str
        )

        # Contents reference: e.g. /Contents 10 0 R or /Contents [10 0 R 11 0 R]
        contents_ids: list[int] = []
        m_contents = re.search(r"/Contents\s+(\d+)\s+\d+\s+R", dict_str)
        if m_contents:
            contents_ids.append(int(m_contents.group(1)))
        else:
            m_contents_arr = re.search(r"/Contents\s*\[(.*?)\]", dict_str)
            if m_contents_arr:
                for ref in re.findall(r"(\d+)\s+\d+\s+R", m_contents_arr.group(1)):
                    contents_ids.append(int(ref))

        # XObject resource references on page (for image discovery)
        xobject_ids: list[int] = []
        m_xobj = re.search(r"/XObject\s*<<(.*?)>>", dict_str, re.DOTALL)
        if m_xobj:
            for ref in re.findall(r"(\d+)\s+\d+\s+R", m_xobj.group(1)):
                xobject_ids.append(int(ref))

        # MediaBox dimensions: [0 0 612 792]
        width_pts = 612.0
        height_pts = 792.0
        m_mbox = re.search(
            r"/MediaBox\s*\[\s*(-?\d+(?:\.\d+)?)\s+(-?\d+(?:\.\d+)?)\s+(-?\d+(?:\.\d+)?)\s+(-?\d+(?:\.\d+)?)\s*\]",
            dict_str,
        )
        if m_mbox:
            w = abs(float(m_mbox.group(3)) - float(m_mbox.group(1)))
            h = abs(float(m_mbox.group(4)) - float(m_mbox.group(2)))
            if w > 0 and h > 0:
                width_pts, height_pts = w, h

        # Detect compression filter
        is_flate = (
            "/Filter /FlateDecode" in dict_str
            or "/Filter/FlateDecode" in dict_str
        )
        is_lzw = "/Filter /LZWDecode" in dict_str
        is_a85 = (
            "/Filter /ASCII85Decode" in dict_str
            or "/Filter /ASCIIHexDecode" in dict_str
        )
        filter_type = "flate" if is_flate else (
            "lzw" if is_lzw else ("a85" if is_a85 else "none")
        )

        # Image properties (for XObject images)
        img_width = 0
        img_height = 0
        if is_image_xobj:
            wm = re.search(r"/Width\s+(\d+)", dict_str)
            hm = re.search(r"/Height\s+(\d+)", dict_str)
            if wm:
                img_width = int(wm.group(1))
            if hm:
                img_height = int(hm.group(1))

        objects[obj_num] = {
            "dict_str": dict_str,
            "stream_bytes": stream_bytes,
            "is_page": is_page,
            "is_catalog": is_catalog,
            "is_flate": is_flate,
            "is_image_xobj": is_image_xobj,
            "filter_type": filter_type,
            "contents_ids": contents_ids,
            "xobject_ids": xobject_ids,
            "width_pts": width_pts,
            "height_pts": height_pts,
            "img_width": img_width,
            "img_height": img_height,
            "raw": body,
            "obj_num": obj_num,
        }

    return objects


def decompress_stream(
    stream_bytes: bytes, filter_type: str = "flate"
) -> bytes:
    """Decompresses PDF stream data (FlateDecode, LZWDecode, ASCII85)."""
    if not stream_bytes:
        return b""
    if filter_type == "flate":
        try:
            return zlib.decompress(stream_bytes)
        except Exception:
            try:
                return zlib.decompress(stream_bytes, -zlib.MAX_WBITS)
            except Exception:
                return stream_bytes
    if filter_type == "a85":
        # ASCII85 / ASCIIHex decode
        try:
            import base64
            return base64.a85decode(stream_bytes, adobe=True)
        except Exception:
            # Try ASCIIHex: pairs of hex digits
            try:
                hex_str = stream_bytes.decode("ascii", errors="ignore")
                hex_str = hex_str.replace(">", "").strip()
                return bytes.fromhex(hex_str)
            except Exception:
                return stream_bytes
    return stream_bytes


def _extract_image_bytes(obj: dict[str, Any]) -> bytes | None:
    """Extracts raw image bytes from a PDF Image XObject."""
    if not obj.get("is_image_xobj") or not obj.get("stream_bytes"):
        return None
    ft = obj.get("filter_type", "none")
    raw = obj["stream_bytes"]
    # DCTDecode = JPEG, JPXDecode = JPEG2000 — already valid image bytes
    ds = obj.get("dict_str", "")
    if "/Filter /DCTDecode" in ds or "/Filter/DCTDecode" in ds:
        return raw  # Already JPEG
    if "/Filter /JPXDecode" in ds:
        return raw  # Already JPEG2000
    # FlateDecode images need decompression
    if ft == "flate":
        return decompress_stream(raw, "flate")
    return raw


def process_pdf_binary(
    data: bytes,
    ocr_provider: Any = None,
    auto_extract: bool = True,
) -> PDFPayload:
    """Universal pure-Python entry point for parsing and extracting text from PDF bytes."""
    # 1. Extract PDF version header
    m_ver = re.search(rb"%PDF-(\d+\.\d+)", data[:64])
    version = m_ver.group(1).decode("ascii") if m_ver else "1.4"
    file_size_bytes = len(data)

    # 2. Parse indirect object graph
    objects = parse_pdf_objects(data)

    # 3. Identify page objects
    page_objs = sorted(
        [obj for obj in objects.values() if obj["is_page"]],
        key=lambda o: o.get("obj_num", 0),
    )
    if not page_objs:
        # If /Type /Page was omitted or indirect, find objects with /Contents or /MediaBox
        page_objs = sorted(
            [obj for obj in objects.values() if obj["contents_ids"]],
            key=lambda o: o.get("obj_num", 0),
        )

    pages: list[PDFPage] = []

    for idx, p_obj in enumerate(page_objs, start=1):
        page_text_parts: list[str] = []

        # If page object has its own stream
        if p_obj["stream_bytes"]:
            ft = p_obj.get("filter_type", "flate")
            decomp = decompress_stream(p_obj["stream_bytes"], ft)
            txt = extract_text_from_content_stream(decomp)
            if txt:
                page_text_parts.append(txt)

        # Decompress referenced content streams
        for c_id in p_obj["contents_ids"]:
            target = objects.get(c_id)
            if target and target["stream_bytes"]:
                ft = target.get("filter_type", "flate")
                decomp = decompress_stream(target["stream_bytes"], ft)
                txt = extract_text_from_content_stream(decomp)
                if txt:
                    page_text_parts.append(txt)

        # Extract text from embedded images via process_image_binary
        if not page_text_parts and auto_extract:
            from .images import process_image_binary

            for xobj_id in p_obj.get("xobject_ids", []):
                xobj = objects.get(xobj_id)
                if xobj and xobj.get("is_image_xobj"):
                    img_bytes = _extract_image_bytes(xobj)
                    if not img_bytes:
                        continue
                    try:
                        payload = process_image_binary(
                            img_bytes,
                            ocr_provider=ocr_provider,
                            auto_extract=auto_extract,
                        )
                        parts: list[str] = []
                        if payload.metadata.ocr_text:
                            parts.append(payload.metadata.ocr_text)
                        if payload.metadata.caption:
                            parts.append(payload.metadata.caption)
                        if parts:
                            page_text_parts.append(
                                f"[OCR Image] {' '.join(parts)}"
                            )
                        else:
                            w = payload.metadata.width
                            h = payload.metadata.height
                            page_text_parts.append(
                                f"[Embedded Image: {w}x{h}px]"
                            )
                    except Exception:
                        w = xobj.get("img_width", 0)
                        h = xobj.get("img_height", 0)
                        page_text_parts.append(
                            f"[Embedded Image: {w}x{h}px]"
                        )

        page_text = "\n".join(page_text_parts).strip()
        word_count = len(page_text.split()) if page_text else 0
        char_count = len(page_text)

        pages.append(
            PDFPage(
                page_number=idx,
                text=page_text,
                page_label=f"[Page {idx}]",
                width_pts=p_obj["width_pts"],
                height_pts=p_obj["height_pts"],
                word_count=word_count,
                char_count=char_count,
            )
        )

    # Fallback if no pages were extracted from object graph
    if not pages:
        # Direct stream scan fallback
        stream_texts: list[str] = []
        for m_str in re.finditer(rb"stream\r?\n(.*?)\r?\nendstream", data, re.DOTALL):
            decomp = decompress_stream(m_str.group(1), "flate")
            txt = extract_text_from_content_stream(decomp)
            if txt:
                stream_texts.append(txt)

        full_raw = "\n\n".join(stream_texts).strip()
        pages.append(
            PDFPage(
                page_number=1,
                text=full_raw,
                page_label="[Page 1]",
                width_pts=612.0,
                height_pts=792.0,
                word_count=len(full_raw.split()) if full_raw else 0,
                char_count=len(full_raw),
            )
        )

    # Extract /Info metadata (title, author, subject, creator)
    title = ""
    author = ""
    for obj in objects.values():
        raw = obj.get("raw", "")
        if isinstance(raw, bytes):
            raw = raw.decode("latin-1", errors="replace")
        # Check for /Info reference or inline /Title /Author
        if "/Title" in raw:
            title_m = re.search(r'/Title\s*\(([^)]*)\)', raw)
            if title_m and not title:
                title = decode_pdf_literal_string(title_m.group(1))
            # Also try hex string format
            if not title:
                title_hex = re.search(r'/Title\s*<([0-9a-fA-F]*)>', raw)
                if title_hex:
                    title = decode_pdf_hex_string(title_hex.group(1))
        if "/Author" in raw:
            author_m = re.search(r'/Author\s*\(([^)]*)\)', raw)
            if author_m and not author:
                author = decode_pdf_literal_string(author_m.group(1))
            if not author:
                author_hex = re.search(r'/Author\s*<([0-9a-fA-F]*)>', raw)
                if author_hex:
                    author = decode_pdf_hex_string(author_hex.group(1))

    meta = PDFMetadata(
        format="PDF",
        version=version,
        page_count=len(pages),
        title=title,
        author=author,
        is_encrypted=b"/Encrypt" in data,
        file_size_bytes=file_size_bytes,
        details={"extracted_pages": len(pages)},
    )

    return PDFPayload(metadata=meta, pages=pages)
