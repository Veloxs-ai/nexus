# Nexus 3.2.0 – 3.4.0: what changed and how to use it

> **Covers:** 3.2.0, 3.3.0 and 3.4.0 (the rest of `docs/` describes 3.1.1 behaviour, which
> still holds unless this page says otherwise). Source of truth: [CHANGELOG.md](../CHANGELOG.md).
> Everything below is standard library only: none of these releases added a dependency, and
> no public method was renamed or removed.

## Contents

1. [Exact table answers over every row (3.2.0)](#1-exact-table-answers-over-every-row-320)
2. [Document routing and map-reduce (3.2.0)](#2-document-routing-and-map-reduce-320)
3. [Grounding verifier (3.2.0)](#3-grounding-verifier-320)
4. [Processing, chunking, PII and performance (3.2.0)](#4-processing-chunking-pii-and-performance-320)
5. [Knowledge graph (3.3.0)](#5-knowledge-graph-330)
6. [Entity typing, review helpers and parsers (3.4.0)](#6-entity-typing-review-helpers-and-parsers-340)
7. [Upgrade notes](#7-upgrade-notes)

---

## 1. Exact table answers over every row (3.2.0)

Questions such as "total refunds by customer last quarter" are answered from every stored
row, not from the few chunks a vector search returns. A planner (your LLM) writes a small JSON
spec; Nexus validates it against the table's profile and computes it either in Python or as
one parameterised SQL statement where the rows are stored.

| Module | What it does |
|---|---|
| `nexus.table_profile` | `profile_records(records)`: per-column type, nulls, distinct count, top values, min/max, nested fields. `profile_text` renders a profile as one planner line; `link_columns(question, profiles)` keeps the columns a question is about. |
| `nexus.record_spec` | Spec v2 and `parse_spec(spec, profile, join_profile=None, current=True)` → `RecordQuery`: `and`/`or`/`not`, `is_null`, `count_distinct`, several named metrics, `order_by` + `limit`, `date_trunc` groups, `having`, `fields`, nested fields (`"address.city"`), one join. Field names are allow-listed from the profile; dirty spellings are matched and missing values reported with the closest stored ones. v1 specs are unchanged. |
| `nexus.record_eval` | `query_records(records, spec)`: the Python engine (the reference for SQL). |
| `nexus.record_sql` | `compile_query(query, "postgresql" \| "sqlite", ChunkTable(...))` → one statement over records stored in chunk metadata; `read_result` gives the same `RecordResult`. Every value and JSON path is a bound parameter. `unicode_lower(conn)` makes SQLite's `lower()` fold like PostgreSQL. |
| `nexus.record_render` | `RecordResult` and the Markdown result text both engines share. |

```python
import json, sqlite3
from nexus.table_profile import profile_records
from nexus.record_spec import parse_spec
from nexus.record_eval import query_records
from nexus.record_sql import ChunkTable, compile_query, read_result, unicode_lower

rows = [{"order_id": i, "customer": ["Acme", "Initech", "Hooli"][i % 3], "amount": 10.0 * i}
        for i in range(1, 31)]
spec = {"metric": "sum", "field": "amount", "group_by": "customer",
        "order_by": [{"metric": "sum", "desc": True}], "limit": 2}

print(query_records(rows, spec).text)          # Python engine

db = sqlite3.connect(":memory:"); unicode_lower(db)
db.execute("CREATE TABLE chunks (document_id TEXT, chunk_index INT, metadata TEXT)")
db.executemany("INSERT INTO chunks VALUES (?, ?, ?)",
               [("orders.csv", i, json.dumps({"record": r})) for i, r in enumerate(rows)])
q = parse_spec(spec, profile_records(rows))
compiled = compile_query(q, "sqlite",
                         ChunkTable("chunks", "c.document_id = ?", ("orders.csv",), layout="record"))
print(read_result(compiled, db.execute(compiled.sql, compiled.params).fetchall(), len(rows)).text)
```

Both print the same table (Acme 1,650; Hooli 1,550; "…and 1 more group(s)"). SQL equals the
Python engine on 3,140 randomised specs. On SQLite, 200,000 rows: count 0.18 s, grouped top 3
1.06 s, join with two filters 2.6 s; the rows never enter application memory.

## 2. Document routing and map-reduce (3.2.0)

* `nexus.doc_routing.rank_documents(question, documents, vector=, chunks=, named=, mentions=)`
  orders a catalog (`document_id`, `document_name`, `summary`) by BM25 over names and summary
  heads, fused by weighted RRF with your vector ranking and keyword hits; it returns
  `RankedDocument(id, score, reasons)`. `question_mentions` finds the names and ids a question
  mentions; `candidate_documents` finds every document a "list every / how many" question
  needs; `knowledge_index` builds a bounded index of the catalog for the planner.
* `nexus.map_reduce`: `excerpt`, `plan_batches(excerpts, batch_tokens=6000,
  batch_documents=12, max_documents=1000, max_tokens=300_000)` (with a cost cap: documents
  past it are `skipped`), `MAP_SYSTEM` / `map_prompt` / `parse_map`, `reduce_groups` /
  `reduce_prompt`, and `coverage_note(read, candidates, contributing)`, which says whether the
  answer covers every candidate document or only part of them.

`rank_documents` over 5,000 documents: 203 ms the first time, 25 ms cached.

## 3. Grounding verifier (3.2.0)

`nexus.grounding.check_answer(answer, passages, score=None, question="")` splits an answer
into claims with their citations (`[2]`, `[2][3]`, `[2, 3]`) and checks each claim against the
passages it cites: every figure, id and date must be there (`30 days` = `thirty days`,
`45,000` = `45k`, `5 March 2026` = `2026-03-05`), content-word overlap decides clear cases,
and an optional cross-encoder (`score`, e.g. `NexusClient.rerank`) scores the rest.
`strip_unsupported(answer, report)` removes unsupported claims.

```python
from nexus.grounding import check_answer
report = check_answer("Refunds are paid within 30 days [1].",
                      {1: "We pay refunds within thirty days."})
report.faithfulness                 # 1.0
[c.status for c in report.checks]   # ['supported']
```

About 5 ms for 20 cited claims without the cross-encoder.

## 4. Processing, chunking, PII and performance (3.2.0)

* **Token-bounded chunks.** Every `process_*` method caps a chunk at the embedder's window
  (450 tokens for `bge-small-en-v1.5`); a longer chunk becomes parts that repeat its context
  header and carry `metadata.part` / `parts` / `parent_chunk_id`. `NexusClient(chunk_max_tokens=)`
  or `NEXUS_CHUNK_MAX_TOKENS` lowers the cap (`0` turns it off).
* **Row records for every tabular source.** CSV, spreadsheets, MySQL and MongoDB chunks carry
  the masked row as `metadata.record` (or `records` for row groups): the input of section 1.
* **Column-aware PII masking for records** (`GuardrailsEngine.classify_columns`,
  `mask_record`, `mask_records`): PII columns masked whole, identifiers and numbers never
  masked; optional deterministic tokens (`[EMAIL:3f9a1c2b7d]`) keep grouping working.
* **PDF**: a standard-library reader (xref streams, object streams, broken files, CMaps,
  CID fonts), encrypted PDFs with an empty password (RC4, AES-128, AES-256), two-column pages
  read column by column, scanned pages OCR'd (with the `[ocr]` extra) including strip/tile scans.
* **Audio**: MP3, M4A/AAC, OGG/Opus and FLAC via the `[video]` extra.
* **Record pages** (`nexus.processing.record_pages`): ServiceNow, Jira and file rows rendered
  as the Markdown page that is chunked.

Selected timings against 3.2.0-pre (same machine): CSV 200k rows 57.2 s → 33.4 s; PDF 200
pages 1.79 s → 0.93 s; XLSX 200k rows 9.2 s / 878 MB → 6.4 s / 160 MB; keyword search over
80k documents 143 ms → 21 ms per query; hybrid search 72.9 ms → 9.0 ms.

## 5. Knowledge graph (3.3.0)

`nexus.graph` is one import for a knowledge graph under the knowledge base. Pure functions,
no I/O: you store the rows.

```python
from nexus.graph import (TableInput, ForeignKey, extract_graph, IncrementalGraph,
                         CSRGraph, leiden, pagerank, ego_subgraph, entity_id)

x = extract_graph(
    tables=[TableInput("customers", customer_rows, primary_key="customer_id"),
            TableInput("orders", order_rows,
                       foreign_keys=[ForeignKey("customer_id", "customers", "customer_id")])],
    texts=[(chunk_id, masked_text, document_id), ...],
)
x.entities, x.mentions, x.relations, x.aliases
```

* **Structured entities** from table rows: entity columns from the table profile (never PII
  columns), one node per row for tables with a key and a name column, typed relations named
  after the columns, foreign keys found by `detect_foreign_keys` (sampled value containment).
* **Text mentions without an NER model**: a gazetteer of known names (longest match), ids
  (`INC0012345`, `C-1014`), abbreviations (`Service Level Agreement (SLA)`), capitalised spans
  with precision filters, noun-phrase concepts as `candidate` entities, `co_mentioned` relations.
* **Resolution**: `normalise_name`, `resolve(candidates, existing, auto_merge=0.92,
  propose=0.80)`, `apply_resolution`. Person and org never merge; risky merges are proposed only.
* **Incremental maintenance**: `mention_delta`, `IncrementalGraph.add` / `remove_chunks`.
* **Structure**: `CSRGraph`, `leiden` (seeded, warm-startable), `pagerank`,
  `personalized_pagerank`, `ego_subgraph`, `community_summary_inputs` / `community_summary_prompt`.
* **Evaluation**: `nexus.graph_eval.score_extraction(extraction, gold)`.

`extract_mentions` reads about 3 MB of text per second per core; Leiden on 100,000 nodes and
1M edges takes about 7 s.

## 6. Entity typing, review helpers and parsers (3.4.0)

### Text entity typing

Text-only typing accuracy went from 0.56–0.64 to 0.97–1.00 with precision and recall kept or
improved. Each capitalised name is typed from its own words (titles, `Project X`, legal
suffixes, departments such as "Legal" or "Customer Success", known organisations and
products, model numbers such as "Zephyr X2", about 2,900 given names and 3,700 places) and its
context ("the customer X", "joined X", "the X migration", "the X office", "in X"). Every
mention of a name in a document gets one type; "Olivia" takes the type of "Olivia Chen" in
the same document. Word lists load on first use (about 1 ms).

| Labelled set (text only) | Typing 3.3.0 → 3.4.0 | Precision | Mention recall |
|---|---|---|---|
| 40 development passages | 0.58 → 0.98 | 1.00 → 1.00 | 0.99 → 1.00 |
| 20 held-out passages | 0.63 → 1.00 | 1.00 → 1.00 | 0.98 → 1.00 |
| 15 independent passages | 0.64 → 0.97 | 0.97 → 1.00 | 0.98 → 1.00 |
| 25 blind passages (written before the work) | 0.56 → 0.99 | 0.90 → 0.97 | 0.86 → 0.99 |

### New graph APIs

```python
from nexus.graph import (extract_graph, merge_proposals, resolve, guess_primary_key,
                         promote_concepts, ForeignKey)

guess_primary_key(["order_no", "id", "customer_id"], rows, table="orders")   # "id"
guess_primary_key(profile["columns"], table="tickets", profile=profile)       # whole-table counts

found = []
x = extract_graph(texts=texts, tables=tables, proposals=found)
found[0]   # MergeProposal(source_type, source_key, target_type, target_key, score, reason,
           #               source_name, target_name); reason: ambiguous | both_structured |
           #               legal_suffix | similar_name
merge_proposals(resolve(candidates, known))   # the same list from a Resolution

decision = promote_concepts(x, texts={chunk_id: text}, documents={chunk_id: document_id})
decision.promoted, decision.boilerplate, decision.rare
x = decision.apply(x)      # concepts in 2+ documents and not template text become active

fk = ForeignKey("customer_id", "customers", "customer_id", table="orders")
fk.from_table, fk.to_table  # "orders", "customers"; detect_foreign_keys fills `table`
```

### Parsers moved into Nexus

```python
from nexus.processing.github_markdown import github_file_markdown, github_issue_markdown
from nexus.processing.cdc_ddl import ddl_cleared_tables, parse_ddl

github_file_markdown("acme/app", "main", "docs/README.md", text)
# "# docs/README.md\n\nRepository: acme/app · Branch: main\nLink: ...\n\n<body>"
# Markdown: front matter as plain lines, MDX imports dropped, relative links made absolute;
# other files: one fenced block that inner backticks cannot close.
github_issue_markdown("acme/app", issue, comments, reviews, review_comments)

ddl_cleared_tables("DROP TABLE IF EXISTS shop.orders, `tmp` CASCADE")   # ['orders', 'tmp']
ddl_cleared_tables("RENAME TABLE a TO b; TRUNCATE c", wanted=["a"])      # ['a']
parse_ddl("ALTER TABLE t RENAME TO t2")
# [DdlChange(verb='rename', tables=(('t',),), renames=((('t',), ('t2',)),))]
```

## 7. Upgrade notes

* 3.3.0: `MetadataConfig.legacy_entities` is `False` by default, so chunk metadata's
  `entities` is empty; use `nexus.graph` for entities.
* 3.4.0: names are typed per document, so a name typed `entity` in 3.3.0 may now be `org`,
  `person`, `place`, `product` or `project`. Entity keys depend on the type for people
  (token-sorted) and organisations (legal suffix), so stored graphs pick up the new types on
  their next rebuild; `resolve` upgrades `entity` rows to the specific type.
* `ForeignKey` gained a fifth field, `table`, with a default: positional construction with
  four fields still works.
