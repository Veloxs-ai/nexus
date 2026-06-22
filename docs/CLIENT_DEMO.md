# Nexus — Client Demo (run from your laptop, fully offline)

> Proprietary and confidential. © 2026 Veloxs AI Inc. All rights reserved.

A scripted, repeatable demo that takes raw enterprise data → indexes → **grounded,
guardrailed AI answers** in front of a client. After a one-time setup, **the demo runs
with no internet connection** (local hashing embeddings, no model downloads, no API
calls).

---

## What it demonstrates
- **Grounded answers** from the client's own data, every answer backed by **citations**.
- **Automatic PII masking** — emails/phones come back as `[EMAIL]` / `[PHONE]`.
- **Guardrails enforced** — secret-disclosure and off-topic questions are refused.
- **Runs anywhere, offline** — a strong message for security-conscious enterprises.

---

## One-time setup (needs internet once — to install)
```bash
cd nexus
./demo/setup.sh
```
This creates `.venv-demo`, installs the root CLI + all seven layers, and validates the
platform (`platform_ready: true`).

## Run the demo (offline)
```bash
./demo/run_demo.sh
```
It will: generate sample enterprise data → build the pipeline (ingest → process →
index) → run a live Q&A showing grounded answers, PII masking, and guardrail blocks.

---

## The demo flow & talking points

**1. Sample data is generated** (`demo/generate_sample_data.py`) — 6 policy documents
(security, finance, customer success) and 5 customer profiles **with real-looking PII**.
> "This is stand-in enterprise content; we'll swap in your data next."

**2. The pipeline builds** (`prepare-demo`): ingest → clean/chunk/enrich → build
vector + lexical + graph indexes. ~instant, all local.
> "Eleven documents indexed — no cloud, no model download."

**3. Grounded questions** (decision: allowed):
| Ask | Highlight |
|---|---|
| "What is the security access policy?" | Synthesized from 3 policy docs, with citations |
| "How is an invoice handled before payment?" | Pulls finance policy + related customers |
| "Tell me about Acme Corp's renewal and support" | Note `[EMAIL]` and `[PHONE]` **masked automatically** |

**4. Guardrails in action** (decision: blocked):
| Ask | Why it's refused |
|---|---|
| "What is the admin password?" | Secret-disclosure policy + leakage guard |
| "What's the weather today?" | Off-topic guard (not in the enterprise context) |
> "The system fails closed — it won't leak secrets or answer outside its grounded scope."

---

## Ask your own / use the client's data
Ask ad-hoc questions:
```bash
source .venv-demo/bin/activate
PYTHONPATH=src python -m nexus.cli ask configs/nexus.yaml "How are access reviews done?"
```
Swap in the client's data by editing the two raw files (same JSON shape), then rebuild:
```bash
# data-processing-enrichment/data/raw/policy_documents.jsonl   {document_id,title,department,body}
# data-processing-enrichment/data/raw/customer_profiles.jsonl  {customer_id,customer_name,status,notes}
PYTHONPATH=src python -m nexus.cli prepare-demo configs/nexus.yaml
```
Keep questions within the configured topics (security, access, MFA, encryption, invoice,
payment, finance, customer, renewal, support, data) — tunable in
`orchestration-guardrails/configs/guardrails.yaml`.

---

## Proof it's offline
- Retrieval uses `provider: local_hashing` (see `embedding-retrieval-intelligence/configs/retrieval.yaml`) — deterministic local embeddings, **no model download**.
- The only network code in the platform is the optional REST *ingestion* connector,
  which this demo does not use.
- You can disconnect Wi-Fi before running `./demo/run_demo.sh` to prove it live.

---

## REST API demo (how the client's apps would call Nexus)
A second script starts the **Nexus Experience REST API**, sends a few requests, and shuts
it down — fully offline:
```bash
./demo/run_api_demo.sh
```
It shows `GET /health` and `POST /v1/ask` returning structured JSON — decision, grounded
answer, **citations**, **confidence**, with PII masked — plus a guardrail `blocked`
response. Example:
```json
POST /v1/ask  {"query": "What is the security access policy?", "channel": "assistant"}
{ "decision": "allowed",
  "answer": "Based on retrieved enterprise context: All employees must use MFA ...",
  "citations": [{"source_id": "doc-001:0", "collection": "policy_documents", "score": 0.341}],
  "metadata": {"confidence": "0.872"} }
```
Run the server yourself (leave it up for live calls):
```bash
source .venv-demo/bin/activate
PYTHONPATH=experience-api-engagement/src \
NEXUS_EXPERIENCE_CONFIG=experience-api-engagement/configs/engagement.yaml \
  uvicorn "nexus_experience.api:create_app" --factory --port 8099
# then:  curl -s -X POST http://127.0.0.1:8099/v1/ask -H 'Content-Type: application/json' \
#          -d '{"query":"How are access reviews done?","channel":"assistant"}'
```
> Auth is disabled in the demo config. To require a key, add an `auth` block with
> `enabled: true` + `api_keys` in `experience-api-engagement/configs/engagement.yaml`;
> callers then send `X-API-Key: <key>`.

## Optional — Veloxs Platform UI
The no-code control plane (SSO, RBAC, drag-style pipeline building, KMS secrets). See
the `veloxs-platform` project.

---

## Troubleshooting
| Symptom | Fix |
|---|---|
| `No module named 'nexus'` | Use `PYTHONPATH=src python -m nexus.cli …` (the scripts already do) |
| A question returns `blocked` | It hit a guardrail (secret term or off-topic) — rephrase on-topic |
| Empty/odd answer | Re-run `prepare-demo` after changing data |
| Setup fails on install | One-time internet is required for `./demo/setup.sh` only |
