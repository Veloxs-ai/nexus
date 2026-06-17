# Changelog

All notable changes to Nexus are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- _(nothing yet)_

### Changed

- **Licensed as proprietary.** Nexus is licensed under the Nexus Proprietary
  Software License, owned by Veloxs AI Inc. (The earlier Apache-2.0 metadata
  was never distributed; no public release occurred.)
- Copyright holder formalized as **Veloxs AI Inc.** across `NOTICE`, package
  metadata, and per-file source headers.

### Fixed

- Authorization bypass: the `"anonymous"` role no longer skips tenant and
  capability checks in the experience layer; open access now derives solely
  from `auth.enabled` being disabled.
- Guardrails: input policies are Unicode-normalized before matching, and the
  composed RAG answer is re-screened for prompt-injection/leakage.

### Security

- Path-traversal hardening: I/O URI resolvers now reject relative paths that
  escape their base directory.

---

## [0.1.0] — 2026-06-02

Initial internal build of the Nexus enterprise AI platform by Veloxs AI Inc.
(not publicly released).

### Added

- Seven layers, each independently installable and replaceable:
  - `enterprise-data-pipeline` — REST, batch, streaming, CDC ingestion
  - `data-processing-enrichment` — ETL/ELT, chunking, metadata extraction
  - `embedding-retrieval-intelligence` — vector, lexical, hybrid, graph search
  - `orchestration-guardrails` — PII masking, prompt safety, policy, grounded RAG
  - `experience-api-engagement` — REST API, SDK, CLI, assistant channels
  - `security-governance` — RBAC, tenant isolation, AEAD encryption, audit log
  - `observability-monitoring` — metrics, logs, traces, AI events, alerts
- Root `nexus` package and CLI as the single external entry point
  (`validate-platform`, `layers`, `prepare-demo`, `ask`).
- Public user / integrator guide at [docs/USING_NEXUS.md](docs/USING_NEXUS.md).
- LinkedIn announcement carousel at [docs/nexus-linkedin-post.pdf](docs/nexus-linkedin-post.pdf).
- 181 deterministic, offline tests across 8 suites.

### Security

The initial release ships with the following security defaults already
in place. See [SECURITY.md](SECURITY.md) for the full posture.

- **Authenticated encryption** in `security-governance`: Fernet
  (AES-128-CBC + HMAC-SHA256) with HKDF-SHA256 key derivation and
  `key_id`-salt domain separation. Fails closed when the key env var is
  unset.
- **API-key authentication** in `experience-api-engagement` with
  constant-time comparison (`hmac.compare_digest`) and `env:VAR_NAME`
  indirection for secrets. Spoofable `request.user_id` removed.
- **Pluggable RBAC hook** (`Authorizer` Protocol) so integrators can
  wire `nexus_security.rbac.authorize` or any policy engine without
  import-coupling. Session ownership enforced.
- **Query length cap** (`auth.max_query_chars`, default 8000) to bound
  inputs flowing to the downstream subprocess.
- **SSRF and bearer-token leak defense** in the REST API connector: the
  `next` link is parsed and cross-origin or non-`http(s)` URLs are
  rejected before any request is made.
- **Subprocess + path-traversal hardening** in the root platform and
  engagement gateway: `python_executable` must be an absolute,
  executable path; `cli_module` must match a strict dotted-name regex;
  resolved paths must stay under `base_dir`.
- **Unicode-normalized guardrails**: NFKC normalization and zero-width
  / bidi-control stripping applied before every PII, prompt-security,
  off-topic, and output-policy check. Defeats common prompt-injection
  bypasses.
- **Luhn-validated credit-card PII**: matches only fire when the Luhn
  checksum passes, eliminating false positives on random 13–16-digit
  numbers.

[Unreleased]: https://github.com/Veloxs-ai/nexus/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/Veloxs-ai/nexus/releases/tag/v0.1.0
