# Copyright 2026 Veloxs AI Inc. All rights reserved.
#
# This file is part of Nexus, proprietary and confidential software of
# Veloxs AI Inc. Use is subject to the Nexus Proprietary Software License;
# see the LICENSE file in the project root. Unauthorized copying,
# distribution, or modification of this file, via any medium, is strictly
# prohibited.
#
# SPDX-License-Identifier: LicenseRef-Veloxs-AI-Proprietary

from __future__ import annotations


def chunk_text(text: str, max_tokens: int, overlap_tokens: int) -> list[str]:
    tokens = text.split()
    if not tokens:
        return []
    if len(tokens) <= max_tokens:
        return [" ".join(tokens)]

    chunks: list[str] = []
    start = 0
    step = max_tokens - overlap_tokens
    while start < len(tokens):
        end = min(start + max_tokens, len(tokens))
        chunks.append(" ".join(tokens[start:end]))
        if end == len(tokens):
            break
        start += step
    return chunks

