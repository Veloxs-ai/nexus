# Nexus — Enterprise Pilot Guide

> Proprietary and confidential. © 2026 Veloxs AI Inc. All rights reserved.
> Provided to pilot participants under the Nexus Proprietary Software License.

This guide gets your team from zero to a working, grounded, governed AI pipeline on
your own data — and explains enough of how Nexus works for a technical and security
review.

---

## 1. What Nexus is

Nexus turns fragmented enterprise data into **secure, grounded, context-aware AI
answers**. It is delivered as **seven loosely-coupled layers**, each independently
installable and replaceable, that together form a complete path from raw data to a
governed answer — usable as a **library, a CLI, or a REST service**.

## 2. How it works (architecture)

Each layer does one job and integrates with the others **only through config files,
JSONL data contracts, and CLI/HTTP** — never by importing another layer's code. That
is what makes any layer swappable for your own systems.

| # | Layer | Responsibility |
|---|---|---|
| 1 | `enterprise-data-pipeline` | Ingest from APIs, batch drops, streams, CDC |
| 2 | `data-processing-enrichment` | Clean, normalize, chunk, enrich (and tokenize sensitive fields) |
| 3 | `embedding-retrieval-intelligence` | Vector, lexical, hybrid, and graph retrieval |
| 4 | `orchestration-guardrails` | Grounded RAG + PII masking, prompt-injection defense, policy |
| 5 | `experience-api-engagement` | REST / SDK / CLI / assistant channels, auth |
| 6 | `security-governance` | RBAC, tenant isolation, encryption, audit |
| 7 | `observability-monitoring` | Metrics, logs, traces, AI events, alerts |

A single root `nexus` CLI is the front door. It validates the platform and runs each
layer **as a subprocess** (with hardening) — it never imports child-layer code.

### What happens when a user asks a question
```
ask → experience-api-engagement   (authenticate → bind identity → channel check)
     → orchestration-guardrails    (normalize → PII mask → prompt-security → policy)
        → embedding-retrieval       (retrieve grounded context from your indexes)
        → compose grounded answer → verify grounding → output policy
     ← decision + answer + citations
   (security-governance + observability apply across every step)
```
Answers are **grounded in your retrieved data** and **screened both ways** — input and
output — so the system fails closed rather than guessing.

---

## 3. What you'll achieve in the pilot

1. Run the end-to-end demo (data → indexes → grounded answer) in minutes.
2. Point it at a sample of **your** data and ask questions against it.
3. Exercise the **REST API** the way your applications would.
4. Hand your security team a concrete, reviewable governance story.

---

## 4. Prerequisites

- Python **3.11+**, `git`, a terminal (macOS / Linux / WSL).
- Pilot **access to the Nexus repository** (provided by Veloxs AI Inc.).
- A small sample dataset (you can start with the bundled demo data).

---

## 5. Step-by-step

### Step 1 — Get access
Veloxs provisions your pilot access to the Nexus repository and a short licensing
agreement. Clone it:
```bash
git clone <your-licensed-nexus-repo-url> nexus
cd nexus
```

### Step 2 — Install
Install the root entry point and each layer (each is its own installable project):
```bash
python3 -m venv .venv && source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e .                         # the `nexus` root CLI
for layer in enterprise-data-pipeline data-processing-enrichment \
             embedding-retrieval-intelligence orchestration-guardrails \
             security-governance observability-monitoring; do
  (cd "$layer" && python -m pip install -e ".[dev]")
done
(cd experience-api-engagement && python -m pip install -e ".[dev,api]")   # [api] adds REST
```

### Step 3 — Validate the platform
```bash
nexus validate-platform configs/nexus.json
# lists each layer as ready/missing and prints platform_ready: true
```

### Step 4 — Run the end-to-end demo
```bash
nexus prepare-demo configs/nexus.json          # builds processed data + retrieval indexes
nexus ask configs/nexus.json "What is MFA?"    # grounded, guardrailed answer + citations
```
You should get a decision, a grounded answer, and the sources it used.

### Step 5 — Point it at your data
Each layer reads a YAML config (paths are listed in `configs/nexus.json`). To pilot on
your own data, edit:
- `enterprise-data-pipeline/configs/sources.json` — your source(s)
- `data-processing-enrichment/configs/processing.json` — chunking/enrichment (and
  field tokenization for sensitive columns)
- `embedding-retrieval-intelligence/configs/retrieval.json` — index settings
- `orchestration-guardrails/configs/guardrails.json` — PII detectors, policies, grounding

Then re-run `nexus prepare-demo …` and `nexus ask …`.

### Step 6 — Use it from your applications (REST)
```bash
cd experience-api-engagement
NEXUS_EXPERIENCE_CONFIG=configs/engagement.json \
  uvicorn "nexus_experience.api:create_app" --factory --port 8000
# POST /v1/ask   with header  X-API-Key: <key>   { "query": "...", "channel": "assistant" }
```
See [USING_NEXUS.md](USING_NEXUS.md) for the full configuration and integration reference.

---

## 6. For your security & compliance review

Nexus is built security-first; highlights to evaluate:

- **AuthN/AuthZ** — authenticated `Principal` is authoritative (the request body can't
  spoof identity); pluggable RBAC; capability + tenant checks.
- **Tenant isolation** — every access is tenant-scoped; cross-tenant denied by default.
- **Encryption** — Fernet (AES) with HKDF-derived keys; key material from env/KMS.
- **PII** — detection + masking with Luhn-validated credit-card handling; Unicode
  normalization defeats look-alike/zero-width evasion.
- **Reversible tokenization** — NIST FF1 format-preserving encryption for sensitive
  fields that must move source↔target (BIN/last-4 preserved, Luhn-valid optional).
- **Prompt security** — input and output screened for injection/leakage; off-topic and
  policy enforcement; grounded-answer verification.
- **Safe by construction** — no `eval`/`exec`/`pickle`/`os.system`/`shell=True`;
  `yaml.safe_load`; subprocess hardening; TLS validation; JSONL audit log.
- **Testable** — deterministic, offline test suites per layer for CI gating.

See [SECURITY.md](../SECURITY.md) for the full threat model and reporting process.

---

## 7. Optional — the Nexora Platform UI

If you prefer a no-code experience, **Nexora** is a multi-tenant control
plane that wraps these layers in a UI: SSO + RBAC, drag-style pipeline building,
config forms generated from each layer's schema, and a KMS-backed secrets vault. Ask
your Veloxs contact to enable it for your pilot.

---

## 8. Pilot support & success criteria

- **Success criteria (suggested):** ingest a sample dataset, return grounded answers
  with citations, demonstrate PII masking + tokenization, and pass your security review.
- **Support:** your Veloxs contact + `security@veloxs.ai` for vulnerabilities.
- **Licensing / scope questions:** `legal@veloxs.ai`.

We typically run pilots over 2–4 weeks; Veloxs assists with data onboarding and a
guided architecture/security walkthrough.
