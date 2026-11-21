# Changelog

All notable changes to Nexus are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [3.2.0] — 2026-11-21

Data-loss, chunk-size, record and PII fixes for retrieval over everything a customer uploads or connects. No public method is renamed or removed; the outputs below change, as described under **Changed**.

### Added
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

### Changed
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

### Fixed
- **MP3 transcripts lost ~95% of their words**: the duration was estimated from the compressed bytes (a 72.5 s file measured 1.03 s), so only the transcript of the first second survived. All 146 of 146 words are now kept on the test recording.
- Silent truncations removed: Slack threads over 4,500 characters (now split into parts with the thread header), video scene dialogue cut at 140 characters, Python class bodies and script-only modules cut at 2,000 characters, unparseable snippets at 500. Module-level code between functions (imports, constants, `__main__` blocks) and class attributes, previously dropped, are now chunked for Python and the other languages.
- An XLSX with embedded images failed with a `TypeError` while building the image-text chunk.
- New coverage contract test: for every processor the stored chunks keep at least 90% of the extracted words, and no chunk exceeds the token cap.
- **PDFs from modern producers** (xref streams, object streams, CID fonts) came out as binary noise or empty pages, and large files ran for minutes in the regular-expression scanner. The scanner is kept only as the fallback for bytes the new reader cannot open.
- `chunk_smart_text` was quadratic (re-slicing the remaining text after every chunk): 8 MB took 4.4 s; it is now linear with identical output (~0.2 s).
- A Markdown table split across chunks kept its header only in the first chunk (80-row probe: `[True, False, False, False, False]`); every piece now has it.
- `{"data": [200 records]}` JSON became one chunk with no records; counts and totals over JSON exports are now computed from records.
- The package's Documentation link and the README point to nexus.veloxs.ai/documentation.html and the guide; the /docs/ address used in 3.1.1 is not served.

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
