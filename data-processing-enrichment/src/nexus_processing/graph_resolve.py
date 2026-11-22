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

"""Entity keys, alias lookups and entity resolution.

``normalise_name(name, entity_type=)`` is the entity key: NFKC, casefold, ``&`` -> ``and``,
diacritics and punctuation removed; org keys keep one canonical legal suffix (``Acme Corp`` =
``ACME Corporation.`` = ``acme corp``; ``Atlas Labs GmbH`` and ``Atlas Labs Inc`` stay two
legal entities), person keys are token-sorted (``Kumar, Ravi`` = ``Ravi Kumar``) without
honorifics.

``resolve(candidates, existing)`` maps each candidate entity to a canonical one:

1. the same key under a generic type (``entity``) and a specific one (``org``) -> the
   specific one (type upgrade);
2. an alias hit in ``existing`` (exact key) with a compatible type;
3. hash blocking (key, first token + length bucket, acronym) and, inside blocks of at most
   ``BLOCK_CAP`` entries, the larger of character-trigram and token Jaccard, with a bonus
   for agreeing types. ``person`` and ``org`` (and any two specific types) never merge; two
   structured entities never auto-merge (proposed only); record entities with different
   primary keys never merge.

Scores >= ``auto_merge`` merge (a text entity into a structured one, else into the more
mentioned one) when the candidate has exactly one such target; an org name without a legal
suffix merges into the one org with that name and a suffix. Scores >= ``propose``, and
ambiguous candidates, are returned as proposals and never applied.
"""

from __future__ import annotations

import re
import unicodedata
from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from functools import lru_cache

from .graph_lexicon import HONORIFICS, ORG_LEGAL_SUFFIXES
from .graph_types import Alias, EntityRef, GraphExtraction, Mention, RelationRef

__all__ = [
    "BLOCK_CAP",
    "AliasIndex",
    "Resolution",
    "acronym",
    "apply_resolution",
    "normalise_name",
    "org_base",
    "resolve",
    "similarity",
]

BLOCK_CAP = 50
GENERIC_TYPES = frozenset({"entity", "concept"})
_PUNCT = re.compile(r"[^\w\s]+|_+")
_SPACE = re.compile(r"\s+")


@lru_cache(maxsize=65536)
def _base(name: str) -> str:
    text = unicodedata.normalize("NFKC", name).casefold().replace("&", " and ")
    if not text.isascii():
        text = "".join(
            c for c in unicodedata.normalize("NFKD", text) if not unicodedata.combining(c)
        )
    return _SPACE.sub(" ", _PUNCT.sub(" ", text)).strip()


@lru_cache(maxsize=65536)
def normalise_name(name: str, *, entity_type: str = "entity") -> str:
    """The entity key of ``name`` for ``entity_type`` ("" when nothing is left)."""
    text = _base(name)
    if not text:
        return ""
    if entity_type == "org":
        base, suffix = _split_org(text)
        return f"{base} {suffix}" if suffix else base
    if entity_type == "person":
        tokens = [t for t in text.split() if t not in HONORIFICS] or text.split()
        return " ".join(sorted(tokens))
    return text


_SUFFIX_CANON = {
    "incorporated": "inc", "corporation": "corp", "limited": "ltd", "company": "co",
    "private": "pvt", "proprietary": "pty", "gesellschaft": "gmbh",
}  # fmt: skip


def _split_org(text: str) -> tuple[str, str]:
    """``(base, canonical legal suffix)`` of a normalised org name: ``"acme corporation"`` ->
    ``("acme", "corp")``, ``"tata private limited"`` -> ``("tata", "pvt ltd")``."""
    tokens = text.split()
    if len(tokens) > 1 and tokens[0] == "the":
        tokens = tokens[1:]
    suffix: list[str] = []
    while len(tokens) > 1 and tokens[-1] in ORG_LEGAL_SUFFIXES:
        suffix.insert(0, _SUFFIX_CANON.get(tokens[-1], tokens[-1]))
        tokens = tokens[:-1]
    return " ".join(tokens), " ".join(suffix)


def org_base(key: str) -> str:
    """An org key without its legal suffix (``"acme corp"`` -> ``"acme"``)."""
    return _split_org(key)[0]


def acronym(key: str) -> str:
    """Initials of a multi-token key (``""`` for one token)."""
    tokens = [t for t in key.split() if t not in ("of", "and", "the", "for")]
    return "".join(t[0] for t in tokens) if len(tokens) > 1 else ""


def _trigrams(text: str) -> frozenset[str]:
    padded = f"  {text} "
    return frozenset(padded[i : i + 3] for i in range(len(padded) - 2))


def similarity(a: str, b: str) -> float:
    """Larger of character-trigram Jaccard and token Jaccard of two keys (0..1)."""
    if a == b:
        return 1.0
    ta, tb = _trigrams(a), _trigrams(b)
    tri = len(ta & tb) / len(ta | tb) if ta or tb else 0.0
    wa, wb = set(a.split()), set(b.split())
    tok = len(wa & wb) / len(wa | wb) if wa or wb else 0.0
    return max(tri, tok)


def _compatible(t1: str, t2: str) -> bool:
    return t1 == t2 or t1 in GENERIC_TYPES or t2 in GENERIC_TYPES


class AliasIndex:
    """Known aliases of a workspace: ``alias_key -> [(entity_key, type, name)]``.

    Built from alias-table rows ``(alias_key, entity_key, type, name)``; a store loads only
    the rows for the blocking keys of the current candidates (``blocking_keys``)."""

    __slots__ = ("_by_alias", "_entities")

    def __init__(self) -> None:
        self._by_alias: dict[str, list[tuple[str, str, str]]] = defaultdict(list)
        self._entities: dict[tuple[str, str], str] = {}

    @classmethod
    def from_rows(cls, rows: Iterable[Sequence[str]]) -> AliasIndex:
        index = cls()
        for alias_key, entity_key, entity_type, name in rows:
            index.add(alias_key, entity_key, entity_type, name)
        return index

    def add(self, alias_key: str, entity_key: str, entity_type: str, name: str) -> None:
        bucket = self._by_alias[alias_key]
        entry = (entity_key, entity_type, name)
        if entry not in bucket:
            bucket.append(entry)
        self._entities.setdefault((entity_type, entity_key), name)

    def lookup(self, alias_key: str) -> list[tuple[str, str, str]]:
        return self._by_alias.get(alias_key, [])

    def entities(self) -> dict[tuple[str, str], str]:
        return self._entities

    def __len__(self) -> int:
        return len(self._entities)


def blocking_keys(key: str) -> list[str]:
    """The keys a store should load aliases for to resolve ``key``."""
    out = [key]
    acr = acronym(key)
    if acr:
        out.append(acr)
    return out


@dataclass(frozen=True, slots=True)
class Resolution:
    mapping: dict[tuple[str, str], tuple[str, str]]  # (type, key) -> canonical (type, key)
    new_aliases: tuple[Alias, ...] = ()
    merges: tuple[tuple[tuple[str, str], tuple[str, str], float], ...] = ()
    proposals: tuple[tuple[tuple[str, str], tuple[str, str], float], ...] = ()
    stats: dict[str, int] = field(default_factory=dict)


class _Union:
    def __init__(self) -> None:
        self.parent: dict[tuple[str, str], tuple[str, str]] = {}

    def find(self, x: tuple[str, str]) -> tuple[str, str]:
        parent = self.parent
        root = x
        while parent.get(root, root) != root:
            root = parent[root]
        while parent.get(x, x) != root:
            parent[x], x = root, parent[x]
        return root


def _is_record_pk(key: str) -> bool:
    return "#" in key


def resolve(
    candidates: Sequence[EntityRef],
    existing: AliasIndex | None = None,
    *,
    auto_merge: float = 0.92,
    propose: float = 0.80,
    weights: Mapping[tuple[str, str], float] | None = None,
) -> Resolution:
    """Map each candidate ``(type, key)`` to its canonical ``(type, key)`` (see module doc).

    ``weights`` (e.g. mention counts) decide the direction of text-to-text merges."""
    existing = existing or AliasIndex()
    weights = weights or {}
    origin: dict[tuple[str, str], str] = {}
    names: dict[tuple[str, str], str] = {}
    for ref, name in existing.entities().items():
        origin[ref] = "structured"
        names[ref] = name
    for c in candidates:
        if c.ref not in origin or c.origin == "structured":
            origin[c.ref] = c.origin
        names.setdefault(c.ref, c.name)
    by_key: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for ref in origin:
        by_key[ref[1]].append(ref)

    union = _Union()
    aliases: list[Alias] = []
    merges: list[tuple[tuple[str, str], tuple[str, str], float]] = []
    proposals: list[tuple[tuple[str, str], tuple[str, str], float]] = []
    stats = {"candidates": len(candidates), "type_upgrades": 0, "alias_hits": 0, "fuzzy_merges": 0}

    def rank(ref: tuple[str, str]) -> tuple[int, int, float, str]:
        return (
            origin.get(ref) == "structured",
            ref[0] not in GENERIC_TYPES,
            weights.get(ref, 0.0),
            ref[1],
        )

    def link(child: tuple[str, str], parent: tuple[str, str]) -> None:
        a, b = union.find(child), union.find(parent)
        if a != b:
            union.parent[a] = b

    # 1-2. exact key across types, then known aliases.
    for c in candidates:
        ref = c.ref
        if ref[0] in GENERIC_TYPES:
            specific = [r for r in by_key[ref[1]] if r[0] not in GENERIC_TYPES]
            if len({r[0] for r in specific}) == 1:
                link(ref, max(specific, key=rank))
                stats["type_upgrades"] += 1
                continue
        hits = [
            (k, t)
            for k, t, _ in existing.lookup(ref[1])
            if _compatible(t, ref[0]) and (t, k) != ref
        ]
        if len(hits) == 1 and not (_is_record_pk(ref[1]) and origin.get(ref) == "structured"):
            target = (hits[0][1], hits[0][0])
            link(ref, target)
            stats["alias_hits"] += 1

    # 3. fuzzy matching inside hash blocks.
    blocks: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for ref in origin:
        key = ref[1]
        if not key or _is_record_pk(key):
            continue
        tokens = key.split()
        if ref[0] in ("org", "entity"):
            blocks[f"o:{org_base(key)}"].append(ref)
        blocks[f"t:{tokens[0]}:{len(key) // 6}"].append(ref)
        blocks[f"t:{tokens[0]}:{len(key) // 6 + 1}"].append(ref)
        acr = acronym(key)
        if acr:
            blocks[f"a:{acr}"].append(ref)
        if len(tokens) == 1 and 2 <= len(key) <= 6:
            blocks[f"a:{key}"].append(ref)
    candidate_refs = {c.ref for c in candidates}
    seen_pairs: set[tuple[tuple[str, str], tuple[str, str]]] = set()
    targets: dict[tuple[str, str], list[tuple[tuple[str, str], float]]] = defaultdict(list)
    for members in blocks.values():
        if len(members) < 2 or len(members) > BLOCK_CAP:
            continue
        for i, a in enumerate(members):
            for b in members[i + 1 :]:
                if a == b or not _compatible(a[0], b[0]):
                    continue
                if a not in candidate_refs and b not in candidate_refs:
                    continue
                pair = (a, b) if a < b else (b, a)
                if pair in seen_pairs:
                    continue
                seen_pairs.add(pair)
                score = round(_score(a, b), 3)
                if score < propose:
                    continue
                both_structured = origin.get(a) == "structured" and origin.get(b) == "structured"
                into, child = (a, b) if rank(a) >= rank(b) else (b, a)
                if score >= auto_merge and not both_structured:
                    targets[child].append((into, score))
                else:
                    proposals.append((child, into, score))
    # A name that matches two different entities ("Atlas Labs" vs "Atlas Labs GmbH" and
    # "Atlas Labs Inc") is ambiguous: proposed, never merged.
    for child in sorted(targets, key=rank):
        options = targets[child]
        roots = {union.find(into) for into, _ in options}
        if len(roots) > 1:
            proposals.extend((child, into, score) for into, score in options)
            stats["ambiguous"] = stats.get("ambiguous", 0) + 1
            continue
        into, score = max(options, key=lambda o: o[1])
        if union.find(child) != union.find(into):
            link(child, into)
            merges.append((child, into, score))
            alias = names.get(child, child[1])
            aliases.append(Alias(child[1], alias, into[1], into[0], "fuzzy", score))
            stats["fuzzy_merges"] += 1

    mapping: dict[tuple[str, str], tuple[str, str]] = {}
    fuzzy_children = {child for child, _, _ in merges}
    for c in candidates:
        root = union.find(c.ref)
        mapping[c.ref] = root
        if root != c.ref and c.ref not in fuzzy_children:
            aliases.append(Alias(c.ref[1], c.name, root[1], root[0], "name", 1.0))
    proposals = [p for p in proposals if union.find(p[0]) != union.find(p[1])]
    final = []
    for a in aliases:  # point every alias at the final canonical entity (merges chain)
        t, k = union.find((a.entity_type, a.entity_key))
        final.append(
            a
            if (t, k) == (a.entity_type, a.entity_key)
            else Alias(a.alias_key, a.alias, k, t, a.source, a.confidence)
        )
    return Resolution(
        mapping, tuple(_dedupe_aliases(final)), tuple(merges), tuple(proposals), stats
    )


def _score(a: tuple[str, str], b: tuple[str, str]) -> float:
    ka, kb = a[1], b[1]
    score = similarity(ka, kb)
    if acronym(ka) == kb or acronym(kb) == ka:
        score = max(score, 0.85)
    if _stems(ka) == _stems(kb):  # singular / plural ("logistic" / "logistics")
        score = max(score, 0.95)
    if "org" in (a[0], b[0]):
        (base_a, suf_a), (base_b, suf_b) = _split_org(ka), _split_org(kb)
        if base_a == base_b and suf_a != suf_b:
            # "Acme" / "Acme Corp" (one has no suffix): the same org; "Acme Inc" / "Acme Ltd"
            # may be two legal entities: proposed only.
            score = max(score, 0.95 if not (suf_a and suf_b) else 0.85)
    if a[0] == b[0]:
        score += 0.03
    # A different number in otherwise similar names ("Acme 2" / "Acme 3") is a different entity.
    if {t for t in ka.split() if t.isdigit()} != {t for t in kb.split() if t.isdigit()}:
        score -= 0.3
    return min(score, 1.0)


def _stems(key: str) -> tuple[str, ...]:
    return tuple(
        t[:-1] if len(t) > 3 and t.endswith("s") and not t.endswith("ss") else t
        for t in key.split()
    )


def _dedupe_aliases(aliases: Iterable[Alias]) -> list[Alias]:
    seen: dict[tuple[str, str, str], Alias] = {}
    for a in aliases:
        k = (a.alias_key, a.entity_type, a.entity_key)
        if k not in seen or a.confidence > seen[k].confidence:
            seen[k] = a
    return list(seen.values())


def apply_resolution(extraction: GraphExtraction, resolution: Resolution) -> GraphExtraction:
    """``extraction`` with every entity reference mapped to its canonical entity: merged
    entities dropped, mentions and relations re-keyed (self-loops dropped), the resolution's
    aliases added."""
    mapping = resolution.mapping

    def canon(t: str, k: str) -> tuple[str, str]:
        return mapping.get((t, k), (t, k))

    entities: dict[tuple[str, str], EntityRef] = {}
    for e in extraction.entities:
        if canon(e.type, e.key) == e.ref:
            entities[e.ref] = e
    mentions: dict[tuple[str, str, str, int], Mention] = {}
    for m in extraction.mentions:
        t, k = canon(m.entity_type, m.entity_key)
        if (t, k) != (m.entity_type, m.entity_key):
            m = Mention(
                k, t, m.chunk_key, m.start, m.end, m.surface, m.method, m.confidence, m.field
            )
        mentions.setdefault((t, k, m.chunk_key, m.start), m)
    relations: dict[tuple[str, ...], RelationRef] = {}
    for r in extraction.relations:
        st, sk = canon(r.src_type, r.src_key)
        dt, dk = canon(r.dst_type, r.dst_key)
        if (st, sk) == (dt, dk):
            continue
        if r.type == "co_mentioned" and (dt, dk) < (st, sk):
            st, sk, dt, dk = dt, dk, st, sk
        key = (st, sk, dt, dk, r.type, r.chunk_key)
        old = relations.get(key)
        count = r.count + (old.count if old else 0)
        relations[key] = RelationRef(
            sk,
            st,
            dk,
            dt,
            r.type,
            r.chunk_key,
            count,
            "structured" if (old and old.origin == "structured") else r.origin,
        )
    aliases = [
        Alias(
            a.alias_key,
            a.alias,
            *reversed(canon(a.entity_type, a.entity_key)),
            a.source,
            a.confidence,
        )
        for a in extraction.aliases
    ]
    stats = dict(extraction.stats)
    stats["merged_entities"] = len(extraction.entities) - len(entities)
    return GraphExtraction(
        tuple(entities.values()),
        tuple(mentions.values()),
        tuple(relations.values()),
        tuple(_dedupe_aliases([*aliases, *resolution.new_aliases])),
        stats,
    )
