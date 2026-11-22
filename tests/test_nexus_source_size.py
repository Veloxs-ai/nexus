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

"""Every library source file stays under the size limit (split a module before it grows past)."""

from __future__ import annotations

from pathlib import Path

MAX_LINES = 500
ROOT = Path(__file__).resolve().parent.parent


def _source_files() -> list[Path]:
    roots = [ROOT / "src", *sorted(p for p in ROOT.glob("*/src") if p.is_dir())]
    return sorted(f for r in roots for f in r.rglob("*.py") if "__pycache__" not in f.parts)


def test_source_tree_is_found():
    files = _source_files()
    assert any(f.name == "client.py" for f in files)
    assert any("nexus_processing" in f.parts for f in files)


def test_no_source_file_exceeds_the_line_limit():
    too_long = {}
    for path in _source_files():
        with path.open("rb") as fh:
            count = sum(1 for _ in fh)
        if count > MAX_LINES:
            too_long[str(path.relative_to(ROOT))] = count
    assert not too_long, f"source files over {MAX_LINES} lines: {too_long}"
