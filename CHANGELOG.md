# Changelog

All notable changes to Nexus are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
