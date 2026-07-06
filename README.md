# Nexus Enterprise AI Platform

Nexus is a layered enterprise AI platform that turns fragmented data into
secure, grounded, context-aware intelligence — usable from any Python
project as a library, a CLI, or a REST service.

It is built as seven loosely-coupled layers, each independently installable
and replaceable. The root `nexus` package is the single external entry point
and does not import any child-layer code.

## Layers

| # | Layer | Responsibility |
|---|---|---|
| 1 | [enterprise-data-pipeline](enterprise-data-pipeline/) | API, batch, streaming, and CDC ingestion |
| 2 | [data-processing-enrichment](data-processing-enrichment/) | ETL/ELT, document chunking, metadata extraction |
| 3 | [embedding-retrieval-intelligence](embedding-retrieval-intelligence/) | Vector, lexical, hybrid, and graph retrieval |
| 4 | [orchestration-guardrails](orchestration-guardrails/) | Prompt safety, PII masking, policy, grounded RAG |
| 5 | [experience-api-engagement](experience-api-engagement/) | REST API, SDK, assistant, web/mobile channels |
| 6 | [security-governance](security-governance/) | RBAC, tenant isolation, encryption, audit logging |
| 7 | [observability-monitoring](observability-monitoring/) | Metrics, logs, traces, AI events, alerts |

## Quick install

```bash
git clone https://github.com/Veloxs-ai/nexus.git
cd nexus
python3 -m venv .venv && source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
nexus validate-platform configs/nexus.json
```

## Full guide

**See [docs/USING_NEXUS.md](docs/USING_NEXUS.md) for the complete public
user and integrator guide** — installation, per-layer reference, security
model, integration patterns, configuration, deployment, and extension
points.

Also useful:

- [docs/architecture.md](docs/architecture.md) — high-level architecture diagram
- Each layer's own `README.md` for layer-local detail

## License

Nexus is proprietary and confidential software, © 2026 Veloxs AI Inc., all
rights reserved. Use is governed by the Nexus Proprietary Software License —
see [LICENSE](LICENSE). For licensing or pilot inquiries, contact
legal@veloxs.ai.
