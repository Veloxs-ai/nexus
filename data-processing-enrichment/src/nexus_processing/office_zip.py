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

"""OpenXML (zip) helpers shared by the XLSX, PPTX and DOCX processors: local tag names,
relationship ids and text of embedded images."""

from __future__ import annotations

import hashlib
import xml.etree.ElementTree as ET
import zipfile
from typing import Any


def _local_tag(elem: ET.Element) -> str:
    """Returns local XML tag without namespace prefix."""
    return elem.tag.split("}")[-1] if "}" in elem.tag else elem.tag


# Image extensions recognized in OpenXML media folders
_IMAGE_EXTENSIONS = frozenset(
    {
        ".png",
        ".jpg",
        ".jpeg",
        ".bmp",
        ".gif",
        ".tiff",
        ".tif",
        ".webp",
    }
)


def _extract_images_from_zip(
    zf: zipfile.ZipFile,
    media_prefix: str,
    ocr_provider: Any = None,
    auto_extract: bool = True,
) -> list[str]:
    """Extracts text from embedded images in an Office ZIP archive.

    Uses ``process_image_binary`` from images.py so improvements to image
    processing automatically benefit all document formats (PPTX, DOCX, XLSX).

    Args:
        zf: Open ZipFile of the Office document.
        media_prefix: Path prefix for media files (e.g. "ppt/media/").
        ocr_provider: Optional OCRProvider for text extraction from images.
        auto_extract: When True, auto-detects OCR provider if not passed.

    Returns:
        List of extracted text strings from embedded images.
    """
    from .images import process_image_binary

    image_texts: list[str] = []
    seen: dict[bytes, Any] = {}  # the same picture embedded twice is OCR'd once
    for name in zf.namelist():
        if not name.startswith(media_prefix):
            continue
        ext = "." + name.rsplit(".", 1)[-1].lower() if "." in name else ""
        if ext not in _IMAGE_EXTENSIONS:
            continue
        try:
            img_bytes = zf.read(name)
            if not img_bytes:
                continue
            digest = hashlib.sha1(img_bytes).digest()
            payload = seen.get(digest)
            if payload is None:
                payload = seen[digest] = process_image_binary(
                    img_bytes,
                    filename=name.split("/")[-1],
                    ocr_provider=ocr_provider,
                    auto_extract=auto_extract,
                )
            parts: list[str] = []
            basename = name.split("/")[-1]
            if payload.metadata.ocr_text:
                parts.append(payload.metadata.ocr_text)
            if payload.metadata.caption:
                parts.append(payload.metadata.caption)
            if parts:
                image_texts.append(f"[Image: {basename}] " + " ".join(parts))
            else:
                w = payload.metadata.width
                h = payload.metadata.height
                image_texts.append(f"[Embedded Image: {basename} {w}x{h}px]")
        except Exception:
            continue
    return image_texts


def _get_rel_id(attrib: dict[str, str]) -> str | None:
    """Extracts relationship ID (e.g. 'rId1') from element attributes."""
    for k, v in attrib.items():
        local_k = k.split("}")[-1] if "}" in k else k
        if "relationships" in k.lower() or k.startswith("r:") or ("}" in k and local_k == "id"):
            return v
    return attrib.get("r:id")
