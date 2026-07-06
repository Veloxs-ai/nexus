# Security Policy

We take the security of Nexus and its users seriously. This document
explains how to report a vulnerability, which versions are supported,
what is in scope, and what security features ship by default.

If you build on Nexus, please also read the **Security model** section of
[docs/USING_NEXUS.md](docs/USING_NEXUS.md) — it covers the threat model
and the documented extension points.

---

## Reporting a vulnerability

**Please do not open a public GitHub issue for security vulnerabilities.**
Public disclosure before a fix is available puts every downstream user at
risk.

### Preferred: GitHub private advisory

Open a [private security advisory](https://github.com/Veloxs-ai/nexus/security/advisories/new)
on this repository. This is the fastest path to a coordinated fix and is
the channel we monitor most closely.

### Alternative: email

If you cannot use GitHub advisories, email **security@veloxs.ai** with
the details below. We will respond from the same address; for sensitive
attachments we can negotiate an encrypted channel on first reply.

### What to include

To help us reproduce and triage quickly, please include:

- A clear description of the vulnerability and its impact.
- Affected version(s), commit SHA(s), and the layer(s) involved
  (e.g. `experience-api-engagement`, `security-governance`).
- A minimal reproduction — steps, sample config, or a proof-of-concept
  script.
- Whether the issue is already public (CVE, blog post, tweet, etc.).
- Your name / handle for credit, or a request to remain anonymous.

### Our response commitments

| Stage | Target |
|---|---|
| Acknowledge receipt | within **3 business days** |
| Initial triage + severity assessment | within **7 business days** |
| Fix and coordinated disclosure | typically **30–90 days** depending on severity and complexity |

We will keep you updated at least every 14 days while a report is open.
For Critical issues we aim for an out-of-band release as soon as a fix is
validated.

---

## Supported versions

Nexus is pre-1.0. Until we tag `v1.0.0`, only the **latest minor release**
receives security fixes.

| Version | Supported |
|---|---|
| `0.1.x` (current) | ✅ |
| `< 0.1` | ❌ |

After `v1.0.0` we will publish a more detailed support window (typically
the latest two minor versions + an LTS line for enterprise users).

---

## Scope

### In scope

- Source code in this repository (`src/nexus/` and all seven layer
  packages under `*/src/`).
- Configuration parsers and the YAML loader paths.
- The REST API exposed by `experience-api-engagement` when started with
  the documented uvicorn command.
- The subprocess wiring between the root `nexus` package, the engagement
  layer, and child-layer CLIs.
- The published `nexus` and per-layer Python packages on PyPI (once
  released).

### Out of scope

- Vulnerabilities in third-party services you wire in (LLM providers,
  vector databases, KMS, OIDC issuers, etc.). Please report those to the
  respective vendors.
- Misconfigurations made by integrators (e.g. checking key material into
  YAML, opening `0.0.0.0` to the internet without auth, running with
  `auth.enabled: false` in production). The framework's job is to make
  the secure path the easy path; integrators are responsible for following
  the documented patterns.
- Reports that depend on attacker-controlled `nexus.yaml` or layer configs.
  Treat platform configs as **trusted input** — anyone who can edit them
  can already replace the running code.
- Denial-of-service via unbounded inputs that the host application is
  expected to bound (rate limits, request-size limits, ingress timeouts).
- Findings that require a compromised host, debugger access, or local
  filesystem write to the install directory.
- Theoretical issues without a working proof of concept.

---

## Security features built in

The current release ships these defaults. Each is covered by tests in
the corresponding layer's `tests/` directory.

### Cryptography (`security-governance`)

- `encrypt_text` / `decrypt_text` use **Fernet** (AES-128-CBC +
  HMAC-SHA256, random IV, authenticated decryption).
- Key derivation: **HKDF-SHA256** with `key_id` as the salt — different
  `key_id`s produce different keys (domain separation).
- **Fails closed** when `key_material_env` is unset; never falls back to
  a constant.
- Decryption raises `EncryptionError` on tamper, wrong key, or malformed
  input.

### Authentication & authorization (`experience-api-engagement`)

- API-key auth via FastAPI `Depends`; constant-time comparison
  (`hmac.compare_digest`).
- Secrets accept `env:VAR_NAME` indirection so they never live in config
  files.
- Authenticated `Principal` is authoritative for identity — the request
  body's `user_id` is **not** trusted.
- Pluggable `Authorizer` Protocol so integrators can wire
  `nexus_security.rbac.authorize` or any other policy engine without
  import-coupling.
- Session ownership enforced; cross-principal `session_id` use is
  rejected.
- `auth.max_query_chars` (default 8000) bounds query length before it
  reaches the downstream subprocess argv.

### Network safety (`enterprise-data-pipeline`)

- `RestApiConnector` parses each `next` link from upstream responses and
  **refuses cross-origin or non-`http(s)` URLs** before any request is
  made.
- **HTTP redirects are refused** (fail closed) — a redirect can silently
  change origin, so the stdlib `urllib` opener raises
  `ConnectorSecurityError` instead of following it.
- Prevents bearer-token leakage, SSRF to cloud metadata services
  (e.g. `169.254.169.254`), and `file://` reads.

### Subprocess + path hardening (`nexus`, `experience-api-engagement`)

- `python_executable` from config must be an absolute path to an
  executable file, or unset (→ `sys.executable`).
- `cli_module` must match `^[A-Za-z_][\w.]*$` — no shell metacharacters.
- `resolve()` rejects paths that escape `base_dir` (`..` traversal,
  absolute paths outside the platform tree).

### Guardrails (`orchestration-guardrails`)

- All prompt / PII / off-topic / output checks first run **NFKC
  normalization** and strip zero-width / bidi-control characters.
  Defeats common prompt-injection bypasses using full-width, RTL
  override, and ZWSP-splitting tricks.
- Credit-card PII detection requires a valid **Luhn checksum**.

### Library-safety hygiene

- No side effects at import time.
- No `logging.basicConfig` or root-logger mutation in library code.
- No `sys.path` or `os.environ` mutations at module load.

### Supply chain (dependency policy)

Nexus is **stdlib-first**: the entire platform runs with exactly two
third-party runtime dependencies, chosen deliberately and reviewed on
every upgrade.

- **`pydantic`** — the typed config/schema contract every layer exposes.
  Control planes (e.g. Nexora) introspect these models to render and
  validate configuration; replacing it with hand-rolled parsing would
  weaken validation, not strengthen it.
- **`cryptography`** — AES/Fernet, HKDF, and the FF1 block-cipher
  primitive. A pure-Python AES would itself be a vulnerability (timing
  side channels, no audit trail); this is the industry-standard,
  audited binding.

Everything else is standard library: CLIs use `argparse`, HTTP ingestion
uses `urllib` (redirects refused), configs are JSON via `json`.
Optional extras, installed only when explicitly requested, never pulled
in by default:

- `[yaml]` → PyYAML, for YAML config files (always `yaml.safe_load`).
- `[api]` (experience layer) → FastAPI + uvicorn for the REST service;
  the core `create_service` path works without it.
- `[dev]` → pytest and ruff, for development only.

The FF1 format-preserving-encryption implementation is verified against
the official NIST SP 800-38G test vectors in
`data-processing-enrichment/tests/`.
- No use of `eval`, `exec`, `pickle`, `os.system`, or `shell=True`.
- `httpx` with TLS verification on by default; no `verify=False`
  anywhere.
- All YAML loaded with `yaml.safe_load`.

---

## Known limitations

These are documented in the layer READMEs and in the **Extension points**
section of [docs/USING_NEXUS.md](docs/USING_NEXUS.md). They are intentional
gaps, not vulnerabilities — but please treat them as design constraints
when assessing risk for your deployment.

| Area | Limitation | Recommended hardening |
|---|---|---|
| Audit log | Plain JSONL append; no tamper-evidence | Add hash-chain or signature; stream to SIEM / WORM storage |
| Session store | In-memory only; not persisted, not multi-worker | Replace with Redis or Postgres |
| Key material | Env-var → HKDF (no rotation, no KMS) | Wire KMS / Vault / cloud KMS into `get_key_material` |
| Off-topic gate | Keyword overlap | Replace with retrieval-similarity threshold |
| PII catalog | Email, SSN, phone, credit card (Luhn) | Integrate Presidio or AWS Comprehend for breadth |
| Rate limiting | Not implemented at the engagement layer | Add per-tenant token bucket at ingress |
| TLS enforcement | `validate_tls` is self-attested | Enforce TLS termination at your ingress |
| Library paths | Some defaults are cwd-relative | Override with absolute paths in production |

---

## Disclosure policy

We follow **coordinated disclosure**:

1. You report privately via the channels above.
2. We acknowledge, triage, and assign a severity (CVSS v3.1).
3. We develop a fix, write a security advisory, and request a CVE if
   appropriate.
4. We coordinate a release date with you. By default we aim for **90 days**
   from initial report; faster for actively-exploited Critical issues,
   slower if a fix requires significant API changes and we want to give
   integrators time to migrate.
5. We publish the advisory, release the fix, and credit the reporter
   (unless anonymity was requested).

We will not pursue legal action against researchers who:

- Make a good-faith effort to follow this policy.
- Avoid privacy violations, data destruction, and service disruption.
- Do not access or exfiltrate user data beyond what is necessary to
  demonstrate the vulnerability.
- Give us reasonable time to fix before public disclosure.

---

## Acknowledgements

We publicly thank researchers who responsibly disclose security issues
(unless they request anonymity). The list will be maintained in
`docs/SECURITY_ACKNOWLEDGEMENTS.md` once the first report is closed.

---

## Changes to this policy

Material changes to this policy will be announced in the repository
release notes. The canonical version of this document always lives at
[SECURITY.md](SECURITY.md) on the default branch.

_Last updated: 2026-06-02_
