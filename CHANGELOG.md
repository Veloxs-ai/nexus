# Changelog

All notable changes to Nexus are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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
