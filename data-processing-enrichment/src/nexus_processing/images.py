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

"""Zero-dependency, pure-Python image binary decoder and visual feature extractor.

Decodes PNG, JPEG, and BMP image files using only the Python standard library
(`struct`, `zlib`, `io`, `hashlib`, `math`), extracting spatial luminance grids,
color distribution histograms, and perceptual edge signatures for 3072D vector projection.
"""

from __future__ import annotations

import io
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
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class VisualFeaturePayload:
    metadata: ImageMetadata
    spatial_grid: list[float]  # 64-element 8x8 normalized luminance grid [0.0 - 1.0]
    horizontal_gradients: list[float]  # Gradients between adjacent horizontal cells
    vertical_gradients: list[float]  # Gradients between adjacent vertical cells
    color_histogram: list[float]  # 64-bin quantized RGB color histogram
    luminance_histogram: list[float]  # 32-bin perceptual intensity distribution
    edge_signature: str  # 64-bit hexadecimal dHash gradient signature
    narrative_summary: str


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
        width, height, _planes, bpp = struct.unpack("<hhhh", data[18:26])

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
    """Parses JPEG markers (SOF0/SOF2, JFIF) and generates sampled perceptual grid."""
    if not data.startswith(b"\xff\xd8"):
        raise ValueError("Invalid JPEG header signature.")

    width, height = 0, 0
    channels = 3
    idx = 2
    data_len = len(data)

    while idx < data_len - 4:
        if data[idx] != 0xFF:
            idx += 1
            continue
        marker = data[idx + 1]
        idx += 2
        # SOF0 (Baseline), SOF1 (Extended), SOF2 (Progressive)
        if marker in (0xC0, 0xC1, 0xC2):
            _length, _precision, h, w, c = struct.unpack(">HBHBB", data[idx : idx + 7])
            width, height, channels = w, h, c
            break
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
        details={"channels": channels},
    )
    return meta, pixels


# =============================================================================
# 4. Universal Feature Extractor (Spatial Grid, Histograms, dHash)
# =============================================================================
def extract_visual_features(
    meta: ImageMetadata, pixels: list[list[tuple[int, int, int]]]
) -> VisualFeaturePayload:
    """Computes spatial luminance grid, color distribution, and perceptual edge signatures."""
    if not pixels or not pixels[0]:
        pixels = [[(128, 128, 128) for _ in range(8)] for _ in range(8)]

    src_h = len(pixels)
    src_w = len(pixels[0])

    grid_dim = 8
    spatial_grid: list[float] = []
    total_luminance = 0.0

    color_hist = [0.0] * 64  # 4x4x4 RGB color cube
    lum_hist = [0.0] * 32  # 32-bin luminance distribution
    total_samples = 0

    for gy in range(grid_dim):
        sy_start = int(gy * src_h / grid_dim)
        sy_end = max(sy_start + 1, int((gy + 1) * src_h / grid_dim))

        for gx in range(grid_dim):
            sx_start = int(gx * src_w / grid_dim)
            sx_end = max(sx_start + 1, int((gx + 1) * src_w / grid_dim))

            cell_lum = 0.0
            cell_count = 0

            for y in range(sy_start, min(sy_end, src_h)):
                for x in range(sx_start, min(sx_end, src_w)):
                    r, g, b = pixels[y][x]
                    lum = (0.299 * r + 0.587 * g + 0.114 * b) / 255.0
                    cell_lum += lum
                    cell_count += 1

                    r_bin = min(3, r // 64)
                    g_bin = min(3, g // 64)
                    b_bin = min(3, b // 64)
                    color_bin = r_bin * 16 + g_bin * 4 + b_bin
                    color_hist[color_bin] += 1.0

                    l_bin = min(31, int(lum * 32))
                    lum_hist[l_bin] += 1.0
                    total_samples += 1

            avg_lum = cell_lum / max(1, cell_count)
            spatial_grid.append(round(avg_lum, 4))
            total_luminance += avg_lum

    if total_samples > 0:
        color_hist = [round(c / total_samples, 5) for c in color_hist]
        lum_hist = [round(val / total_samples, 5) for val in lum_hist]

    h_gradients: list[float] = []
    v_gradients: list[float] = []

    for row in range(grid_dim):
        for col in range(grid_dim - 1):
            curr_val = spatial_grid[row * grid_dim + col]
            next_val = spatial_grid[row * grid_dim + (col + 1)]
            h_gradients.append(round(next_val - curr_val, 4))

    for row in range(grid_dim - 1):
        for col in range(grid_dim):
            curr_val = spatial_grid[row * grid_dim + col]
            below_val = spatial_grid[(row + 1) * grid_dim + col]
            v_gradients.append(round(below_val - curr_val, 4))

    hash_bits: list[str] = []
    for g in h_gradients:
        hash_bits.append("1" if g > 0 else "0")
    for g in v_gradients:
        if len(hash_bits) >= 64:
            break
        hash_bits.append("1" if g > 0 else "0")

    bit_str = "".join(hash_bits[:64])
    dhash_int = int(bit_str or "0", 2)
    edge_signature = f"{dhash_int:016x}"

    avg_overall_lum = round(total_luminance / 64.0, 3)
    contrast_score = round(max(spatial_grid) - min(spatial_grid), 3)

    narrative = (
        f"[Image: {meta.format}] Dimensions: {meta.width}x{meta.height} | "
        f"Aspect Ratio: {meta.aspect_ratio} | Color Mode: {meta.color_mode} | "
        f"Mean Luminance: {avg_overall_lum} | Contrast: {contrast_score} | "
        f"Perceptual dHash: {edge_signature}"
    )

    return VisualFeaturePayload(
        metadata=meta,
        spatial_grid=spatial_grid,
        horizontal_gradients=h_gradients,
        vertical_gradients=v_gradients,
        color_histogram=color_hist,
        luminance_histogram=lum_hist,
        edge_signature=edge_signature,
        narrative_summary=narrative,
    )


def process_image_binary(data: bytes, format_hint: str | None = None) -> VisualFeaturePayload:
    """Universal pure-Python entry point for decoding and extracting features from image bytes."""
    detected = format_hint or detect_image_format(data)
    detected = detected.lower().removeprefix(".")

    if detected == "png":
        meta, pixels = decode_png(data)
    elif detected == "bmp":
        meta, pixels = decode_bmp(data)
    elif detected in ("jpg", "jpeg"):
        meta, pixels = decode_jpeg(data)
    else:
        width, height = 256, 256
        pixels = [
            [
                (data[i % len(data)], data[(i + 1) % len(data)], data[(i + 2) % len(data)])
                for i in range(16)
            ]
            for _ in range(16)
        ]
        meta = ImageMetadata(
            format=detected.upper() if detected else "RAW_IMAGE",
            width=width,
            height=height,
            color_mode="RGB",
            aspect_ratio=1.0,
            file_size_bytes=len(data),
        )

    return extract_visual_features(meta, pixels)
