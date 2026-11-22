# Changelog

All notable changes to Nexus are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [3.4.1] — unreleased

### Changed

- Source modules split so that no library file is longer than 500 lines. Behaviour, output and public API are unchanged: every original import path still works (the old modules re-export what moved), processed payloads are identical on the benchmark corpus, and hot-path timings are unchanged.
  - `nexus.client`: `NexusClient` is assembled from mixins, one per `process_*` family: `client_document` (`process_document`, with format sniffing and routing in `client_routing`), `client_image`, `client_video`, `client_audio`, `client_databases` (MySQL, MongoDB), `client_tabular` (spreadsheets, SQLite), `client_office` (presentations, Word), `client_email`, `client_chat` (chat, Slack export) and `client_code` (code, OpenAPI). Names that `nexus.client` exposed at module level still resolve.
  - `nexus.record_spec`: the resolved-query dataclasses and limits moved to `nexus.record_query`.
  - `nexus.operations.signals`: failure-mode diagnosis (`Diagnosis`, `FAILURE_PATTERNS`, `diagnose`) moved to `signals_diagnosis`.
  - `nexus.operations.intents`: the default lexicon (`DEFAULT_LEXICON`, `Lexicon`) moved to `intents_lexicon`.
  - `nexus.processing`: `code` (into `code_model`, `code_python`, `code_polyglot`, `code_openapi`), `email_chat` (`email_mime`), `images` (`image_decode`), `markup_html` (`markup_html_tree`), `office` (`office_zip`, `office_word`, `office_docx`, `office_pptx`, `office_sheet`, `office_xlsx`), `pdf_fonts` (`pdf_glyphs`) and `pgoutput` (`pgoutput_decode`).
- A test fails when any source file passes 500 lines.
- `estimate_tokens` counts ASCII text with string operations instead of the regex (identical counts, 2-3x faster); `fit_text` with the built-in estimate counts every character once however deep it splits (identical pieces; it recounted each part at every level). `prepare_chunks` leaves a text over 16,384 characters to `fit_text` instead of counting it twice.
- `profile_records` classifies each distinct text once per column (up to 4,096) and handles plain numbers inline: identical profile, about 1.8x faster.
- `rank_documents` keeps each term's BM25 part per catalog index and builds only the documents it returns: identical ranking, about 2.5x faster on a warm 30,000-document catalog.

### Added

Generic building blocks for large tables and catalogs. Nothing in them knows a schema: tables, columns and fields are the caller's. Standard library only. Guide: [docs/TABLE_SCALE_3.4.1.md](docs/TABLE_SCALE_3.4.1.md).

- Records in a table with one row per record: `ChunkTable(layout="row", columns={path: (column, kind)})` (`nexus.record_sql`). The JSON column is the record; mapped fields are read from typed columns (`"text"`, `"number"`, `"date"`) and from the JSON on rows where the column is NULL, so results are the same as reading the JSON. Top-level `eq` / `in` conditions add index-friendly conditions on the source rows. The SQL building blocks moved to `nexus.record_sql_builder` (`ChunkTable` is still imported from `nexus.record_sql`); SQLite statements write the trimmed blanks as `char(32, 9, 13, 10)` (a constant, so an expression index matches).
- `nexus.record_slots`: `plan_slots(profile, text=8, number=8, date=4, *, sample=, names=, exclude=)` → slot map; `slot_values(record, slot_map)`; `slot_columns(slot_map)` (the `ChunkTable.columns` map); `text_slot`, `number_slot`, `date_slot` (what a slot can hold exactly).
- `nexus.table_rollups`: `build_rollups(rows, profile, max_groups=50, max_numbers=20)`, `apply_row_change(rollups, old, new)`, `answer_from_rollups(query, rollups)` → the same `RecordResult` as the engines, or None. Count / sum / avg / min / max per value of low-cardinality columns and per month of date columns, exact decimal sums, plain JSON.
- `nexus.index_advice`: `recommend_indexes(profile, recent_specs, max_indexes=3, *, exclude=, keys=True)` → `IndexAdvice(path, name, reason, uses, score)`; `expression_index_sql(table, column, path=None, dialect="postgresql", *, where_sql=, name=, form="folded", lead=(), concurrently=False, if_not_exists=True)`; `sql_literal(value)`.
- `nexus.vector_sql` (pgvector): `vector_index_ddl(table, column, dim, *, quantize=None|"halfvec", metric="cosine", where_sql=, m=16, ef_construction=64, name=, concurrently=False)`, `knn_sql(table, column, dim, *, exact=, quantize=, metric=, where_sql="TRUE", select="*", limit=40, placeholder="%s", strategy=, distance_alias="distance")` → `KnnQuery(sql, settings, strategy)`, `choose_strategy(scope_vectors, total_vectors=None, *, k=40, exact_limit=50000, ef_search=100, max_scan_cap=1000000)` → `Strategy(kind, ef_search, max_scan_tuples, reason)`.
- `nexus.processing.record_caps`: `cap_record_values(record, max_chars=4000, *, marker="_truncated")` (long text values cut, the cut fields and their lengths listed under the marker) and `cap_document(chunks, max_chars)` → `(chunks, report)`. `prepare_chunks` takes `max_record_chars=`, `max_document_chars=` and `report=` (all off by default).
- `nexus.table_records`: `row_hash(record, *, exclude=())` (40 hex characters, independent of key order), `embed_policy(profile, rows=None, *, min_text_chars=40, sample=2000)` and `needs_vector(record, policy)` (only rows with free text need an embedding; without sample rows every row does), and the record caps re-exported.
- `nexus.table_profile.key_like(column, rows)`: a column with a different value on every row, also past the distinct cap.
- `nexus.doc_routing.DocumentIndex`: `DocumentIndex.build(documents, *, id_key=, name_key=, summary_key=, version=)` and `.rank(question, ...)`, the same ranking as `rank_documents` without re-reading the catalog per question.

### Performance

One core, medians, before = this branch after the split, after = this release (scratch data, deleted after):

| Case | Before | After |
|---|---|---|
| `estimate_tokens`, 5 MB text | 207 ms | 103 ms |
| `fit_text`, one 5 MB cell | 716 ms | 258 ms |
| `prepare_chunks`, 8 rows with 17 MB of cells | 3.14 s | 0.91 s |
| ... with `max_record_chars=4000`: record metadata | 17.4 MB | 0.40 MB |
| `profile_records`, 200k rows x 7 columns | 1.47 s | 0.80 s |
| `prepare_chunks`, 200k row chunks | 2.76 s | 1.59 s |
| `rank_documents`, 30k documents, 3 questions (warm) | 562 ms | 221 ms |
| Records on SQLite, 100k rows, point lookup by order number | 767 ms (chunk JSON) | 0.4 ms (row layout, text slot, expression index) |
| ... sum by region / best month | 671 / 728 ms | 295 / 323 ms (slots); < 0.1 ms (rollups) |

Outputs are identical before and after for `fit_text`, `prepare_chunks` (both cases), `profile_records`, `rank_documents` and every records answer. The knowledge-graph quality sets score the same (hand-labelled 1.00 / 1.00 / 0.98, held-out 1.00 / 1.00 / 1.00, independent 1.00 / 1.00 / 0.97, blind 0.97 / 0.99 / 0.99, synthetic 1.00 / 1.00 / 1.00 precision / mention recall / typing). The row layout and rollups are checked against the Python engine on randomised data and specs (rollups: over 1,000 answered specs, and after 400 random inserts, updates and deletes). PostgreSQL statements are generated and parameter-checked here but were not run against a PostgreSQL server.

## [3.4.0] — 2026-11-22

Text entity typing without a model, the review and key helpers a knowledge-graph product needs, and two parsers that applications were carrying themselves (GitHub Markdown, CDC DDL). Standard library only: no new dependency. No public method is renamed or removed.

### Added

- Text entity typing (`graph_typing`, `graph_names`, `graph_places`, `graph_orgs`): every capitalised span gets weighted type votes from its own words (honorific, `Project X` and `X Initiative` / `X Programme`, legal suffix or org head word, departments such as "Legal", "Customer Success", "HR"; unit words such as "Vendor Management Office"; known organisations and products; model numbers "Zephyr X2", "Atlas 300", "Nimbus 12"; org industry words "Tidewater Logistics"; about 2,900 given names and 3,700 countries, regions, states and cities; product and document head words) and from its context (the word before: "the customer X", "joined X", "in X", "at X"; the words after: "the X migration", "the X upgrade", "the X office", "X requested"). Coordinated names share a type ("Soylent, Cyberdyne and Vandelay Industries"). Votes are summed per name and document, so every mention of a name in a document gets one type, and a lone "Olivia" or "Bluepeak" takes the type of "Olivia Chen" or "Bluepeak Energy" there; a name still untyped takes the type it got in other documents of the call. Department words open a sentence only before a verb ("Legal will review"), never as "Head of Sales". Word lists are packed strings built into sets on first use (`graph_lexicon.given_names()`, `places()`, `ambiguous_names()`, `ambiguous_places()`; `GIVEN_NAMES` / `PLACES` still resolve). Ambiguous places ("Reading", "Phoenix", "Aurora") need a place cue.
- `guess_primary_key(columns, rows, table=, profile=)` and `key_like_column(name)` (`graph_keys`): the column that identifies a row (`id`, `<table>_id`, `*_no`, `*_code`, `*_number`, `uuid`, camelCase `customerId`), unique and never null in the profile or the rows; `id` / `<singular>_id` first.
- `merge_proposals(resolution, names=)` → `MergeProposal(source_type, source_key, target_type, target_key, score, reason, source_name, target_name)` (`graph_review`): a stable, de-duplicated list (one row per pair, by score then keys) with the reason the pair was not merged: `ambiguous`, `both_structured`, `legal_suffix`, `similar_name`. `Resolution.proposal_reasons` is aligned with `Resolution.proposals`; `extract_graph(proposals=[...])` collects the list.
- `promote_concepts(extraction, texts, documents=, min_documents=2, window=4, template_share=0.6, max_document_share=0.5, min_corpus=10)` → `ConceptPromotion(promoted, boilerplate, rare)` with `.apply(extraction)`: noun-phrase concepts become active when they appear in two or more documents and are not template boilerplate (one sentence context shared by most of their documents, e.g. "payable within thirty days").
- `ForeignKey.table` (the owning table), with `from_table` / `to_table`; `detect_foreign_keys` fills it and `extract_graph` fills it from `TableInput.name` (without changing the caller's object).
- `nexus.processing.github_markdown`: `github_file_markdown(repo, branch, path, text, url=, absolute_links=True)` (header with path, repository, branch and link; Markdown kept with YAML front matter as plain lines, MDX import/export lines dropped, relative links and images made absolute outside code blocks; other files in a fence longer than any backtick run, with a language), `github_issue_markdown(repo, item, comments, reviews, review_comments, state=, labels=, url=)`, `code_fence`, `is_markdown_path`, `markdown_links_absolute`.
- `nexus.processing.cdc_ddl`: `parse_ddl(query)` → `DdlChange(verb, tables, renames)` and `ddl_cleared_tables(query, wanted=())` for `TRUNCATE`, `DROP [TEMPORARY] TABLE [IF EXISTS]`, `RENAME TABLE a TO b, ...` and `ALTER TABLE a RENAME TO b`: several statements, leading comments, MySQL `/*! */` hints, quoted (`` ` ``, `"`, `[]`) and qualified names, `ONLY`, `RESTART IDENTITY`, `CASCADE`.
- `graph_resolve.key_from_base(text, entity_type)`: `normalise_name` for an already normalised generic key.

### Changed

- Capitalised spans are typed per document after all of its chunks are read (was: per span). A one-word name at a sentence start followed by an org verb is typed `org` ("Gringotts requested ...", was `entity`). Tax and employment forms (`W-9`, `W-8BEN`, `I-9`) are no longer record ids.

### Quality

Measured with `nexus.graph_eval` (text only, no gazetteer; precision over active entities):

| Labelled set | Entities | Precision 3.3.0 → 3.4.0 | Mention recall | Typing |
|---|---|---|---|---|
| 40 hand-labelled passages (development) | 115 | 1.00 → 1.00 | 0.99 → 1.00 | 0.58 → 0.98 |
| 20 held-out passages | 46 | 1.00 → 1.00 | 0.98 → 1.00 | 0.63 → 1.00 |
| 15 independent passages | 60 | 0.97 → 1.00 | 0.98 → 1.00 | 0.64 → 0.97 |
| 25 blind passages (`tests/graph_samples_blind.py`, written before this work, never edited) | 98 | 0.90 → 0.97 | 0.86 → 0.99 | 0.56 → 0.99 |
| Synthetic contracts, tickets, calls + tables | 141 | 1.00 → 1.00 | 1.00 → 1.00 | 1.00 → 1.00 |

The blind set was written by the same team that wrote the rules, so it is honest about over-fitting to the development sets but not a substitute for a reviewer's set.

### Performance

`extract_mentions` without a gazetteer, 10,000 chunks (17.8 MB, capitalised-name dense), one core, best of 3: 4.73 s → 5.65 s (3.76 → 3.15 MB/s). The word lists (2,902 given names, 3,648 places) load on first use in about 1 ms. Gazetteer, structured, resolution and community paths are unchanged.

## [3.3.0] — 2026-11-22

Knowledge graph under the knowledge base: deterministic entities and relations from table rows, entity mentions in text without an NER model, entity resolution with an alias table, incremental (per-chunk) maintenance, Leiden communities, PageRank and ego-graph selection. Pure functions, standard library only: no new dependency, no I/O (the caller owns storage). No public method is renamed or removed.

### Added

- `nexus.graph`: one import for the whole knowledge-graph API (re-exports below), plus `extract_graph(texts=, tables=, gazetteer_names=, known_aliases=)`: structured entities first, a gazetteer built from them (names, aliases, primary-key ids), text mentions, then resolution, in one call. `TableInput(name, records, primary_key=, profile=, column_kinds=, hints=, foreign_keys=)`; `gazetteer_from(entities, aliases)`.
- Data shapes (`nexus.processing.graph_types`): `EntityRef` (`key`, `name`, `type`, `origin`, `attributes`, `status`), `Mention` and `RelationRef` (named tuples, keyed by the caller's opaque chunk key), `Alias`, `GraphExtraction`; `ENTITY_TYPES` (person, org, place, product, project, record, concept, entity); `EXTRACTOR_VERSION = "kg1"`; deterministic ids `entity_id(workspace, type, key)` and `relation_id(workspace, src, dst, type)` (uuid5; `co_mentioned` is symmetric) so stores upsert idempotently; `merge_extractions`.
- Structured extraction (`graph_structured`): `infer_entity_columns(profile, column_kinds=, hints=)` picks entity columns from a 3.2.0 `table_profile` (text, distinct ratio 0.001–0.95 with no lower bound when the column name gives a type: customer, assignee, product, region, short values, no dates/numbers/enums/codes, never a PII column by name or by `column_kinds`; type from a column-name lexicon, connector `hints` override it); `infer_row_entity` (one node per row only for tables with a primary key and a name/title column); `structured_graph(records, columns, table=, row_entity=, foreign_keys=, pk_index=)` gives `field` and `fk` mentions, typed relations named after the columns, and primary-key aliases (`structured_id`); `pk_index_for`; `detect_foreign_keys(profiles, samples)` by sampled value containment. Masked values (`[EMAIL]`, `[EMAIL:hash]`, `<PERSON>`, `****`) never become entities.
- Text extraction (`graph_text`, `graph_spans`, `graph_phrases`, `graph_tokens`, `graph_lexicon`): `extract_mentions(chunks, gazetteer=, config=TextGraphConfig(...), extra_detector=)` over `(chunk_key, text[, document_key])`: one tokenisation per chunk; `Gazetteer` (token trie, longest match, case rules: multi-word names any case, single words capitalised, short/ALL-CAPS words exact; org names also match without their legal suffix; names that point at two entities are dropped); ids (`INC0012345`, `C-1014`); abbreviation definitions both ways (`Service Level Agreement (SLA)`, `GDPR (General Data Protection Regulation)`) with document scope and `abbrev` aliases; capitalised spans with precision filters (sentence-start words need evidence, common words, months, weekdays, headings, ALL-CAPS heading lines, job titles and roles, a role word before a given name dropped ("CFO Daniel Abernathy" is Daniel Abernathy, a person), spans of 6+ words; "Boston and Chicago" and "Ravi Kumar of Acme Corp" are two names, "Bank of India" is one); typing by gazetteer, org suffix or head word, honorific or given name (word lists ship as package data), place list; noun-phrase concepts as `candidate` entities (C-value, at most 8 per chunk); `co_mentioned` relations per sentence with counts; an optional `extra_detector` hook for a caller-owned NER model.
- Resolution (`graph_resolve`): `normalise_name(name, entity_type=)` (NFKC, casefold, diacritics, `&` → `and`; person keys token-sorted without honorifics; org keys keep one canonical legal suffix: `ACME Corporation.` = `Acme Corp`); `AliasIndex.from_rows`, `blocking_keys`; `resolve(candidates, existing, auto_merge=0.92, propose=0.80)` → `Resolution(mapping, new_aliases, merges, proposals)`: generic → specific type upgrade, alias hits, hash blocking (key, org base, first token + length, acronym) and trigram/token Jaccard inside blocks of at most 50; person and org never merge, two structured entities and two different legal suffixes are only proposed, different numbers or primary keys never merge, a name matching two entities is proposed (ambiguous), never merged; `apply_resolution`.
- Incremental maintenance (`graph_delta`): `mention_delta(old, new)` / `touched_entities` (rows to delete and insert per chunk), `aggregate_relations` / `prune_relations` (evidence per chunk; co-mentions kept at 2+ or when one end is structured), and `IncrementalGraph` (in memory: `add(extraction, documents=)` replaces a chunk's rows, `remove_chunks(keys)`, counts per entity, `edges()` for communities; both return a `ChangeSet` with `edges_changed`).
- Communities and ranking (`nexus.retrieval.graph_community`, `graph_rank`): `CSRGraph.from_edges` (array-backed CSR, about 12 bytes per directed entry), `leiden(g, resolution=, seed=, max_levels=, theta=, initial=, max_seconds=)` (local moving, refinement, aggregation; seeded and deterministic; warm start), `modularity`, `pagerank`, `personalized_pagerank`, `degree_centrality`, `top_entities`, `ego_subgraph(focus, neighbours, hops=, limit=, node_weight=)` (best nodes within 1–3 hops, always connected to the focus), `community_label`, `members_hash`, `community_summary_inputs` and `community_summary_prompt` / `COMMUNITY_SUMMARY_SYSTEM` (what an LLM needs to summarise a community).
- `nexus.graph_eval.score_extraction(extraction, gold)`: entity precision, mention recall ("everything about X"), typing accuracy and a false-positive sample against `GoldEntity` labels.

### Changed

- The capitalised-word regex `entities` in chunk metadata (`enrichment.extract_metadata`) is now opt-in: `MetadataConfig.legacy_entities=False` by default, and the `entities` key is an empty list. Use `nexus.graph` for entities.

### Quality

Measured with `nexus.graph_eval` (precision over active entities; noun-phrase candidates are not scored):

| Labelled set | Entities | Precision | Mention recall | Typing |
|---|---|---|---|---|
| 40 hand-labelled enterprise passages (text only; used during development) | 115 | 1.00 | 0.99 | 0.58 |
| 20 held-out passages (text only; written after the rules were set) | 46 | 1.00 | 0.98 | 0.63 |
| 15 passages written by an independent reviewer (text only; never used for tuning) | 60 | 0.97 | 0.98 | 0.68 |
| Synthetic contracts, tickets, calls + customers/orders tables (tests) | 141 | 1.00 | 1.00 | 1.00 |
| Nexora RAG fixture S (549 text chunks, 5,220 rows) | 1,295 | 0.997 | 1.00 (planted customer 1.00) | 1.00 |
| Nexora RAG fixture M (6,269 text chunks, 207,520 rows) | 9,740 | 1.00 | 0.998 (planted customer 1.00) | 1.00 |

Text-only typing is low because single unknown names ("Hooli", "Workday") are typed `entity`; with structured entities in the gazetteer they take the structured type.

### Performance

Same 8-core machine, one core, Python 3.12, best of 3:

| Workload | Result |
|---|---|
| `structured_graph`, 200,000 rows x 2 entity columns | 0.85 s (236k rows/s); `profile_records` adds 1.4 s |
| `extract_mentions`, 10,000 chunks (13.2 MB) with a 100,000-name gazetteer | 4.3 s: 3.1 MB/s, 0.43 s per 1,000 chunks; 58 MB peak (traced) |
| `extract_graph` on fixture M (6,269 text chunks + 207,520 rows, with resolution) | 6.8 s |
| `CSRGraph.from_edges` + `leiden`, 100,000 nodes / 1M edges | 2.2 s + 7.2 s (warm start 4.5 s); CSR 23 MB, process peak 283 MB |
| `pagerank`, 100,000 nodes / 1M edges | 6.1 s |
| `ego_subgraph`, 2 hops, 50 neighbours per node, limit 300 | 0.6 ms p95 |
| Leiden on Zachary's karate club | modularity 0.4198 (the known optimum) |

### Known limits

- Text typing without a gazetteer is word-list based (honorifics, about 425 given names, about 435 places and regions, org suffixes).
- Noun-phrase concepts are POS-free; they stay `candidate` until a store sees them in 2+ documents.
- Names of 6+ words and lowercase brand names (`iPhone`) are not found in text unless they are in the gazetteer.
- Warm-started Leiden is about 1.6x faster than a cold run on the 1M-edge benchmark.
- Model numbers after a name are not part of it ("Zephyr X2" is found as "Zephyr"), and form names with a digit ("W-9") are typed `record`.

## [3.2.0] — 2026-11-22

One release with two parts: (1) processing, chunking, record, PII and performance work across every layer, and (2) exact table answers over every row, document routing, map-reduce and a grounding verifier. Standard library only: no new dependency. No public method is renamed or removed.

### Part 1 — Exact table answers, routing, map-reduce and grounding

Exact answers over every row of a table, computed where the rows are stored; document-level routing, map-reduce over every candidate document, and a grounding verifier for cited answers. Standard library only: no new dependency. No public method is renamed or removed.

#### Summary

- **Exact table answers over every row.** `table_profile` describes each column; `record_spec` (spec v2) resolves a planner's spec against the profile (allow-listed fields, dirty spellings matched, missing values reported with the closest stored ones); `record_sql` compiles it to one parameterised PostgreSQL JSONB / SQLite JSON1 statement that runs where the rows are stored; `record_eval` is the Python reference engine; `record_render` gives both engines the same result text. SQL equals the Python engine on 3,140 randomised specs (3 storage layouts, joins and dirty values included).
- **Document routing and map-reduce.** `doc_routing` ranks a catalog (BM25 + weighted RRF), finds the documents a "list every / how many" question needs, and builds a bounded knowledge index; `map_reduce` plans, prompts, parses and reduces per-document map calls under a cost cap and says when coverage is partial.
- **Grounding verifier.** `grounding.check_answer` checks every cited claim of an answer against the passages it cites (exact figures, ids and dates; content words; an optional cross-encoder), in milliseconds per answer.
- Standard library only; no new dependency, no public API renamed or removed.

#### Added

- `nexus.table_profile`: `profile_records(records)` describes each column of a table's records in one pass (type: integer / number / date / boolean / text / object / array / mixed; nulls and null %; distinct count, capped at 1,000 tracked values per column; every value when there are at most 50, else the top 10; min/max for numbers and dates; nested object fields one level down). `profile_text` renders a profile as one planner line; `link_columns(question, profiles)` keeps the columns a question is about when more than 10 tables or 40 columns are in scope (name words and value hits).
- `nexus.record_spec`: records spec v2 and `parse_spec(spec, profile, join_profile=None, current=True)` → `RecordQuery`. Adds `and`/`or`/`not` conditions, `is_null`, `count_distinct`, several metrics with names, `order_by` + `limit` (top N), `date_trunc` groups (day, week, month, quarter, year), `having`, list projection (`fields`), nested fields (`"address.city"`) and one join with a second table on a declared key (`inner` or `left`). v1 specs (`filters`, `metric`, `field`, `group_by`, `limit`) are unchanged. Field names are allow-listed from the profile. With a complete value list, a text value matches every stored spelling that normalises the same (`"mid market"` = `"Mid-Market"` = `"MID_MARKET "`), and a value that is not stored is reported with the closest stored values (`RecordQuery.not_found`, `impossible`) instead of computing 0.
- `nexus.record_eval`: `query_records(records, spec)` and `evaluate(query, records, join_records)`, the Python engine (the reference for the SQL engine).
- `nexus.record_sql`: `compile_query(query, "postgresql" | "sqlite", ChunkTable(...))` compiles a `RecordQuery` to one parameterised statement over records stored in chunk metadata (`record`, or `records` row groups), and `read_result` turns its rows into the same `RecordResult`. Every value, JSON path and constant is a bound parameter; results are bounded (at most 200 listed rows or 100 groups). `ChunkTable.layout="record"` reads one-row chunks with a single JSON parse per chunk on SQLite. `unicode_lower(sqlite_connection)` makes SQLite's `lower()` fold like PostgreSQL and Python.
- `nexus.record_render`: `RecordResult` (`kind`, `matched`, `total`, `columns`, `rows`, `listed`, `groups`, `not_found`, `notes`, `text`) and the Markdown result text shared by both engines.
- `nexus.record_values`: the value rules both engines share (`text_of`, `number_of`, `fold`, `normalize_value`, `key_text`).
- `nexus.doc_routing` (document-level routing): `rank_documents(question, documents, vector=, chunks=, named=, mentions=)` orders a catalog by relevance — BM25 over each document's name (x3) and summary head, fused by weighted Reciprocal Rank Fusion with the caller's summary-vector ranking, chunk keyword hits and named documents; the catalog index is cached by content (8 catalogs). `question_mentions(question)` finds the entities a question names (quoted phrases, capitalised names, ids such as `P1` / `C-1014`); `mentions_in(text, phrases)` checks whole-word matches. `candidate_documents(...)` returns every document a "list every / how many / everything about X" question needs read: the documents that mention its entities, else those whose keyword hits carry at least half of the question's IDF weight, plus the closest summary vectors. `knowledge_index(...)` renders the knowledge-index text (counts by type, the most relevant documents) within a token budget.
- `nexus.map_reduce`: the text side of map-reduce over many documents — `excerpt` (a document's first chunk plus the chunks with the question's words, or the whole document when small), `plan_batches` (map calls by token budget and count, with a cost cap: documents past it are `skipped`), `MAP_SYSTEM` / `map_prompt` / `parse_map` (one finding line per document, `NONE` dropped), `REDUCE_SYSTEM` / `reduce_groups` / `reduce_prompt`, and `coverage_note` ("every one of the N candidate documents was read" or "PARTIAL: read X of Y").
- `nexus.grounding`: `check_answer(answer, passages, score=None, question="")` splits an answer into claims (sentences, list items, table rows) with their inline citations (`[2]`, `[2][3]`, `[2, 3]`; list items take the citations of the line that introduces them) and checks each cited claim against the passages it cites: every figure, id and date must appear there (`45,000` = `45k` within its precision; small counts and figures the question states are exempt), the content-word share decides clear cases, and the cross-encoder (`score`, e.g. `NexusClient.rerank`) scores the rest on the best-matching window of each passage. Claims are `supported`, `unsupported` (missing figure or id, a citation to no passage, or almost nothing in common) or `unverified` (a loose paraphrase or weak match). `GroundingReport.to_dict()`, `cited_refs`, `strip_unsupported`.
- `nexus.text_terms`: the shared word, stem, number and id helpers of the three modules above (`terms`, `question_terms`, `query_words`, `numbers`, `key_tokens`).
- `nexus.figure_text`: `spell_figures(text)` writes English number words (`"one hundred and twenty"` → `120`, `"twenty-one"` → `21`) and long-form dates (`"March 5, 2026"`, `"5th of March 2026"` → `2026-03-05`) as digits; number words inside hyphenated names (`priority-one`) are kept. Grounding compares figures through it.

#### Performance

Measured on the same 8-core machine (SQLite 3.53, one row per chunk, best of 3), 200,000 rows:

| Workload | Time |
|---|---|
| `profile_records`, 200k rows x 7 columns | 1.43 s |
| SQL count, no filter | 0.18 s |
| SQL count, 2 equality filters | 0.42 s |
| SQL sum with 2 filters | 0.67 s |
| SQL group by customer, top 3 by sum | 1.06 s |
| SQL sum by month (`date_trunc`) | 1.00 s |
| SQL list, top 10 by amount | 0.80 s |
| SQL join (200k orders x 20 customers) with 2 filters, packed rows | 2.6 s |
| Python engine on the same queries (rows already in memory) | 0.10–1.90 s |

Document routing, map-reduce and grounding (same machine, best of 3):

| Workload | Time |
|---|---|
| `rank_documents`, 5,000-document catalog, first call (builds the index) / cached | 203 ms / 25 ms |
| `candidate_documents`, 5,000 keyword-hit chunks | 263 ms |
| `excerpt`, 1,000 documents of 8 chunks | 341 ms |
| `plan_batches`, 1,000 documents | 0.5 ms |
| `check_answer`, 20 cited claims, word and figure checks only | 5 ms |
| `check_answer`, a 6-claim answer with 4 paraphrases, MiniLM-L-6 cross-encoder (4-5 calls) | 53-92 ms p50, 157 ms max |

Grounding quality on Nexora's offline evaluation (fixtures S and M): no supported claim of a correct answer flagged unsupported; every claim with an altered figure or id, and every unrelated claim, flagged unsupported.

The SQL engine needs no rows in application memory. PostgreSQL reads JSONB without parsing it, so it is expected to be faster than these SQLite numbers; it was not measured here.

#### Fixed (before release)

- Records SQL: groups tied on the ordering metric now put the empty group last, as the Python engine does (the empty group's label was `''`, which sorted first and could change which groups a `limit` kept).
- `parse_spec`: a `limit` that is not a whole number raises `RecordQueryError` with the reason instead of `ValueError`.
- Grounding: a correct claim whose figure is written another way than in its passage (`30 days` / `thirty days`, `120` / `one hundred and twenty`, `5 March 2026` / `2026-03-05`, a year inside an ISO date, `FY2025` / `fiscal year 2025`) is no longer marked unsupported; a changed figure still is.

#### Known limits

- On PostgreSQL, a `week` bucket of an impossible calendar date (`2025-02-30`) fails the statement; the other buckets only read the text.
- SQLite's built-in `lower()` folds ASCII only; call `unicode_lower(connection)` for parity on non-ASCII text.
- Texts of JSON objects differ between engines (`{"a": 1}` vs `{"a":1}`); condition on their fields instead (`"address.city"`).
- On SQLite, a field whose name contains a double quote cannot be read (the query says so); a list without `fields` over such a table fails. PostgreSQL binds the path as an array and is not affected.
- Grounding does not convert units: `24 months` against `two years` is still reported unsupported. The cross-encoder measures relevance, not entailment.

### Part 2 — Processing, chunking, records, PII and performance

Data-loss, chunk-size, record and PII fixes for retrieval over everything a customer uploads or connects. No public method is renamed or removed; the outputs below change, as described under **Changed**.

#### Performance

Measured against 3.2.0-pre (commit 8dc3371) on the same 8-core machine, run back to back with nothing else running; CPU p50 unless noted. Outputs are identical except where **Changed** / **Fixed** say otherwise. Benchmarks: `bench.py` per layer (processing parsers, client/pipeline/tables, guardrails/PII, chunking/retrieval), re-runnable against any checkout with `--repo`.

| Workload | 3.2.0-pre | 3.2.0 |
|---|---|---|
| `process_document` CSV, 10k rows (wall / CPU) | 2.43 s / 6.40 s | 1.68 s / 4.29 s |
| `process_document` CSV, 200k rows (wall / CPU) | 57.2 s / 178 s | 33.4 s / 92 s |
| `process_mysql_table`, 20k rows | 2.09 s | 1.20 s |
| `process_pdf`, 200 pages (wall / CPU) | 1.79 s / 2.07 s | 0.93 s / 1.76 s |
| PDF text extraction, 400 pages | 1.53 s | 1.10 s |
| XLSX, 50k rows (CPU / peak memory) | 2.28 s / 219 MB | 1.51 s / 40 MB |
| XLSX, 200k rows (CPU / peak memory) | 9.24 s / 878 MB | 6.39 s / 160 MB |
| CSV parse, 100k rows (CPU / peak memory) | 629 ms / 156 MB | 441 ms / 140 MB |
| Slack export, 40 channels | 670 ms | 322 ms |
| `prepare_chunks`, long rows / `ChunkLimiter` corpus | 546 ms / 7.13 s | 263 ms / 3.63 s |
| Keyword search, 80k documents (per query) | 143 ms | 21 ms |
| Vector search, 32k entries (peak memory) | 3.56 s (39 MB) | 0.10 s (0.3 MB) |
| `RetrievalEngine.search` (hybrid) | 72.9 ms | 9.0 ms |
| `mask_records`, 200k rows | 13.6 s | 8.4 s |
| `mask_pii`, 1 MB multilingual text | 548 ms | 420 ms |
| Encrypt / decrypt, 1,000 values | 49 / 45 ms | 27 / 24 ms |
| Nexora offline eval (M fixture, 63,769 chunks): ingest | 13.9 s | 9.8 s |

Search quality: hybrid RRF MRR@10 0.695 -> 0.739 (weighted fusion unchanged at 0.9); keyword search returns the same order. Nexora's offline eval headline is unchanged (accuracy 0.706, hit@5 0.969, refusal correctness 1.0, false completeness 0).

Costs paid for accuracy: English `mask_pii` is 5-9% slower (cued national phone formats; phone recall 0.63 -> 0.73 at precision 1.0); `detect_pii` is about 1.7x slower because it now uses the masking spans; `validate_records` compares every duplicate's event time (50k records: 10 -> 36 ms); well-formed HTML is 4-5% slower (HTML5 implied end tags); a non-UTF-8 file pays about 0.2 ms for code-page detection; polyglot code emits five times as many chunks (one per method).

#### Added
- **Encrypted PDFs are read** (`nexus.processing.pdf_crypt`, standard library only): the standard security handler with RC4 (40-128 bit, revisions 2-3), AES-128 (`AESV2`, revision 4) and AES-256 (`AESV3`, revisions 5-6), crypt filters and `Identity`; the empty user password, then the empty owner password, is tried (most "secured" statements and forms). Streams are decrypted lazily, on first use. A file that needs a real password reports `PdfDocument.needs_password` and its pages `source="encrypted"` (they were `empty` with no reason). On the test files encrypted with pypdf (5 algorithms x 2 documents) the text is identical to the unencrypted file (word recall 1.0; was 0.0).
- **Two-column pages are read column by column** (`nexus.processing.pdf_columns`): when a page's baselines hold gutter-wide gaps and a vertical gutter separates two prose columns (each with a fifth of the text, lines filling their column, almost nothing crossing), the left column is read before the right, with full-width lines (titles, footers) in place. Tables and single-column pages keep stream order. Word-bigram recall on a row-wise two-column file: 0.872 -> 0.983 (pypdf 0.889). Pages without such gaps pay nothing (the detector is not run).
- **Pages scanned in strips or tiles are OCR'd** (`pdf_scan.page_images`): a text-less page with no single image covering a quarter of it, but whose image tiles (each at least 2% of the page) together do, is OCR'd tile by tile, top to bottom.
- **Record pages** (`nexus.processing.record_pages`): `servicenow_task_page`, `servicenow_generic_page`, `servicenow_article_page`, `jira_issue_page`, `file_page_header` / `file_page` and `field_text` render already-fetched ServiceNow rows, Jira issues with comments and bucket/drive files as the Markdown page that is chunked (moved from Nexora; same output).
- Opt-in `address` PII detector (`detect_pii_spans(text, entities=["address"])`, mask `[ADDRESS]`): house number, 1-4 capitalised words and a street type (`Street`, `Rd`, `Marg`, `Nagar`, ...) with an optional unit. Not a default detector.
- `prepare_chunks(..., count_many=)`, `fit_text(..., known=, count_many=)` and `ChunkLimiter.fit(text, known)`: batched token counting and already-known counts (see **Changed**). `SemanticEmbedder.additive_counts` is True for BERT-style tokenizers, whose counts add up across whitespace.
- **Token-bounded chunks.** Every `process_*` method caps each chunk at the embedder's window (450 tokens for `bge-small-en-v1.5`, counted with the model's own tokenizer; a conservative estimate when no local tokenizer is available). A chunk over the cap becomes consecutive parts with its context header (`Section: A > B`, `Columns: ...`, `[Workbook: f | Sheet: s | Row n]`, `[Table: t | PK: 1]`, ...) repeated on every part and `metadata.part` / `parts` / `parent_chunk_id`; nothing is dropped. `NexusClient(chunk_max_tokens=...)` or `NEXUS_CHUNK_MAX_TOKENS` lowers the cap, `0` turns it off. New `NexusClient.count_tokens()`, `fit_chunk_text()` and `chunk_limiter`; `nexus.processing.token_budget.fit_text()`.
- `embedding_info()` returns `max_tokens` (largest chunk the model embeds whole) and `window` (the model's input limit).
- **Row records for every tabular source.** `process_mysql_table` and `process_mongo_collection` attach the masked row as `metadata.record` (`records` for `rows_per_chunk > 1`); `process_spreadsheet` attaches a typed, masked `record` per row plus `metadata.sheet` (and a `sheet` field in the record when the workbook has several data sheets); CSV through `process_document` is read with `csv.DictReader` (delimiter sniffed among `, ; | tab`, title lines skipped) into row-group chunks carrying `metadata.records` and `row_range`. Numeric CSV columns become numbers (`1,234.50` -> `1234.5`); identifier-like columns (leading zeros, `id`, `zip`, `phone`, ...) keep their text.
- **Column-aware PII masking for records**: `GuardrailsEngine.classify_columns()`, `mask_record()`, `mask_records()` (`nexus.guardrails.pii_columns`). Each column is classified once from its name and values (email, phone, SSN / national id, card, secret, identifier, timestamp, numeric, boolean, text); PII columns are masked whole, identifier / timestamp / numeric columns are never masked, free text gets the text detectors. Optional `token_secret` gives deterministic `[EMAIL:3f9a1c2b7d]` tokens so grouping and equality still work.
- **Compressed audio**: MP3, M4A/AAC, OGG/Opus and FLAC are decoded with PyAV (extra `[video]`) to 16 kHz mono with the real duration; `process_document` routes `.m4a`, `.aac`, `.ogg`, `.oga`, `.opus` and `.flac` (and sniffs `OggS`, `fLaC` and M4A `ftyp`) to `process_audio`.
- **Standard-library PDF reader** (`nexus.processing.pdf_reader`, `pdf_lexer`, `pdf_filters`, `pdf_fonts`, `pdf_content`, `pdf_layout`, `pdf_extract`): cross-reference tables and streams with `/Prev` chains and hybrid files, object streams (`/ObjStm`), xref rebuild by scanning when the table is missing or broken, Flate (PNG/TIFF predictors), LZW, ASCII85, ASCIIHex and RunLength filters, the page tree in document order with inherited resources, `/ToUnicode` CMaps (`bfchar`, `bfrange`, code space ranges), Type0/CID fonts with `/W` widths, simple fonts with WinAnsi/MacRoman/Standard encodings and `/Differences` glyph names, and a content-stream interpreter (`cm`, `q`/`Q`, `Tm`/`Td`/`TD`/`T*`, `Tc`/`Tw`/`Tz`/`TL`/`Ts`, `Tj`/`TJ` with kerning gaps as spaces, Form XObjects). `extract_pdf_pages(data, page_texts=None, ocr_provider=None)` returns cleaned page text with a `source` per page. On the five test PDFs it matches pypdf (word recall 0.95–0.99 against pypdf, same page counts) and reads the 25 MB handbook in 2.3 s (the regex scanner ran for more than 5 minutes).
- **Scanned pages are OCR'd** (`nexus.processing.pdf_scan`): a page with no text layer is OCR'd from its page image — JPEG and JPEG 2000 as is, Flate/raw gray, RGB, CMYK and 1-bit samples wrapped as PNG, CCITT G3/G4 wrapped as TIFF (standard library only) — with the `[ocr]` extra. Pages are marked `text_source` `ocr` (with `ocr_confidence`), `needs_ocr` (no OCR engine) or `ocr_unsupported` (JBIG2).
- **PDF layout clean-up**: running headers, footers and page numbers that repeat in the top/bottom band of most pages are removed (`Page 3 of 10`-style lines are recognised by a number that follows the page number); headings are found from font sizes and rendered as `#` Markdown; each page carries the heading path in force where it starts (`metadata.heading_path` and a `Section:` line in the chunk); words hyphenated across lines are re-joined.
- `NexusClient.process_pdf(..., page_texts=...)`: page texts from another engine (a list or a function of the PDF bytes); Nexus still OCRs scans, reads pages the other engine left empty with its own reader, removes running lines, masks and bounds chunks.
- **`NexusClient.process_file(document_id, name, payload, file_type=None, *, metadata, enable_guardrails, shallow_mode, pdf_page_texts)`**: one entry point that dispatches by extension and content (Slack exports, Word, Excel incl. `.xls`, PowerPoint, PDF, audio, video, images with magic-byte format sniffing, SQLite, code, e-mail, chat, OpenAPI, text); raises `UnsupportedFormat` for a non-Slack `.zip`.
- `NexusClient.extract_text(name, data, *, file_type, strict, pdf_page_texts) -> ExtractedText(text, format, units, readable, encoding)`: readable text of a file without chunking (`[Page n]`, `[Slide n]`, `[Sheet Rn]` units); `strict` refuses binary noise.
- **`nexus.processing.text_decode`**: `decode_text(bytes) -> DecodedText(text, encoding, confidence, bom, replaced)` (BOM, UTF-16 without BOM by NUL pattern, strict UTF-8, cp1252, latin-1) and `looks_binary(bytes)`.
- **Storage-ready chunks** (`nexus.processing.chunk_store`): `prepare_chunks(chunks, *, max_tokens, count_tokens, title, drop_keys, ...)` drops empty chunks and caller-owned metadata keys, splits chunks over the token budget into header-led parts (record on the first part only, `part`/`parts`, `record_key` kept), packs runs of tiny row chunks into token-bounded groups with `records`, `packed_rows` and `row_range`, and reserves room for a long title; `document_digest(name, file_type, chunks)` (summary text from every processor's structure keys); `title_passages(texts, titles, count_tokens, window)`. Client methods `NexusClient.prepare_chunks()`, `document_digest()` and `embed_passages(texts, titles=None)` (the title is shortened to fit the window, never the passage).
- **JSON documents as tables** (`nexus.processing.json_table`): `json_table(text)` finds the largest array of objects at any depth, flattens records to dotted keys and keeps the other fields as `key.path: value` lines; `process_document` on `.json` now produces row-group chunks with column-masked `metadata.records` (like CSV) and a context chunk; `compact_json`, `flatten_json`, `find_record_array`.
- **Markup to Markdown**: `html_to_markdown(html, dialect="html" | "confluence")` (`nexus.processing.markup_html`; headings, pipe tables, nested lists, code, links, images; scripts, styles, navigation, footers and asides dropped; Confluence macros, task lists, panels, page/attachment links and CDATA bodies) and `adf_to_markdown(doc)` for Atlassian Document Format (`nexus.processing.markup_adf`).
- **Notion** (`nexus.processing.notion`): `notion_rich_text`, `notion_property_value`, `notion_page_title` and `notion_blocks_to_markdown(block_id, list_children, ...)`, which renders a block tree through a caller-supplied children callback (the caller keeps the API client).
- **Warehouse values and records** (`nexus.table_records`): `coerce_value(dialect, column, raw)` and `rows_from_columns(dialect, columns, data)` for BigQuery, Snowflake and Databricks wire formats; `flatten_record(record, sep, skip, max_value_chars)` (Salesforce-style nested records); `rows_to_markdown(name, rows, kind)`.
- **Passages and outlines**: `join_adjacent(prev, next)` / `stitch(texts)` re-join consecutive chunks without their repeated headers (`Section:`, `Columns:`, `[...]`, Markdown table headers) and overlap (`nexus.processing.passages`); `plan_sections(chunks, ...)`, `section_text(run)` and `build_outline(name, chunks, complete, ...)` map/reduce a large document into section notes and a summary with an injected completion function (`nexus.processing.outline`).
- **CDC**: `ChangeEvent.source_position` (`lsn:`, `binlog:file:pos`, `clustertime:t:i`) and `tx_id` from Debezium, Maxwell and MongoDB events; `is_newer(event, than)` for ordered, idempotent apply; `apply_change(previous, event)` (partial-update merge, removed fields, deletes); `mysql_row_event(...)`, `mongo_change_event(change)` and `driver_jsonable(value)`. `NexusClient.process_change_events(events, *, state, column_kinds)` merges, masks by column with stable kinds and renders each record's chunk from the masked record.
- **PII**: `detect_pii_spans(text, config, entities) -> [PiiSpan(start, end, entity)]` on the original text (detection on an NFKC shadow with an offset map, so full-width digits and zero-width separators cannot hide a value) and `mask_spans(text, spans, placeholder)`; `GuardrailsEngine.register_detector(entity, fn)` merges caller detectors (for example an NER model) into `mask_pii` and `detect_pii_spans`; `merge_column_kinds(known, rows)` / `GuardrailsEngine.merge_column_kinds()` keep column kinds stable across CDC batches.
- `detect_injection(text)` / `GuardrailsEngine.detect_injection()` (`nexus.guardrails.prompt_security.INJECTION_RULES`): five named indirect-prompt-injection rules, checked on the text as written and normalised.
- **Retrieval**: `reciprocal_rank_fusion(ranked_lists, key, k=60)`, `RankingConfig.fusion="rrf"` for scale-free hybrid fusion, `LexicalIndex(scoring="bm25")` (Okapi BM25, k1 1.2, b 0.75), `rerank_multi(queries, passages, score, found_by)` and `NexusClient.rerank_multi()` / `reranker_info()` (re-ranker cost profiles).
- **Language and parse quality**: `detect_language(text)` / `detect_script(text)` (script histogram plus stopword profiles; ISO 639-1 codes) and `assess_text(texts)`; every `process_*` result has `quality` (`chars_indexed`, `alnum_ratio`, `replacement_char_ratio`, `empty_chunks`, `language`, flags `no_text`, `garbled_text`, `replacement_chars`, `mostly_empty`).
- `EasyOCRProvider.read_lines(image)` returns OCR lines in reading order with confidence (`order_ocr_boxes`).
- Separate query-time inference: `SemanticEmbedder` keeps a query-only model instance (`NEXUS_QUERY_MODEL=shared` turns it off), so `embed_query` no longer waits for a running `embed_batch`. Measured on an 8-core Mac while 1,500 passages were embedded: `embed_query` p95 13.8 ms (was 96 s, the whole batch). `NEXUS_ONNX_THREADS` sets ONNX intra-op threads.
- `NEXUS_ML_THREADS` caps the CPU threads of EasyOCR (torch) and faster-whisper (CTranslate2); opt-in, defaults unchanged.
- **Legacy encodings are detected** (`nexus.processing.charset_detect`, used by `decode_text`): Central European, Cyrillic, Greek, Turkish, Arabic, Hebrew, Baltic, KOI8-R, Shift-JIS, EUC-JP, GB18030, Big5 and EUC-KR. Windows-1252 stays the default for Western text (all 984 single-character cp1252 contexts still decode as cp1252); a mostly-UTF-8 file with a few broken bytes stays UTF-8 with only those bytes replaced.
- Language ID: Ukrainian, Bulgarian, Serbian, Macedonian, Belarusian, Kazakh, Marathi, Persian, Urdu and kanji-only Japanese, plus Polish, Czech, Romanian, Danish, Norwegian, Finnish, Hungarian and Vietnamese profiles.
- `SheetData.context`: XLSX title rows above the header (also emitted as a title chunk).
- Polyglot code: methods inside TS/JS/Java/C#/Rust classes become `Class.method` symbols and chunks (the class chunk is unchanged and lists them).
- DOCX headings are also recognised from localised style names (`styles.xml`) and outline levels.
- Opt-in PII detectors `aadhaar` (Verhoeff checksum), `pan` and `iban` (mod-97 and country length); none is a default detector. Phone masks absorb a leading `+` or `(` (`+[PHONE]` is now `[PHONE]`); national formats (Indian, German, UK, French) are masked after a phone cue or a leading `+`.
- `LocalVectorStore.remove(id)` and `LexicalIndex.remove(id)`.
- `NexusClient.process_change_events(..., positions=)`: key -> last applied log position, updated in place, so redelivered events are skipped across batches.
- `NEXUS_ONNX_THREADS` / `NEXUS_ONNX_QUERY_THREADS` (ONNX threads for passage/re-rank and query models) and opt-in `NEXUS_TOKENIZER_THREADS`.
- `iter_jsonl` (streaming JSONL reader) in `nexus_observability.io` and `nexus_security.io`.

#### Changed
- **Token budgeting counts each text once** (output identical, checked against 3.2.0-pre on 4 corpora x 5 counters): `estimate_tokens` counts with one regular expression in C (same values; 1.7x faster); `prepare_chunks` counts only chunks longer than the budget in characters, in one batch (`NexusClient.prepare_chunks` passes the tokenizer's batch call), and reuses the counts for row packing; `fit_text` and its splitter take the count the caller already has, count each level's parts in one batch and skip the re-check of joined pieces when the counter is additive (`estimate_tokens`; the bge tokenizer, fuzz-checked). Nexora's offline RAG eval (M) table ingest, wall p50 of 5: `public.cases` 3.02 s -> 1.40 s, `public.accounts` 0.41 s -> 0.25 s, `public.orders` 1.51 s -> 1.42 s (3.1.1: 0.41 / 0.10 / 0.66 s; the rest is token-accurate splitting and packing that 3.1.1 did by characters). With the bge tokenizer, `prepare_chunks` on 600 rows of ~3.4k characters: 6.5 s -> 2.2 s wall (batched, tokenizer threads) or 3.5 s CPU with `TOKENIZERS_PARALLELISM=false`.
- The OCR engine is loaded on the first page that needs OCR, not for every PDF: a born-digital PDF no longer imports the deep-learning runtime (about 2.4 s and 165 MB per worker process with EasyOCR installed). Output is identical.
- **Audio with a transcript is chunked by transcript segments** (whole segments, at most ~60 s or ~180 words per chunk), and the acoustic numbers (RMS, ZCR, centroid, bands) are no longer in the chunk text (they stay in metadata). Audio without a transcript is still framed into fixed windows. An untimed `transcript=` is split by sentences instead of being repeated on every window.
- `embed_batch` sorts passages by length and takes the model lock per mini-batch; the re-ranker locks per mini-batch of 32 pairs, so concurrent questions interleave.
- PII text detectors are context-aware: a bare digit run is a phone number only after a cue (`phone`, `call`, `mobile`, `tel`, `whatsapp`, ...) and a card only when it is Luhn-valid with a card prefix or a card cue; formatted numbers (`415-555-0100`, `(415) 555-0100`, `+91 98765 43210`, `4111 1111 1111 1111`) are masked as before. Numbers glued to a longer token (`ORD-555-123-4567`, `1234567890.50`) or following an identifier / timestamp key (`order_id:`, `created_at:`, `account_no:`) are no longer masked. Database, Mongo and spreadsheet rows are masked by column, and their chunk text is built from the masked row so text and record agree.
- Spreadsheet values are typed: date-formatted cells (built-in and custom `numFmt`s, 1900 and 1904 date systems) become ISO dates (`2024-03-01`, `2024-03-01T12:00:00`, `09:30:00`) instead of serial numbers, in XLSX and in legacy XLS through xlrd. `metadata.data` is now the masked row (it was unmasked).
- MongoDB arrays of sub-documents keep every element (previously the first 10, with a `_truncated` key).
- **Free-text phone numbers are masked again** (open item O1): a bare digit run is also a phone number after personal cues (`my number is`, `his no.`, `text me at`, `ping`, `message`) or when it has the shape of a dialable number (NANP `[2-9]XX[2-9]XXXXXX`, Indian mobile `[6-9]XXXXXXXXX`) and no identifier, amount (`amount`, `total`, `price`, `$`, ...) or date cue precedes it. Identifier and amount columns are unaffected (records are masked by column).
- **Masking is never weaker in these cases:** a phone or card number right after a cue and a `#` (`cc#4111...`, `tel#555...`) is masked; a comma-separated list of phone numbers is masked in full (only a 1-3 digit group after a comma counts as a decimal or thousands part); id, time and number columns still mask secrets (JWT, API keys) and e-mail addresses inside their values; a `contact` / `emergency` column of bare dialable numbers is a phone column.
- `detect_pii_spans(..., strict=True)` turns the context rules off (every phone-shaped and Luhn-valid card-shaped number is a span), for output policies and compliance redaction where over-redaction is acceptable and a miss is not.
- **`mask_pii` keeps the text as written**: detection runs on a normalised shadow, but only the masked values change; superscripts, ligatures and the zero-width joiners Indic scripts and emoji need are kept (previously the whole text was NFKC-normalised and every format character removed). Bidi controls and zero-width spaces are still removed. `process_document` stores NFC text (was NFKC: `x²` became `x2`).
- `process_document` given bytes decodes them with `decode_text` (it stored the Python `repr`, `"b'...'"`); the encoding is in the first trace stage's details.
- PDF chunks: pages without text produce no chunk (counted in `metadata.empty_pages`); chunk indexes are consecutive; chunk metadata adds `text_source`, `heading_path` and `ocr_confidence`. `NexusClient.process_pdf` moved to `nexus/client_pdf.py` (same signature plus `page_texts`); the new client methods live in `nexus/client_ingest.py` and `nexus/client_store.py`, so `client.py` is 220 lines shorter. The old regular-expression PDF scanner moved to `nexus_processing/pdf_legacy.py`; `nexus_processing.pdf` re-exports its helpers.
- `chunk_markdown` splits a pipe table that does not fit only between rows and repeats its header and separator rows on every piece; `token_budget.split_header` treats a Markdown table header (alone or after a `Section:` line) as a header, so token-split parts of a table repeat it too.
- `chunk_json` serialises compactly (`indent=2` spent about 40% of a chunk's characters on spaces).
- PowerPoint tables are Markdown pipe tables with a header row (were `a | b` lines). Word sections carry the full heading path (`Guide > Install`; was the last heading only), and paragraphs inside block-level content controls (`w:sdt`) are read.
- Lexical tokens cover every script: accented Latin words match their unaccented spelling, Devanagari/Arabic/Cyrillic words are tokens (marks included), and Chinese/Japanese/Korean runs become character bigrams; ASCII tokens are unchanged.
- `EasyOCRProvider.extract_text` orders lines top to bottom and drops boxes under 0.3 confidence.
- The `RetrievalEngine` docstring no longer claims RRF for the default weighted fusion.
- **XLSX is streamed** (`iterparse`, each row cleared): 50k rows 2.5 s / 219 MB -> 1.0 s / 40 MB; 200k rows 878 MB -> 160 MB peak. Repeated headers are numbered (`Amount_2`); only columns that hold data get a header.
- CSV is parsed in one `csv.reader` pass (about 28% less CPU, rows identical); integers without a decimal point are parsed exactly.
- PDF text showing is table-driven (per-font decode tables, C-level advance sums): about 26-30% less CPU with bit-identical text positions. Form XObjects are decoded once per document.
- Slack exports render each message once (3x faster); Mongo documents are cleaned once (7x faster on deep documents); PNG Up prediction, CMYK and image-mask conversion are vectorised (identical bytes).
- JSON: a second record array in a document becomes one readable context line per record instead of one multi-MB JSON line; `flatten_json` is iterative.
- `EasyOCRProvider` resolves the torch device when the model loads; video OCR is detected only when a demuxer exists; images under 32 x 10 px are not OCR'd; identical embedded images are OCR'd once per file.
- Language ID returns `und` when under 5% of the words are stopwords.
- **Vector search** normalises once on insert and scores by dot product with a heap top-k (32k entries: 2.2 s -> 65 ms per query; same top-k); re-adding an id replaces its vector; `load()` de-duplicates.
- **Keyword search** touches only the query's postings with a heap top-k (80k documents: 97.5 -> 13.3 ms per query, same order); saved indexes store document lengths, so `load()` no longer re-tokenises (old index files still load).
- ONNX threads: the passage model and re-ranker default to `NEXUS_ONNX_THREADS` or half the CPUs, the query model to `NEXUS_ONNX_QUERY_THREADS` or 2 (embeddings identical; process CPU while querying during ingest 7.5 -> 5.9 cores).
- **PII detection is linear and faster**: e-mail scan anchored on `@`; Unicode shadow built with one `str.translate`; ASCII and literal prefilters; ASCII fast path in `normalize_text`; table masking memoised per call (`mask_records` 20k rows 1.41 -> 0.62 s). Output is identical except the phone and placeholder changes listed here.
- `detect_pii` uses the same spans as masking; `GuardrailsEngine.evaluate()` detects once and masks from those spans.
- **`NexusClient.process_document` masks free text once, before chunking**, so a value cut at a chunk boundary or repeated in an overlap can no longer escape detection. Chunk boundaries can shift slightly (a mask is shorter than its value). CSV cells are masked once (CSV 10k rows: 2.2 -> 1.4 s wall, 6.0 -> 2.8 s CPU; output identical). Packed row groups are not re-tokenised by the chunk limiter.
- **`process_change_events` emits one chunk per key** (its final state, or one delete) and skips events that are not newer than the last applied one; Kafka tombstones (`None`) are ignored. A batch that inserts and deletes a key now reports one delete instead of an upsert and a delete (1,000 events: 1,000 -> 731 chunks, final state always correct).
- `validate_records` keeps the newest record per key (was the first); event times are timezone-aware (epoch values are UTC, not local time); `FileDropConnector.read` honours the checkpoint.
- Encryption keys (HKDF + Fernet) are cached per key (token format unchanged); `evaluate_existing_alerts` only writes alerts not already recorded.
- Placeholders (`N/A`, `none`, `-`, ...) stay visible in PII columns; secrets are always masked.
- Code-page detection scores each distinct word once, language ID looks each word up once in a stopword index, and the national phone scan is skipped when no ten-digit run exists (all three with identical results, checked by equivalence tests).

#### Fixed
- PowerPoint: text placed directly on a slide, outside any shape, was dropped; it is kept as the slide's text.
- **MP3 transcripts lost ~95% of their words**: the duration was estimated from the compressed bytes (a 72.5 s file measured 1.03 s), so only the transcript of the first second survived. All 146 of 146 words are now kept on the test recording.
- Silent truncations removed: Slack threads over 4,500 characters (now split into parts with the thread header), video scene dialogue cut at 140 characters, Python class bodies and script-only modules cut at 2,000 characters, unparseable snippets at 500. Module-level code between functions (imports, constants, `__main__` blocks) and class attributes, previously dropped, are now chunked for Python and the other languages.
- An XLSX with embedded images failed with a `TypeError` while building the image-text chunk.
- New coverage contract test: for every processor the stored chunks keep at least 90% of the extracted words, and no chunk exceeds the token cap.
- **PDFs from modern producers** (xref streams, object streams, CID fonts) came out as binary noise or empty pages, and large files ran for minutes in the regular-expression scanner. The scanner is kept only as the fallback for bytes the new reader cannot open.
- `chunk_smart_text` was quadratic (re-slicing the remaining text after every chunk): 8 MB took 4.4 s; it is now linear with identical output (~0.2 s).
- A Markdown table split across chunks kept its header only in the first chunk (80-row probe: `[True, False, False, False, False]`); every piece now has it.
- `{"data": [200 records]}` JSON became one chunk with no records; counts and totals over JSON exports are now computed from records.
- The package's Documentation link and the README point to nexus.veloxs.ai/documentation.html and the guide; the /docs/ address used in 3.1.1 is not served.
- CSV: a title line containing the delimiter became the header; integers above 2^53 lost precision; a blank line inside a quoted cell was dropped.
- HTML without explicit end tags (`li`, `td`, `tr`, `p`, ...) lost tables and lists; unclosed `<p>` and deep nesting raised `RecursionError`.
- DOCX: tabs, line breaks and multi-paragraph table cells glued words together; `|` inside cells broke tables; merged cells shifted columns; header and footer runs got false spaces.
- XLSX: duplicate headers overwrote values; a title row became the header; a stray far cell created 16k columns; phonetic guides were mixed into the text.
- Polyglot code patterns backtracked quadratically on long whitespace runs (ReDoS); extensionless JavaScript with `import` lines was parsed as Python.
- PDF: hyphenated compounds that the document writes elsewhere keep their hyphen when broken at a line end (`user-level`, not `userlevel`).
- Atlassian (ADF) documents nested thousands of levels deep no longer lose their text.
- UTF-8 files with a few broken bytes were decoded as cp1252.
- Keyword index: re-adding a document left its old postings behind.
- Hybrid RRF was made worse by an all-zero graph ranking, and graph scoring matched stopwords, substrings and the node type label (RRF MRR@10 0.553 -> 0.739 on the bench).
- Nested dicts and lists in id, time or number columns were never masked; raw e-mail addresses were kept in `metadata.emails`; `N/A` placeholders were masked as `[PHONE]`.
- Quadratic e-mail and `fake_system_turn` regular expressions (hyphen chains and blank-line runs are now linear).
- `run_cdc` mutated its input; a mixed naive/aware checkpoint raised `TypeError`.
- The re-ranker's sigmoid overflowed on large scores; loading one embedding model no longer blocks loading another.

## [3.1.1] — 2026-09-28

Fixes found while writing the documentation at [nexus.veloxs.ai/docs](https://nexus.veloxs.ai/docs/). No public API is renamed or removed; three defaults behave differently, as described under **Changed**.

### Added
- `RagConfig.min_semantic_score` (default `None`, off): when set, retrieval-engine results whose semantic similarity to the question is below it are not used as context, so a question the indexed documents cannot answer is `blocked` instead of answered from loosely related chunks.
- `inspect_prompt(..., include_leakage=True)`: pass `False` to check blocked patterns only.

### Changed
- **Keyword search scoring** (`LexicalIndex.search`, and therefore `lexical_score` and the blended `score` of `NexusClient.search()`): a document's score is now the IDF-weighted share of the query's meaningful words it contains (0–1). Stopwords (`the`, `of`, `is`, …) no longer count, rare words count more than common ones, and query words found in no document lower the score. Previously the best keyword match always scored 1.0, even when it shared only a word like "the". Scores and, sometimes, the order of results change; the index file format is unchanged.
- **Answer re-screening**: the composed answer is still checked for blocked patterns (instructions injected through retrieved documents), but no longer for leakage terms. Documents may legitimately mention "password" or "token"; previously any answer citing such a document was blocked. Questions are still checked for leakage terms exactly as before.
- **Off-topic gate**: an enabled gate with an empty `allowed_keywords` list no longer blocks every question; with no keywords there is no topic restriction. With keywords configured, behaviour is unchanged.

### Fixed
- ServiceNow incidents created by `ServiceNowProvider` showed "Nexora Operations" as the correlation display; it is now "Nexus". Duplicate detection (by `correlation_id`) is unaffected.
- Documentation: README examples now pass the required IDs to `process_*`, use `scene_interval_seconds` for video and no longer pass a non-existent `collection` argument to `search()`; `PROCESSING_REFERENCE.md` shows the real chunk record and inserts into the columns `pgvector_ddl()` creates; `ARCHITECTURE_OVERVIEW.md` and `USING_NEXUS.md` point to the Kafka and PostgreSQL CDC sources added in 3.0.1–3.1.0 and describe the semantic embeddings; `SECURITY.md` lists 3.1.x as the supported line.
- The package's Documentation URL points to nexus.veloxs.ai/docs.

## [3.1.0] — 2026-09-28

### Added
- **Operations building blocks** (`nexus.operations`, pure Python, no new dependencies) for governed, continuous decisions: a safe expression language for business rules (allow-listed syntax, no code execution, missing fields never raise), versioned decision tables (`first` / `priority` / `collect` / `unique` hit policies, computed outputs, evaluation traces), strategies (derived facts plus an ordered chain of tables with reason codes), a contact policy engine (contact hours by recipient timezone, frequency caps, consent, do-not-disturb, conversation cooling-off; `IN_RBI` and `US_REG_F` presets), case state machines, permanent idempotency keys and deterministic test/control assignment.
- **Points scorecards** (`nexus.operations.scorecard`) — characteristics with expression bins, base points / base odds / PDO scaling to a probability, bands, adverse-action style reason codes; usable as strategy steps.
- **Case planner** (`nexus.operations.engine`) — `plan_case` turns facts into a decision, next state, actions with permanent idempotency keys (subject, cycle, stage), contact-rule timing, channel fallback on missing consent or do-not-disturb, opt-outs, pauses (promises, approvals) and a holdout arm that is evaluated but never contacted; `OperationsEngine` runs the full loop in memory.
- **Reply intents** (`nexus.operations.intents`) — offline multilingual classifier (English, Hinglish, Hindi, Marathi) with confidence, secondary signals (stop contact, call back), entities (promise date, UTR/RRN, amount, months of relief requested), a review threshold, `redact()` and an optional LLM fallback that receives only redacted text and whose confidence is capped.
- **Messaging** (`nexus.operations.messaging`) — placeholder-only templates, recipient masking, and providers sharing one `send()` interface: dry run, HMAC-SHA256 signed webhook with idempotency key, SMTP (STARTTLS/TLS), WhatsApp Cloud API templates, Twilio; retryable vs permanent failures.
- **Experiments** (`nexus.operations.experiments`) — Wilson score intervals, two-proportion z-test, lift with confidence interval and minimum-sample guard, per-arm summaries against a control.
- **Learned reply model** (`IntentModel`, `evaluate_model`) — multinomial naive Bayes over word and character 3–4-gram features (robust to Hinglish spelling), trained on reviewers' labels, serialized as plain counts, k-fold evaluation; `IntentClassifier(model=...)` consults it only when the rules are unsure and above its own confidence threshold, before the optional LLM.
- **Condition monitoring** (`nexus.operations.signals`) — `AssetMonitor` keeps a small serializable state per asset (recent readings, a down-sampled day of history, time-aware fast/slow EWMAs) and turns readings into an `Assessment`: engineering limits, robust z against the median/MAD baseline, drift, rate of change, a statistically significant slope with the time to the alarm limit, data quality (implausible values, flatlined sensors, silence), judged on the median of the last three readings so a single glitch never alarms; per-signal scores fused with a noisy-OR into `anomaly_score` and `failure_risk`, with reason codes. `diagnose` maps the symptom pattern to a likely failure mode (sensor fault, bearing wear, cavitation, electrical overload, overheating, leak or blockage) with confidence, evidence and recommended checks. `window_stats` for tumbling-window aggregates.
- **Work orders** (`nexus.operations.workorders`) — one `WorkItem` to a ServiceNow incident (Table API, idempotency key in `correlation_id`, looked up before creating), an IBM Maximo work order (`externalrefid`), a Microsoft Teams Adaptive Card or a dry run; https only, retryable vs permanent failures, `work_provider_from_config`; `status(ref)` reads a ticket back as `open` / `in_progress` / `resolved` / `closed` / `cancelled` (`TicketStatus`) for time-to-repair reporting.
- **Apache Kafka source** (`nexus.processing.kafka`, extra `[kafka]` = confluent-kafka) — `KafkaSource` for at-least-once pipelines: consumer groups, `read_committed`, no auto-commit, `commit(batch)` of the next offset per partition after the caller has applied the batch; SASL_SSL with SCRAM-SHA-512 by default, unencrypted protocols only with `allow_plaintext=True`; broker hostname verification and mutual TLS (client certificate and key); rebalance-safe commits (partitions are tracked through the assign / revoke / lost callbacks, only owned partitions are committed, and a commit during a rebalance returns `False` instead of failing); `check()` connection test and `lag()` per consumer group through a client that never joins the group; `decode()` to CDC `ChangeEvent`s (Debezium with the Kafka key, tombstones as deletes) or JSON documents, and `avro_decoder()` for Confluent Schema Registry Avro (extra `[kafka-avro]`).
- `plan_case`: action kind `work_order`; an action whose rule requires approval is planned with `needs_approval` and queued only after approval (`PlannedAction.ready`); the approval carries the action's idempotency key. `OperationsEngine` gains `work_providers` and `approve()`.
- `plan_case`: call and visit tasks respect opt-outs, like messages.
- Expression functions `today()`, `add_days(date, n)` and `str(value)`.

- **Outbound SSRF protection** (`nexus.operations.outbound`) for every provider call (webhook, WhatsApp Cloud, Twilio, SMTP, ServiceNow, Maximo, Teams): the host is resolved and every address checked — loopback, link-local / cloud metadata, unspecified, multicast and reserved ranges are refused, including IPv4 embedded in IPv6 (mapped, NAT64, 6to4); private ranges only with `NEXUS_OUTBOUND_ALLOW_PRIVATE=1` or for hosts in `NEXUS_OUTBOUND_ALLOWED_HOSTS`; the connection is pinned to the checked address (TLS still verified against the host name) and redirects are refused.
- TRAI DLT: `Message.dlt_entity_id` (principal entity id) next to the header and content template id, sent to gateways; `dlt_problems(message)` lists what an Indian SMS still lacks. SMTP connections are pinned to the checked address as well (`outbound.pinned_smtp`; TLS still verified against the host name).
- `KafkaSource.before_revoke` (flush and commit while partitions are still owned) and `assignment_version` (drop per-partition state after a rebalance); `AssetMonitor` state is serialized compactly (whole seconds, 4 decimals).

### Changed
- `plan_case`: an action whose rule sets `requires_approval` is no longer ready to send before the approval (`PlannedAction.needs_approval`; use `ready` instead of `sendable` when queueing).

## [3.0.1] — 2026-09-27

**Breaking for integrators of 3.0.0** — processing no longer produces vectors, and the legacy 3072D hashing projection with every API kept for it is removed. Embed chunk text at storage time with `embed_texts()` / `embed_query()`. See "Upgrading from 3.0.0" in the README. This release consolidates the unpublished 3.2.1–4.0.0 development versions.

### Added
- **Semantic embeddings** — `NexusClient.embed_texts()` (batched passages), `embed_query()` (asymmetric query encoding) and `embedding_info()`, backed by FastEmbed/ONNX (`BAAI/bge-small-en-v1.5`, 384D). Configure with `NEXUS_EMBEDDING_PROVIDER` (`fastembed` | `openai`), `NEXUS_EMBEDDING_MODEL`, `NEXUS_EMBEDDING_DIMENSIONS`, `NEXUS_MODEL_CACHE_DIR`. The OpenAI provider batches 256 inputs per request.
- **Cross-encoder re-ranking** — `NexusClient.rerank(query, passages)` returns (0, 1) relevance scores (`Xenova/ms-marco-MiniLM-L-6-v2`).
- **CDC / webhook normalization** (`nexus.processing.cdc`) — `normalize_change_event(s)` auto-detects Debezium (envelope + Kafka key), Maxwell, MongoDB change streams (partial updates flagged for merge) and generic webhooks; single events, lists, `{"events": [...]}` or NDJSON (max 1,000 per batch). `change_event_text` renders one record chunk.
- **PostgreSQL change data capture** (`nexus.processing.pgoutput`) — a pure-Python decoder for PostgreSQL's built-in `pgoutput` logical replication protocol (no wal2json or other server extension) producing the same `ChangeEvent` objects as the other CDC formats, keyed by replica-identity columns, with type-aware value conversion (`numeric` as exact `Decimal`), unchanged-TOAST handling (`partial` events) and primary-key changes as delete + insert; plus `PostgresLogicalStream` (psycopg2): prerequisite checks with actionable fixes (wal_level, REPLICATION role, publication, replica identity), an exact initial copy through an exported snapshot consistent with the slot's start position, publication column lists and row filters honoured in that copy (PostgreSQL 15+ data minimization), slot inspection (lag, `wal_status`, invalidation, conflicts) and drop, `IDENTIFY_SYSTEM` for detecting a restored or different cluster, deterministic session settings (ISO dates, UTC), at-least-once delivery where nothing is confirmed until the caller has durably applied it, and idle-time confirmation so quiet databases do not retain WAL.
- **Webhook signing** — `sign_webhook_payload` / `verify_webhook_signature`: HMAC-SHA256 with optional timestamp binding (5-minute replay window), constant-time comparison.
- **Slack** — `NexusClient.process_slack_export()` parses workspace export `.zip` files or one channel's `.json` (threads grouped with replies, top-level messages windowed per channel/day, mentions resolved, join/leave noise dropped, PII masked). For live workspaces: `verify_slack_signature` (Events API v0 signing), `slack_event_message` (new / edited / deleted message mapping) and the public `messages_to_chunks`, shared by export and live paths.
- **Pluggable ML extraction** — optional OCR (EasyOCR, `[ocr]`), transcription (faster-whisper, `[audio-ml]`) and video demuxing (PyAV, `[video]`); embedded images in PPTX, DOCX, XLSX, PDF and email are OCR'd through one `process_image_binary()` path.
- **`release_idle_models(max_idle_seconds)`** — unloads shared OCR / Whisper models that have been idle, so long-running services only hold that memory while processing media.
- **Chunking** — heading-aware Markdown chunks with a `Section: A > B` breadcrumb; CSV row packing (~1.5k-char chunks with a repeated header); section-sized Word chunks (`group_word_sections`).
- Layer package versions and `configs/nexus.json` aligned to 3.0.1.
- DDL builders `pgvector_ddl(dim)` (HNSW + generated `tsvector` with GIN), `mysql_ddl(dim)`, `mongo_atlas_vector_index(dim)`; `get_pgvector_column_type(dim)` returns `halfvec` above 2000 dimensions.

### Changed
- `fastembed` is a core dependency (`NEXUS_EMBEDDING_PROVIDER=auto` is accepted as an alias for it); the retrieval engine, indexer and hybrid search use the semantic embedder.
- Processing stages end with "… Chunk Assembly" (no vector projection).
- OCR and Whisper models are loaded lazily, shared process-wide, run on CUDA or Apple MPS when available (`NEXUS_ML_DEVICE`), and oversized images are downscaled to 2560 px before OCR.
- Ingestion PII masking also covers API keys (OpenAI/AWS/Google/GitHub/Slack/Stripe), JWTs and international phone numbers; detectors apply in a fixed specific-to-generic order.
- Format fidelity: PDF image XObjects, ASCII85/ASCIIHex filters and `/Info` metadata; 32-bit float WAV; full JPEG SOF range; Word headers/footers/footnotes; PPTX SmartArt; nested RFC822 emails and iCalendar invites; MongoDB extended JSON types; MySQL composite primary keys.

### Removed
- `NexusClient.embed()`, `chunk_embeddings=`, `ProcessedChunk.embedding`, `embed_image` / `embed_audio` / `embed_video_scene`.
- `HashingEmbedder`, `ImageEmbedder`, `AudioEmbedder`, `VideoEmbedder`, the `local_hashing` provider and all hashing / lexical fallbacks; the `semantic` extra.
- `normalize_mysql_cdc_event`, `normalize_mongo_change_event` (use `normalize_change_event`).
- `project_code_vector`, `EMBEDDING_DIM`; DDL constants `PGVECTOR_DDL_SCHEMA`, `MYSQL_DDL_SCHEMA`, `MONGO_ATLAS_VECTOR_SEARCH_INDEX`.

### Fixed
- `process_document` raised `OSError: File name too long` for raw text payloads with long lines (the text was probed as a file path).
- SQL injection in SQLite table introspection; MP3 ID3v2 UTF-16 decoding; truncated MP4 crash; BMP unsigned dimensions; PPTX slide ordering; polyglot brace counting.
- Sliding-window overlap starts on a word boundary.

## [3.0.0] — 2026-08-27

### Changed

- **Nexus is now open source under the Apache License 2.0.** The project was
  previously distributed under the proprietary Nexus Software License.
  Copyright remains with Veloxs AI Inc.; see [LICENSE](LICENSE) and
  [NOTICE](NOTICE).
  - Per-file headers on all source files changed from
    `LicenseRef-Veloxs-AI-Proprietary` to `Apache-2.0`.
  - `license` metadata updated in the root and all seven layer
    `pyproject.toml` files.
  - `NOTICE` rewritten with an explicit trademark reservation. Apache-2.0
    §6 grants **no** rights in the Nexus or Veloxs AI marks.
- **Consistent product naming.** Nexus is now uniformly presented as the
  **Enterprise Intelligence Framework** everywhere a user encounters it: the
  README, all documentation, every layer README, the package summary on PyPI,
  the root and per-layer `pyproject.toml` descriptions, the `nexus --help`
  banner, the `import nexus` docstring, and `configs/nexus.json`. Each layer
  README now states which framework it belongs to and which capability it
  provides.
- **All references to other Veloxs AI products removed.** The repository now
  documents Nexus and nothing else, so readers are never left wondering which
  product a page describes. Trademark reservations are scoped to the Nexus and
  Veloxs AI marks; commercial-support pointers are product-neutral.
- **Documentation consolidated and renamed consistently.** The project
  described itself three different ways ("Enterprise AI Platform",
  "Enterprise AI Engine", "Enterprise Intelligence Framework") across five
  overlapping entry points at the repository root. It is now uniformly the
  **Enterprise Intelligence Framework**, the root holds only `README.md` and
  the governance files, and every guide lives under `docs/` and is indexed
  from the README:
  - `PROJECT_OVERVIEW.md` → `docs/ARCHITECTURE_OVERVIEW.md`
  - `USER_GUIDE.md` → `docs/INTEGRATION_GUIDE.md`
  - `documentation.md` → `docs/PROCESSING_REFERENCE.md`
- Repository documentation rewritten for a public, external audience:
  `README.md`, `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md` (now Contributor
  Covenant 2.1), `SECURITY.md`, `MAINTAINERS.md`, and the issue and pull
  request templates.
- Layer package versions aligned with the distributed package version
  (`2.4.0`); they had drifted at `0.1.0`.
- `configs/nexus.json` → `platform.version` corrected to `2.4.0`.
- Ruff configuration now pins an explicit rule selection so lint results are
  reproducible across ruff versions instead of drifting with the default
  rule set.

### Added

- [`SUPPORT.md`](SUPPORT.md) — where to ask questions, what to expect, and
  how the open-source project relates to commercial support.
- Developer Certificate of Origin (DCO) sign-off requirement for
  contributions. There is no CLA.
- CI now verifies that every tracked `.py` file carries the Apache-2.0 SPDX
  header, that no proprietary license markers remain, and that the
  distribution builds and passes `twine check`.
- `[project.scripts]` restored, so `pip install veloxs-nexus` once again
  provides the documented `nexus` command. It had been dropped, leaving the
  CLI reachable only via `python -m nexus.cli`.
- Root `dev` extra (`pytest`, `ruff`), so `pip install -e ".[dev]"` works
  from the repository root as the CI workflow and contributor docs assume.
- **Multimodal & Binary Document Ingestion Engine (Zero External Dependencies)**:
  - **Microsoft Word (.docx)**: Pure-Python OpenXML parser extracting heading hierarchy (`Heading1..6`), paragraphs, bullet lists, markdown tables, and document metadata.
  - **Spreadsheets (.xlsx) & Presentations (.pptx)**: Multi-sheet cell matrix traversal, shared strings resolution, slide text extraction, and speaker notes resolution.
  - **Audio Processing (.wav, .mp3, .aiff)**: Python 3.13-safe signal decoding, RMS loudness profiling, Zero-Crossing Rate (ZCR), Voice Activity Detection (VAD), and 7-band spectral decomposition (20Hz–20kHz) with temporal window citations (`[00:00 - 00:10]`).
  - **Video & Computer Vision (.mp4, .mov, .png, .jpeg, .bmp)**: Pure-Python ISO BMFF container parser, temporal scene chunking, motion variance, 8x8 luminance grid, and 64-bit dHash perceptual hashing.
  - **Code AST & API Specifications**: Python standard library AST parser (signatures, decorators, typed params, cyclomatic complexity), Polyglot regex scanners (`.ts`, `.js`, `.go`, `.rs`, `.java`, `.cpp`, `.cs`), and OpenAPI 3.0/3.1 / Swagger 2.0 route & schema extractors.
  - **Databases & Messaging**: Native binary SQLite parser (`.db`, `.sqlite`), MySQL CDC binlog event normalizer, MongoDB BSON deserializer and dot-notation flattener, and RFC 822 MIME email / threaded chat decoders.
- **Universal Auto-Routing in `NexusClient.process_document`**:
  - Automatically identifies file extensions and binary container headers (`.docx`, `.xlsx`, `.pptx`, `.pdf`, `.wav`, `.mp3`, `.mp4`, `.png`, `.db`, `.py`, etc.) and routes to native parsers.
  - Accepts both raw binary `bytes` and file path strings seamlessly.
- **Unified 3072D Vector Space**: All multimodal chunks project into IEEE 754 $L_2$ unit-normalized 3072D vectors ($\|V\|_2 = 1.0$), enabling unified cross-modal search and RAG across documents, spreadsheets, audio, video, code, and databases.
- **5-Stage Execution Telemetry**: Every document payload returns a granular 5-stage trace with timing and stage status.

### Fixed

- **Retrieval indexes were never written to or read from disk.** Both
  `build_indexes()` and `hybrid.search()` constructed their vector, lexical,
  and graph stores with the `in_memory_only=True` default introduced in the
  2.3.0 in-memory refactor, which makes `save()` and `load()` silent no-ops.
  The `build-index` CLI command reported a document count and exited
  successfully while writing nothing, and the subsequent `search` found
  nothing. Both call sites now opt out explicitly.
- Two `README.md` examples raised on execution: `mask_pii()` was shown
  without its required `config` argument, and `nexus.pipeline.batch` was
  documented as exporting `run_batch_job` rather than `run_batch`.
- The documented environment-variable table listed two variables that are not
  read anywhere in the codebase. It now lists the variables Nexus actually
  reads (`NEXUS_SECURITY_KEY`, `NEXUS_FPE_KEY`, `NEXUS_EXPERIENCE_CONFIG`) and
  the config fields that name the rest (`key_material_env`, `auth_env`,
  `api_key_env`).
- Four layer READMEs documented `.yaml` config paths and examples after the
  configs became JSON, leaving every documented command in them broken.
- `docs/USING_NEXUS.md` still declared Nexus proprietary and stated that it
  does not accept external contributions.
- Loop variables (`mod`, `name`) and the `sys` import leaked into the public
  `nexus` namespace and appeared in `dir(nexus)`; `LayerStatus` was exported
  but missing from `__all__`.
- A `lambda` in `mask_pii()` captured the `mask_value` loop variable by
  reference rather than binding it.

### Removed

- Internal engineering documents that are not appropriate for a public
  repository: `IMPROVEMENT_GUIDE.md`, `docs/evaluation/`, and `update.md`.
  These described internal implementation details unrelated to the Nexus
  framework.
- `build/` and `dist/` are no longer tracked in git. Build artifacts belong
  on PyPI and GitHub Releases.

### Security

- No credentials, keys, tokens, certificates, or customer data were found in
  the working tree or in any commit of the repository history. All sample
  data is synthetic.

---

## [2.4.0] — 2026-08-26

### Added

- **Five-stage execution trace** returned with every processed document:
  per-stage durations, itemized summaries, and status, exposed as
  `ProcessedDocumentPayload.execution_trace`.
- **`enable_guardrails` toggle** on `process_document()`, allowing callers to
  bypass PII redaction where verbatim fidelity matters (audit logs, code,
  account identifiers).

### Changed

- Improved floating-point precision in vector normalization; embeddings now
  normalize to exact L2 unit length (`1.0`) under IEEE 754.
- Text normalization hardened ahead of chunking.
- Line endings standardized across the source tree.

---

## [2.3.0] — 2026-08-24

### Added

- **Unified `NexusClient`** as the single in-process entry point, replacing
  subprocess round-trips with in-memory layer engines.
- **Clean nested namespace packaging**: `pip install veloxs-nexus` provides
  `import nexus` with `nexus.pipeline`, `nexus.processing`, `nexus.retrieval`,
  `nexus.guardrails`, `nexus.experience`, `nexus.security`, and
  `nexus.observability`.
- **3072-dimensional multi-gram vector projection** (unigrams 1.5×,
  bigrams 2.0×, trigrams 2.5×).
- **`nexus.database`** with a PostgreSQL + pgvector reference DDL schema and
  SQLAlchemy column types.
- Automated PyPI publishing via GitHub Actions using Trusted Publishing
  (OIDC), so no long-lived API token is stored in the repository.

### Changed

- In-memory stores are guarded by `threading.Lock` mutexes.
- `in_memory_only=True` skips disk I/O entirely for serverless and read-only
  runtimes.
- Tenant-bound cryptographic salting: `HKDF-SHA256("nexus-salt-" + tenant_id
  + "-" + key_id)`, so two tenants processing identical data produce
  cryptographically distinct ciphertext.
- Crypto utilities no longer perform implicit environment lookups; secrets are
  passed explicitly, with the environment as an opt-in fallback only.
- Hardcoded database paths decoupled from layer code.

### Removed

- The bundled test suites and demo data were removed from the distribution in
  this release. **They have been restored** — see `[Unreleased]`.

---

## [0.1.0] — 2026-06-02

Initial build of the Nexus platform by Veloxs AI Inc.

### Added

- Seven layers, each independently installable and replaceable:
  - `enterprise-data-pipeline` — REST, batch, streaming, CDC ingestion
  - `data-processing-enrichment` — ETL/ELT, chunking, metadata extraction
  - `embedding-retrieval-intelligence` — vector, lexical, hybrid, graph search
  - `orchestration-guardrails` — PII masking, prompt safety, policy, grounded RAG
  - `experience-api-engagement` — REST API, SDK, CLI, assistant channels
  - `security-governance` — RBAC, tenant isolation, AEAD encryption, audit log
  - `observability-monitoring` — metrics, logs, traces, AI events, alerts
- Root `nexus` package and CLI (`validate-platform`, `layers`,
  `prepare-demo`, `ask`).
- Integrator guide at [docs/USING_NEXUS.md](docs/USING_NEXUS.md).
- Deterministic, offline test suites across all eight projects.

### Security

- **Authenticated encryption**: Fernet (AES-128-CBC + HMAC-SHA256) with
  HKDF-SHA256 key derivation and `key_id` salt domain separation. Fails
  closed when the key environment variable is unset.
- **API-key authentication** with constant-time comparison
  (`hmac.compare_digest`) and `env:VAR_NAME` indirection for secrets.
  Spoofable `request.user_id` removed.
- **Pluggable RBAC hook** (`Authorizer` Protocol) so integrators can wire
  their own policy engine without import-coupling. Session ownership
  enforced.
- **Query length cap** (`auth.max_query_chars`, default 8000).
- **SSRF and bearer-token leak defense** in the REST connector: `next` links
  are parsed and cross-origin or non-`http(s)` URLs rejected before any
  request is made; redirects are refused outright.
- **Subprocess and path-traversal hardening**: `python_executable` must be an
  absolute executable path, `cli_module` must match a strict dotted-name
  regex, and resolved paths must stay under `base_dir`.
- **Unicode-normalized guardrails**: NFKC normalization and zero-width /
  bidi-control stripping before every PII, prompt-security, off-topic, and
  output-policy check.
- **Luhn-validated credit-card detection**, eliminating false positives on
  arbitrary 13–16 digit numbers.

[Unreleased]: https://github.com/Veloxs-ai/nexus/compare/v2.4.0...HEAD
[2.4.0]: https://github.com/Veloxs-ai/nexus/compare/v2.3.0...v2.4.0
[2.3.0]: https://github.com/Veloxs-ai/nexus/compare/v0.1.0...v2.3.0
[0.1.0]: https://github.com/Veloxs-ai/nexus/releases/tag/v0.1.0
