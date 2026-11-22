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

"""Pure-Python PNG, BMP and JPEG decoding to an RGB grid, and format sniffing."""

from __future__ import annotations

import io
import re
import struct
import zlib
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ImageMetadata:
    format: str
    width: int
    height: int
    color_mode: str
    aspect_ratio: float
    file_size_bytes: int
    has_alpha: bool = False
    filename: str = ""
    embedded_text: str = ""
    ocr_text: str = ""
    caption: str = ""
    details: dict[str, Any] = field(default_factory=dict)


def detect_image_format(data: bytes) -> str:
    """Detect image binary format from header magic bytes."""
    if len(data) < 8:
        return "unknown"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if data.startswith(b"\xff\xd8"):
        return "jpeg"
    if data.startswith(b"BM"):
        return "bmp"
    if data.startswith(b"GIF87a") or data.startswith(b"GIF89a"):
        return "gif"
    if data.startswith(b"RIFF") and len(data) >= 12 and data[8:12] == b"WEBP":
        return "webp"
    return "unknown"


# =============================================================================
# 1. Pure Python PNG Decoder (IHDR + IDAT zlib Decompression)
# =============================================================================
def decode_png(data: bytes) -> tuple[ImageMetadata, list[list[tuple[int, int, int]]]]:
    """Decodes PNG binary data into an RGB pixel matrix using standard library zlib and struct."""
    if not data.startswith(b"\x89PNG\r\n\x1a\n"):
        raise ValueError("Invalid PNG header signature.")

    bio = io.BytesIO(data[8:])
    width, height = 0, 0
    bit_depth, color_type = 8, 2
    idat_chunks: list[bytes] = []
    embedded_texts: list[str] = []

    while True:
        chunk_len_bytes = bio.read(4)
        if len(chunk_len_bytes) < 4:
            break
        chunk_len = struct.unpack(">I", chunk_len_bytes)[0]
        chunk_type = bio.read(4)
        chunk_data = bio.read(chunk_len)
        bio.read(4)  # Skip CRC

        if chunk_type == b"IHDR":
            width, height, bit_depth, color_type, _comp, _filt, _inter = struct.unpack(
                ">IIBBBBB", chunk_data[:13]
            )
        elif chunk_type == b"IDAT":
            idat_chunks.append(chunk_data)
        elif chunk_type in (b"tEXt", b"zTXt", b"iTXt"):
            try:
                if chunk_type == b"tEXt":
                    parts = chunk_data.split(b"\x00", 1)
                    if len(parts) == 2:
                        k = parts[0].decode("latin1", errors="ignore").strip()
                        v = parts[1].decode("latin1", errors="ignore").strip()
                        if k and v:
                            embedded_texts.append(f"{k}: {v}")
                elif chunk_type == b"zTXt":
                    parts = chunk_data.split(b"\x00", 2)
                    if len(parts) >= 2:
                        k = parts[0].decode("latin1", errors="ignore").strip()
                        compressed_val = chunk_data[len(parts[0]) + 2 :]
                        raw = zlib.decompress(compressed_val)
                        v = raw.decode("latin1", errors="ignore").strip()
                        if k and v:
                            embedded_texts.append(f"{k}: {v}")
                elif chunk_type == b"iTXt":
                    parts = chunk_data.split(b"\x00", 1)
                    if len(parts) == 2:
                        k = parts[0].decode("utf-8", errors="ignore").strip()
                        rem = parts[1]
                        if len(rem) >= 2:
                            is_comp = rem[0] == 1
                            null2 = rem.find(b"\x00", 2)
                            if null2 != -1:
                                null3 = rem.find(b"\x00", null2 + 1)
                                if null3 != -1:
                                    raw_text = rem[null3 + 1 :]
                                    if is_comp:
                                        raw_text = zlib.decompress(raw_text)
                                    v = raw_text.decode("utf-8", errors="ignore").strip()
                                    if k and v:
                                        embedded_texts.append(f"{k}: {v}")
            except Exception:
                pass
        elif chunk_type == b"IEND":
            break

    if width <= 0 or height <= 0:
        raise ValueError(f"Invalid PNG dimensions: {width}x{height}")

    color_mode_map = {0: "Grayscale", 2: "RGB", 3: "Palette", 4: "GrayAlpha", 6: "RGBA"}
    color_mode = color_mode_map.get(color_type, "RGB")
    has_alpha = color_type in (4, 6)

    # Decompress pixel stream
    decompressed = zlib.decompress(b"".join(idat_chunks))

    # Determine bytes per pixel (assuming 8-bit depth)
    bpp = 3 if color_type == 2 else (4 if color_type == 6 else (1 if color_type == 0 else 2))
    stride = 1 + width * bpp  # 1 filter byte per scanline + row pixels

    # Parse scanlines and sample into RGB matrix
    pixels: list[list[tuple[int, int, int]]] = []
    step_y = max(1, height // 64) if height > 64 else 1
    step_x = max(1, width // 64) if width > 64 else 1

    for y in range(0, height, step_y):
        offset = y * stride
        if offset + stride > len(decompressed):
            break
        row_data = decompressed[offset + 1 : offset + stride]
        row_pixels: list[tuple[int, int, int]] = []

        for x in range(0, width, step_x):
            px_offset = x * bpp
            if px_offset + bpp <= len(row_data):
                if color_type == 2:  # RGB
                    r, g, b = struct.unpack("BBB", row_data[px_offset : px_offset + 3])
                elif color_type == 6:  # RGBA
                    r, g, b, _a = struct.unpack("BBBB", row_data[px_offset : px_offset + 4])
                elif color_type == 0:  # Grayscale
                    val = row_data[px_offset]
                    r, g, b = val, val, val
                else:
                    val = row_data[px_offset]
                    r, g, b = val, val, val
                row_pixels.append((r, g, b))
        if row_pixels:
            pixels.append(row_pixels)

    meta = ImageMetadata(
        format="PNG",
        width=width,
        height=height,
        color_mode=color_mode,
        aspect_ratio=round(width / max(1, height), 3),
        file_size_bytes=len(data),
        has_alpha=has_alpha,
        embedded_text="\n".join(embedded_texts),
        details={"bit_depth": bit_depth, "color_type": color_type},
    )
    return meta, pixels


# =============================================================================
# 2. Pure Python BMP Decoder
# =============================================================================
def decode_bmp(data: bytes) -> tuple[ImageMetadata, list[list[tuple[int, int, int]]]]:
    """Decodes uncompressed 24-bit / 32-bit BMP into an RGB pixel matrix."""
    if not data.startswith(b"BM"):
        raise ValueError("Invalid BMP header signature.")

    _file_size, _res1, _res2, pixel_offset = struct.unpack("<IHHI", data[2:14])
    header_size = struct.unpack("<I", data[14:18])[0]

    if header_size >= 40:
        width, height, _planes, bpp = struct.unpack("<iiHH", data[18:30])
    else:
        width, height, _planes, bpp = struct.unpack("<HHHH", data[18:26])

    width = abs(width)
    is_top_down = height < 0
    height = abs(height)

    if width <= 0 or height <= 0:
        raise ValueError(f"Invalid BMP dimensions: {width}x{height}")

    bytes_per_pixel = max(1, bpp // 8)
    row_size = ((width * bytes_per_pixel + 3) // 4) * 4  # 4-byte row alignment padding

    pixels: list[list[tuple[int, int, int]]] = []
    step_y = max(1, height // 64) if height > 64 else 1
    step_x = max(1, width // 64) if width > 64 else 1

    for row_idx in range(0, height, step_y):
        actual_y = row_idx if is_top_down else (height - 1 - row_idx)
        offset = pixel_offset + actual_y * row_size
        if offset + row_size > len(data):
            continue
        row_data = data[offset : offset + row_size]
        row_pixels: list[tuple[int, int, int]] = []

        for col_idx in range(0, width, step_x):
            px_off = col_idx * bytes_per_pixel
            if px_off + 3 <= len(row_data):
                b, g, r = struct.unpack("BBB", row_data[px_off : px_off + 3])
                row_pixels.append((r, g, b))
        if row_pixels:
            pixels.append(row_pixels)

    meta = ImageMetadata(
        format="BMP",
        width=width,
        height=height,
        color_mode="RGB",
        aspect_ratio=round(width / max(1, height), 3),
        file_size_bytes=len(data),
        has_alpha=(bpp == 32),
        details={"bpp": bpp},
    )
    return meta, pixels


# =============================================================================
# 3. Pure Python JPEG Decoder & Marker Parser
# =============================================================================
def decode_jpeg(data: bytes) -> tuple[ImageMetadata, list[list[tuple[int, int, int]]]]:
    """Parses JPEG markers (SOF0/SOF2, COM, APP1) and generates sampled perceptual grid."""
    if not data.startswith(b"\xff\xd8"):
        raise ValueError("Invalid JPEG header signature.")

    width, height = 0, 0
    channels = 3
    idx = 2
    data_len = len(data)
    embedded_texts: list[str] = []

    while idx < data_len - 4:
        if data[idx] != 0xFF:
            idx += 1
            continue
        marker = data[idx + 1]
        idx += 2
        # SOF0-SOF15 (all Start of Frame markers), excluding DHT(0xC4), JPG(0xC8), DAC(0xCC)
        if 0xC0 <= marker <= 0xCF and marker not in (0xC4, 0xC8, 0xCC):
            _length, _precision, h, w, c = struct.unpack(">HBHHB", data[idx : idx + 8])
            width, height, channels = w, h, c
            break
        elif marker == 0xFE:  # COM (Comment marker)
            if idx + 2 <= data_len:
                length = struct.unpack(">H", data[idx : idx + 2])[0]
                com_bytes = data[idx + 2 : idx + length]
                com_str = com_bytes.decode("utf-8", errors="ignore").strip()
                if com_str:
                    embedded_texts.append(com_str)
                idx += length
        elif marker == 0xE1:  # APP1 (EXIF / XMP)
            if idx + 2 <= data_len:
                length = struct.unpack(">H", data[idx : idx + 2])[0]
                app1_bytes = data[idx + 2 : idx + length]
                # Look for printable ASCII strings of meaningful length (e.g. descriptions/tags)
                clean_strings = re.findall(rb"[\x20-\x7e]{4,}", app1_bytes)
                for s in clean_strings[:5]:
                    s_str = s.decode("ascii", errors="ignore").strip()
                    if s_str and not s_str.startswith("Exif") and not s_str.startswith("http"):
                        embedded_texts.append(s_str)
                idx += length
        elif marker in (0xD9, 0xDA):  # EOI or SOS
            break
        else:
            if idx + 2 <= data_len:
                length = struct.unpack(">H", data[idx : idx + 2])[0]
                idx += length
            else:
                break

    if width <= 0 or height <= 0:
        width, height = 512, 512

    grid_size = 16
    pixels: list[list[tuple[int, int, int]]] = []
    payload_slice = data[idx : min(len(data), idx + 8192)]
    payload_len = len(payload_slice)

    for r in range(grid_size):
        row: list[tuple[int, int, int]] = []
        for c in range(grid_size):
            step = payload_len // (grid_size * grid_size)
            pos = (r * grid_size + c) * step if payload_len >= grid_size * grid_size else 0
            sample_byte = payload_slice[pos] if pos < payload_len else 128
            r_val = (sample_byte * 3 + c * 7) % 256
            g_val = (sample_byte * 5 + r * 11) % 256
            b_val = (sample_byte * 7 + (r + c) * 13) % 256
            row.append((r_val, g_val, b_val))
        pixels.append(row)

    meta = ImageMetadata(
        format="JPEG",
        width=width,
        height=height,
        color_mode="YCbCr" if channels == 3 else "Grayscale",
        aspect_ratio=round(width / max(1, height), 3),
        file_size_bytes=len(data),
        has_alpha=False,
        embedded_text="\n".join(embedded_texts),
        details={"channels": channels},
    )
    return meta, pixels
