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
color distribution histograms, and perceptual edge signatures (image metadata).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .image_decode import (
    ImageMetadata,
    decode_bmp,
    decode_jpeg,
    decode_png,
    detect_image_format,
)


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
    extracted_text: str = ""


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

    img_label = meta.filename or meta.format
    narrative_lines = [
        f"[Image: {img_label}] Format: {meta.format} | Dimensions: {meta.width}x{meta.height} | "
        f"Aspect Ratio: {meta.aspect_ratio} | Color Mode: {meta.color_mode} | "
        f"Mean Luminance: {avg_overall_lum} | Contrast: {contrast_score} | "
        f"Perceptual dHash: {edge_signature}"
    ]
    extracted_text_parts = []
    if meta.caption:
        narrative_lines.append(f"Caption: {meta.caption}")
        extracted_text_parts.append(meta.caption)
    if meta.ocr_text:
        narrative_lines.append(f"Visual Text / Content: {meta.ocr_text}")
        extracted_text_parts.append(meta.ocr_text)
    elif meta.embedded_text:
        narrative_lines.append(f"Embedded Text: {meta.embedded_text}")
        extracted_text_parts.append(meta.embedded_text)

    extracted_text = " | ".join(extracted_text_parts)
    narrative = "\n".join(narrative_lines)

    return VisualFeaturePayload(
        metadata=meta,
        spatial_grid=spatial_grid,
        horizontal_gradients=h_gradients,
        vertical_gradients=v_gradients,
        color_histogram=color_hist,
        luminance_histogram=lum_hist,
        edge_signature=edge_signature,
        narrative_summary=narrative,
        extracted_text=extracted_text,
    )


_OCR_MIN_SIDE = 32  # images narrower than this (or under a third of it tall) are not OCR'd


def process_image_binary(
    data: bytes,
    format_hint: str | None = None,
    filename: str = "image",
    ocr_text: str | None = None,
    caption: str | None = None,
    ocr_provider: Any | None = None,
    auto_extract: bool = False,
) -> VisualFeaturePayload:
    """Universal pure-Python entry point for decoding and extracting features from image bytes.

    Always inspects binary magic bytes first before trusting format_hint or filename,
    guaranteeing that mismatched extensions (e.g. JPEG bytes in a .png file) decode safely.

    Notes:
        New parameters ocr_provider and auto_extract can be used to plug in an OCRProvider.
    """
    magic_detected = detect_image_format(data)
    detected = magic_detected if magic_detected != "unknown" else (format_hint or "unknown")
    detected = detected.lower().removeprefix(".")
    # Guard: force unknown for empty payloads to avoid decoder crashes
    if not data:
        detected = "unknown"

    if detected == "png":
        meta, pixels = decode_png(data)
    elif detected == "bmp":
        meta, pixels = decode_bmp(data)
    elif detected in ("jpg", "jpeg"):
        meta, pixels = decode_jpeg(data)
    else:
        width, height = 256, 256
        # Guard against empty data causing ZeroDivisionError
        safe_data = data if data else b"\x00"
        pixels = [
            [
                (
                    safe_data[i % len(safe_data)],
                    safe_data[(i + 1) % len(safe_data)],
                    safe_data[(i + 2) % len(safe_data)],
                )
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

    meta.filename = filename

    # --- ML-Powered Content Extraction (Pluggable) ---
    # Priority: 1) Explicit pre-computed text  2) Pluggable provider  3) Auto-detect
    auto_ocr = ""
    # Icons, bullets and spacers hold no readable text: skip the OCR model for them.
    too_small = 0 < meta.width < _OCR_MIN_SIDE or 0 < meta.height < _OCR_MIN_SIDE // 3
    if not ocr_text and not caption and not too_small:
        provider = ocr_provider
        if provider is None and auto_extract:
            from .ml_providers import auto_detect_ocr_provider

            provider = auto_detect_ocr_provider()
        if provider is not None:
            import contextlib

            with contextlib.suppress(Exception):
                auto_ocr = provider.extract_text(data)

    if caption:
        meta.caption = caption
    if ocr_text:
        meta.ocr_text = ocr_text
    elif auto_ocr:
        meta.ocr_text = auto_ocr

    return extract_visual_features(meta, pixels)
