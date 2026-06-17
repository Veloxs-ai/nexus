# Copyright 2026 Veloxs AI Inc. All rights reserved.
#
# This file is part of Nexus, proprietary and confidential software of
# Veloxs AI Inc. Use is subject to the Nexus Proprietary Software License;
# see the LICENSE file in the project root. Unauthorized copying,
# distribution, or modification of this file, via any medium, is strictly
# prohibited.
#
# SPDX-License-Identifier: LicenseRef-Veloxs-AI-Proprietary

from nexus_retrieval.lexical import LexicalIndex
from nexus_retrieval.models import IndexedDocument


def test_lexical_index_scores_keyword_matches(tmp_path):
    index = LexicalIndex("lexical.json", tmp_path)
    index.add(IndexedDocument(id="a", collection="docs", text="security access access"))
    index.add(IndexedDocument(id="b", collection="docs", text="finance payment"))

    results = index.search("access security")

    assert results[0].id == "a"
    assert results[0].lexical_score == 1.0


def test_lexical_index_persists(tmp_path):
    index = LexicalIndex("lexical.json", tmp_path)
    index.add(IndexedDocument(id="a", collection="docs", text="security access"))
    index.save()

    loaded = LexicalIndex("lexical.json", tmp_path)
    loaded.load()

    assert loaded.search("security")[0].id == "a"

