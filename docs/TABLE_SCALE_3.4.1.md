# Table-scale building blocks (3.4.1)

Nexus 3.4.1 adds generic pieces for applications that keep large tables and many documents:
exact table answers without parsing JSON per row, rollups that answer common questions without
reading rows, index and pgvector SQL, and bounds for very large cells. Nothing here knows a
schema: every function takes the caller's table, column and field names. Standard library only.

## 1. One row per record, with typed slots (`nexus.record_sql`, `nexus.record_slots`)

`ChunkTable(layout="row")` reads records from a table with one row per record, whose JSON
column (`metadata=`) is the record itself. `columns=` maps fields to typed columns of the same
row, which the compiled statement reads instead of the JSON:

```python
from nexus.record_slots import plan_slots, slot_columns, slot_values
from nexus.record_spec import parse_spec
from nexus.record_sql import ChunkTable, compile_query

slot_map = plan_slots(profile, text=8, number=8, date=4, sample=rows[:2000])
# {"v": 1, "rows": ..., "slots": [{"path": ["order_no"], "name": "order_no", "kind": "text",
#                                  "column": "t1"}, ...]}
values = slot_values(row, slot_map)      # {"t1": "SO-1", "n1": 12.5, "d1": "2026-01-02T00:00:00Z"}

source = ChunkTable("my_records", "c.table_id = ?", (table_id,), metadata="record",
                    order="row_no", layout="row", columns=slot_columns(slot_map))
compiled = compile_query(parse_spec(spec, profile), "postgresql", source, placeholder="%s")
```

- `plan_slots` takes key-like columns first, then categories, then the fullest columns; numbers
  and dates get number/date slots unless the sample shows they would not read back exactly.
- A slot holds a value only when SQL gives back exactly the JSON's text (text: any scalar;
  number: integers below 2**53 and shortest-form decimals with at most 13 significant digits and
  at least 0.001; date: `YYYY-MM-DD` and `YYYY-MM-DDTHH:MM:SSZ`, stored as UTC). Otherwise the
  slot is NULL and that row's JSON is read: results never change, only speed.
- Column types: PostgreSQL `TEXT` / `NUMERIC` / `TIMESTAMPTZ`; SQLite `TEXT` / `NUMERIC` /
  `TEXT`.
- Top-level `eq` / `in` conditions add index-friendly conditions on the source rows: the folded
  text of a text slot, a number slot (`IN (...) OR IS NULL`), or (PostgreSQL) the folded JSON
  text. Index them with `expression_index_sql` (section 3).

## 2. Rollups (`nexus.table_rollups`)

```python
from nexus.table_rollups import answer_from_rollups, apply_row_change, build_rollups

rollups = build_rollups(rows, profile)          # plain JSON; store it with the profile
apply_row_change(rollups, old_row, new_row)     # insert: old None; delete: new None
result = answer_from_rollups(parse_spec(spec, profile), rollups)  # RecordResult or None
```

Answers count / sum / avg / min / max (and count_distinct of the filtered column) over the
table, filtered by conditions on one rolled column, or grouped by one rolled column or a date
column by month. Rolled columns: every value known in the profile and at most 50 values; sums
are exact decimals. It returns None for anything else (two filtered columns, a column with many
values, a min/max whose extreme row was deleted): run the SQL then. Only pass rollups built
from the current rows.

## 3. Index advice (`nexus.index_advice`)

```python
from nexus.index_advice import expression_index_sql, recommend_indexes, sql_literal

for advice in recommend_indexes(profile, recent_specs, max_indexes=3, exclude=slotted_paths):
    print(advice.name, advice.reason, advice.uses)   # "lookup" | "range" | "key"

expression_index_sql("my_records", "record", "customer", lead=["table_id"],
                     where_sql="table_id = " + sql_literal(table_id), concurrently=True)
# CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_my_records_... ON my_records
#   (table_id, (lower(btrim((record #>> '{"customer"}'), E' \t\r\n')))) WHERE table_id = '...'
expression_index_sql("my_records", "t1", None, lead=["table_id"])  # a text slot
```

## 4. pgvector (`nexus.vector_sql`)

```python
from nexus.vector_sql import choose_strategy, knn_sql, vector_index_ddl

vector_index_ddl("chunks", "embedding", 384, quantize="halfvec", where_sql="kind <> 1")
strategy = choose_strategy(scope_vectors=30_000, total_vectors=10_000_000)  # "exact"
query = knn_sql("chunks", "embedding", 384, quantize="halfvec", where_sql="scope_id = %s",
                select="id, document_id", limit=40, strategy=strategy)
# run query.settings (SET LOCAL ...) then query.sql with [vector_text, scope_id]
```

A scope with at most 50,000 vectors is compared exactly (full recall; the distance is written
so no HNSW index is used); a larger one walks the HNSW graph with iterative scan and a
`hnsw.max_scan_tuples` sized to its share of the graph.

## 5. Very large cells and documents

- `estimate_tokens` counts ASCII text with string operations (same counts, 2-3x faster) and
  `fit_text` counts every character once however deep it splits (same pieces; a 5 MB cell
  0.72 s -> 0.26 s).
- `prepare_chunks(..., max_record_chars=4000, max_document_chars=None, report={})`: long record
  values are cut and listed under `record["_truncated"]` (`cap_record_values`), the chunk texts
  keep the full value; `max_document_chars` keeps the leading chunks (`cap_document`) and
  `report` says what was left out.
- `nexus.table_records`: `row_hash(record)` (40 hex characters, key order free) to tell changed
  rows apart; `embed_policy(profile, rows)` / `needs_vector(record, policy)`: only rows with
  free text need an embedding (no sample rows: embed everything).
- `profile_records` remembers the kind of each repeated text: same profile, 1.8x faster.

## 6. Routing over many documents (`nexus.doc_routing`)

```python
from nexus.doc_routing import DocumentIndex

index = DocumentIndex.build(catalog, version=catalog_version)  # once per catalog version
ranked = index.rank(question, vector=ids_by_summary, limit=50)  # same as rank_documents
```

The BM25 part of each term is computed once per index and reused by later questions.
