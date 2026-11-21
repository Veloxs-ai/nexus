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

"""Source lines no symbol chunk covers (module-level code, class attributes).

Symbol chunkers emit one chunk per function or class; everything between them
(imports, constants, configuration, script statements, class-level assignments) would
otherwise be lost. ``uncovered_blocks`` returns those lines as consecutive blocks so
they become chunks of their own.
"""

from __future__ import annotations

__all__ = ["uncovered_blocks"]


def uncovered_blocks(
    lines: list[str], covered: list[tuple[int, int]], max_lines: int = 60
) -> list[tuple[int, int, str]]:
    """``(start, end, text)`` blocks of uncovered lines, at most ``max_lines`` lines each.

    Lines are kept verbatim; a block runs over blank lines but stops at covered code.
    """
    taken = [False] * (len(lines) + 1)
    for start, end in covered:
        for n in range(max(1, start), min(len(lines), end) + 1):
            taken[n] = True
    runs: list[tuple[int, int]] = []
    n = 1
    while n <= len(lines):
        if taken[n]:
            n += 1
            continue
        start = n
        while n <= len(lines) and not taken[n]:
            n += 1
        runs.append((start, n - 1))
    blocks: list[tuple[int, int, str]] = []
    for run_start, run_end in runs:
        for start in range(run_start, run_end + 1, max(1, max_lines)):
            end = min(run_end, start + max_lines - 1)
            numbered = [(i, lines[i - 1]) for i in range(start, end + 1)]
            kept = [i for i, line in numbered if line.strip()]
            if kept:
                blocks.append((kept[0], kept[-1], "\n".join(lines[kept[0] - 1 : kept[-1]])))
    return blocks
