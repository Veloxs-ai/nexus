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

from nexus_processing.chunking import chunk_text


def test_chunk_text_preserves_overlap():
    text = " ".join(f"token{i}" for i in range(10))

    chunks = chunk_text(text, max_tokens=4, overlap_tokens=1)

    assert chunks == [
        "token0 token1 token2 token3",
        "token3 token4 token5 token6",
        "token6 token7 token8 token9",
    ]


def test_chunk_text_returns_empty_for_blank_text():
    assert chunk_text("   ", max_tokens=10, overlap_tokens=2) == []
