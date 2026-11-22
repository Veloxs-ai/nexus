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

"""Deterministic entities and relations from table records (connector and database rows).

``infer_entity_columns(profile)`` picks the columns whose values are entities from a
``nexus.table_profile`` profile: text columns with a distinct ratio between 0.001 and 0.95
(no lower bound when the column name gives a type: customer, assignee, product, region),
short values (<= 80 characters, < 12 words), not dates/numbers/booleans, not low-cardinality
enums (``status``, ``priority``...), never a PII column (by name or by ``column_kinds``).
The type comes from the column-name lexicon; ``hints`` (connector-declared) override it.

``infer_row_entity(profile, primary_key=)`` names a row entity when a table has a primary
key and a name/title column (customers, accounts); tables without one (orders, tickets)
create no per-row node.

``structured_graph(records, columns, ...)`` makes one pass over ``(chunk_key, record)``:
value entities ("field" mentions), row entities, foreign-key mentions resolved through
``pk_index`` ("fk"), and typed relations: row entity -> each value (named after the column),
or between the value columns of a row (``customer -> assignee`` named after the second).

``detect_foreign_keys(profiles, samples)`` finds key columns by sampled value containment.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from .graph_lexicon import ENUM_COLUMN, PII_COLUMN, PII_KINDS, TITLE_COLUMN, column_type
from .graph_resolve import normalise_name
from .graph_types import Alias, EntityRef, GraphExtraction, Mention, RelationRef

__all__ = [
    "EntityColumn",
    "ForeignKey",
    "RowEntitySpec",
    "detect_foreign_keys",
    "infer_entity_columns",
    "infer_row_entity",
    "is_masked",
    "pk_index_for",
    "structured_graph",
]

MAX_VALUE_CHARS = 80
MAX_VALUE_WORDS = 12
MAX_ENTITY_COLUMNS = 8
_MASK = re.compile(r"\[[A-Z][A-Z0-9_]*(?::[0-9a-f]{4,})?\]|<[A-Z][A-Z0-9_]*>|\*{3,}|█")
_KEYISH = re.compile(r"(^|_)(id|key|code|no|num|number|ref|fk)$")


@dataclass(frozen=True, slots=True)
class EntityColumn:
    name: str  # column name; dotted for a nested field ("address.city")
    type: str
    relation: str  # relation type named after the column ("customer", "assignee")


@dataclass(frozen=True, slots=True)
class RowEntitySpec:
    primary_key: str
    name_column: str
    type: str = "record"
    unique_names: bool = True  # key by name (merges with the same name elsewhere) or name#pk


@dataclass(frozen=True, slots=True)
class ForeignKey:
    column: str
    ref_table: str
    ref_column: str
    containment: float = 1.0


def is_masked(text: str) -> bool:
    """True when ``text`` carries a PII mask token (``[EMAIL]``, ``[REDACTED_X]``, ``****``)."""
    return bool(_MASK.search(text))


def _relation_name(column: str) -> str:
    name = re.sub(r"[^a-z0-9]+", "_", column.casefold()).strip("_")
    name = re.sub(r"_(id|key|code|no|ref|fk|name)$", "", name) or name
    return name[:64]


def _sample_values(column: Mapping[str, Any]) -> list[tuple[str, int]]:
    pairs = column.get("values") or column.get("top") or []
    return [(str(v), int(n)) for v, n in pairs]


def infer_entity_columns(
    profile: Mapping[str, Any],
    *,
    column_kinds: Mapping[str, str] | None = None,
    hints: Mapping[str, str] | None = None,
    exclude: Iterable[str] = (),
) -> list[EntityColumn]:
    """The entity columns of a profiled table (see the module docstring), at most 8."""
    rows = int(profile.get("rows") or 0)
    kinds = column_kinds or {}
    hints = hints or {}
    skip = set(exclude)
    out: list[EntityColumn] = []
    for col in profile.get("columns", ()):
        name = str(col.get("name", ""))
        if not name or name in skip:
            continue
        folded = re.sub(r"[^a-z0-9]+", "_", name.casefold()).strip("_")
        if name in hints:
            if hints[name] in ("", "none", "attribute"):
                continue
            out.append(EntityColumn(name, hints[name], _relation_name(name)))
            continue
        if col.get("type") != "text" or rows <= 0:
            continue
        if str(kinds.get(name, "")).casefold() in PII_KINDS or PII_COLUMN.search(folded):
            continue
        present = rows - int(col.get("nulls") or 0)
        distinct = int(col.get("distinct") or 0)
        if present <= 0 or distinct <= 1:
            continue
        entity_type = column_type(name)
        if col.get("distinct_capped"):
            if entity_type == "entity":
                continue  # unknown cardinality and no name signal
        else:
            ratio = distinct / present
            # A column whose name gives it a type (customer, assignee, product, region) holds
            # entities however few there are: 20 customers over 200k orders are still 20
            # customers, and the customer-product edges of those orders are the useful ones.
            if ratio > 0.95 or (ratio < 0.001 and entity_type == "entity"):
                continue
        if distinct < 16 and ENUM_COLUMN.search(folded):
            continue
        sample = _sample_values(col)
        if sample:
            total = sum(n for _, n in sample) or 1
            avg_len = sum(len(v) * n for v, n in sample) / total
            avg_words = sum(len(v.split()) * n for v, n in sample) / total
            if avg_len > MAX_VALUE_CHARS or avg_words >= MAX_VALUE_WORDS:
                continue
            if all(_looks_like_id(v) for v, _ in sample[:10]):
                continue  # codes (order numbers, SKUs) are keys, not entities
        out.append(EntityColumn(name, entity_type, _relation_name(name)))
    return out[:MAX_ENTITY_COLUMNS]


_ID_VALUE = re.compile(r"^(?=.*\d)[A-Za-z0-9]+(?:[-_/.][A-Za-z0-9]+)*$")


def _looks_like_id(value: str) -> bool:
    return bool(_ID_VALUE.match(value.strip()))


def infer_row_entity(
    profile: Mapping[str, Any],
    *,
    primary_key: str | None,
    table: str = "",
    column_kinds: Mapping[str, str] | None = None,
) -> RowEntitySpec | None:
    """A row-entity spec when the table has a primary key and a name or title column."""
    if not primary_key:
        return None
    kinds = column_kinds or {}
    rows = int(profile.get("rows") or 0)
    best = None
    for col in profile.get("columns", ()):
        name = str(col.get("name", ""))
        folded = re.sub(r"[^a-z0-9]+", "_", name.casefold()).strip("_")
        if name == primary_key or col.get("type") != "text" or not TITLE_COLUMN.match(folded):
            continue
        if str(kinds.get(name, "")).casefold() in PII_KINDS or PII_COLUMN.search(folded):
            continue
        sample = _sample_values(col)
        if sample and sum(len(v) for v, _ in sample) / len(sample) > MAX_VALUE_CHARS:
            continue
        rank = 0 if folded in ("name", "title") else 1
        if best is None or rank < best[0]:
            best = (rank, name, col)
    if best is None:
        return None
    _, name, col = best
    present = rows - int(col.get("nulls") or 0)
    unique = not col.get("distinct_capped") and int(col.get("distinct") or 0) == present
    entity_type = column_type(table.rsplit(".", 1)[-1]) if table else "entity"
    return RowEntitySpec(
        primary_key, name, "record" if entity_type == "entity" else entity_type, unique
    )


def _value(record: Mapping[str, Any], column: str) -> Any:
    if column in record:
        return record[column]
    if "." in column:
        head, _, tail = column.partition(".")
        inner = record.get(head)
        if isinstance(inner, Mapping):
            return inner.get(tail)
    return None


def _text(value: Any) -> str | None:
    if value is None or isinstance(value, bool | dict | list):
        return None
    text = str(value).strip()
    if not text or len(text) > MAX_VALUE_CHARS * 2 or is_masked(text):
        return None
    return text


def row_entity_key(name: str, pk: str, spec: RowEntitySpec) -> str:
    key = normalise_name(name, entity_type=spec.type)
    if not key:
        return ""
    return key if spec.unique_names else f"{key}#{normalise_name(pk)}"


def pk_index_for(
    records: Iterable[Mapping[str, Any]], spec: RowEntitySpec, ref_column: str | None = None
) -> dict[str, tuple[str, str, str]]:
    """``{value of ref_column (default the primary key): (entity_key, type, name)}`` for the
    row entities of a table: what ``structured_graph(pk_index=)`` resolves foreign keys with."""
    out: dict[str, tuple[str, str, str]] = {}
    column = ref_column or spec.primary_key
    for record in records:
        name = _text(_value(record, spec.name_column))
        pk = _text(_value(record, spec.primary_key))
        ref = _text(_value(record, column))
        if name and pk and ref:
            key = row_entity_key(name, pk, spec)
            if key:
                out[ref] = (key, spec.type, name)
    return out


def structured_graph(
    records: Iterable[tuple[str, Mapping[str, Any]]],
    columns: Sequence[EntityColumn],
    *,
    table: str,
    row_entity: RowEntitySpec | None = None,
    foreign_keys: Sequence[ForeignKey] = (),
    pk_index: Mapping[str, Mapping[str, tuple[str, str, str]]] | None = None,
) -> GraphExtraction:
    """Entities, mentions, relations and aliases from ``(chunk_key, record)`` rows."""
    pk_index = pk_index or {}
    names: dict[tuple[str, str], dict[str, int]] = {}
    attrs: dict[tuple[str, str], tuple[tuple[str, str], ...]] = {}
    mentions: list[Mention] = []
    relations: list[RelationRef] = []
    aliases: dict[tuple[str, str, str], Alias] = {}
    rows = 0
    fk_specs = [
        (fk, pk_index.get(fk.ref_table, {}), _relation_name(fk.column)) for fk in foreign_keys
    ]
    col_caches: list[dict[Any, tuple[str, str] | None]] = [{} for _ in columns]
    for chunk_key, record in records:
        rows += 1
        found: list[tuple[str, str, str]] = []  # (type, key, relation name)
        for col, col_cache in zip(columns, col_caches, strict=True):
            raw = record.get(col.name) if col.name in record else _value(record, col.name)
            if raw is None:
                continue
            try:
                hit = col_cache.get(raw, False)
            except TypeError:  # unhashable value
                continue
            if hit is False:
                text = _text(raw)
                key = normalise_name(text, entity_type=col.type) if text is not None else ""
                hit = (text, key) if key else None
                if len(col_cache) < 100_000:
                    col_cache[raw] = hit
            if hit is None:
                continue
            text, key = hit
            ref = (col.type, key)
            bucket = names.get(ref)
            if bucket is None:
                bucket = names[ref] = {}
            bucket[text] = bucket.get(text, 0) + 1
            mentions.append(Mention(key, col.type, chunk_key, -1, -1, text, "field", 1.0, col.name))
            found.append((col.type, key, col.relation))
        for fk, index, rel in fk_specs:
            raw = _text(_value(record, fk.column))
            hit = index.get(raw) if raw is not None else None
            if hit is None:
                continue
            key, etype, name = hit
            names.setdefault((etype, key), {}).setdefault(name, 0)
            mentions.append(Mention(key, etype, chunk_key, -1, -1, raw, "fk", 1.0, fk.column))
            found.append((etype, key, rel))
        row_ref = None
        if row_entity is not None:
            name = _text(_value(record, row_entity.name_column))
            pk = _text(_value(record, row_entity.primary_key))
            if name and pk:
                key = row_entity_key(name, pk, row_entity)
                if key:
                    row_ref = (row_entity.type, key)
                    bucket = names.setdefault(row_ref, {})
                    bucket[name] = bucket.get(name, 0) + 1
                    attrs[row_ref] = (("table", table), ("pk", pk))
                    mentions.append(
                        Mention(
                            key,
                            row_entity.type,
                            chunk_key,
                            -1,
                            -1,
                            name,
                            "field",
                            1.0,
                            row_entity.name_column,
                        )
                    )
                    pk_key = normalise_name(pk)
                    aliases[(pk_key, row_entity.type, key)] = Alias(
                        pk_key, pk, key, row_entity.type, "structured_id", 1.0
                    )
        if row_ref is not None:
            for etype, key, rel in found:
                if (etype, key) != row_ref:
                    relations.append(
                        RelationRef(
                            row_ref[1], row_ref[0], key, etype, rel, chunk_key, 1, "structured"
                        )
                    )
        elif len(found) > 1:
            for i, (t1, k1, _) in enumerate(found):
                for t2, k2, rel in found[i + 1 :]:
                    if (t1, k1) != (t2, k2):
                        relations.append(
                            RelationRef(k1, t1, k2, t2, rel, chunk_key, 1, "structured")
                        )
    entities = []
    for ref, surfaces in names.items():
        display = max(surfaces.items(), key=lambda kv: (kv[1], kv[0]))[0]
        entities.append(EntityRef(ref[1], display, ref[0], "structured", attrs.get(ref, ())))
        for surface in surfaces:
            alias_key = normalise_name(surface)
            if alias_key and alias_key != ref[1]:
                aliases.setdefault(
                    (alias_key, ref[0], ref[1]),
                    Alias(alias_key, surface, ref[1], ref[0], "name", 1.0),
                )
    stats = {
        "rows": rows,
        "structured_entities": len(entities),
        "structured_mentions": len(mentions),
        "structured_relations": len(relations),
    }
    return GraphExtraction(
        tuple(entities), tuple(mentions), tuple(relations), tuple(aliases.values()), stats
    )


def detect_foreign_keys(
    profiles: Mapping[str, Mapping[str, Any]],
    samples: Mapping[str, Sequence[Mapping[str, Any]]],
    *,
    primary_keys: Mapping[str, str] | None = None,
    min_containment: float = 0.9,
    min_distinct: int = 3,
) -> list[ForeignKey]:
    """Key columns found by sampled value containment: ``A.col`` references ``B.key`` when at
    least ``min_containment`` of A's sampled distinct values are B's key values. Keys are the
    declared primary keys, else unique text/integer columns; integer columns need a name
    signal (``customer_id``, ``account_no``) because small integers are contained everywhere."""
    primary_keys = primary_keys or {}
    keys: dict[str, list[tuple[str, set[str]]]] = {}
    for table, profile in profiles.items():
        rows = samples.get(table, ())
        if not rows:
            continue
        cols = []
        for col in profile.get("columns", ()):
            name = str(col.get("name", ""))
            declared = primary_keys.get(table) == name
            unique = (
                not col.get("distinct_capped")
                and int(col.get("distinct") or 0) == int(profile.get("rows") or -1)
                and col.get("type") in ("text", "integer")
            )
            if declared or unique:
                values = {str(v) for r in rows if (v := _value(r, name)) is not None}
                if len(values) >= min_distinct:
                    cols.append((name, values))
        keys[table] = cols
    found: list[ForeignKey] = []
    for table, profile in profiles.items():
        rows = samples.get(table, ())
        for col in profile.get("columns", ()):
            name = str(col.get("name", ""))
            if primary_keys.get(table) == name or col.get("type") not in ("text", "integer"):
                continue
            values = {str(v) for r in rows if (v := _value(r, name)) is not None}
            if len(values) < min_distinct:
                continue
            folded = re.sub(r"[^a-z0-9]+", "_", name.casefold()).strip("_")
            best = None
            for ref_table, ref_cols in keys.items():
                if ref_table == table:
                    continue
                stem = re.sub(r"[^a-z0-9]+", "_", ref_table.rsplit(".", 1)[-1].casefold()).rstrip(
                    "s"
                )
                for ref_col, ref_values in ref_cols:
                    if col.get("type") == "integer" and not (
                        _KEYISH.search(folded) and stem and stem in folded
                    ):
                        continue
                    share = len(values & ref_values) / len(values)
                    if share >= min_containment and (best is None or share > best.containment):
                        best = ForeignKey(name, ref_table, ref_col, round(share, 3))
            if best is not None:
                found.append(best)
    return found
