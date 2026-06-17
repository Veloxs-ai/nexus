# Architecture

## Purpose

The Orchestration & Guardrails layer controls AI interactions with enterprise data by enforcing safety, policy, privacy, and grounded response requirements.

## Flow

```mermaid
flowchart LR
  A["User Query"] --> B["Prompt Security"]
  B --> C["PII Detection and Masking"]
  C --> D["Policy Enforcement"]
  D --> E["Off-topic Detection"]
  E --> F["RAG Retrieval"]
  F --> G["Grounded Response Composer"]
  G --> H["Output Verification"]
  H --> I["Policy-Compliant Answer"]
```

## Loose Coupling

This project integrates with upstream layers through config paths and index files:

- `data-processing-enrichment` produces enriched records and chunks.
- `embedding-retrieval-intelligence` indexes those outputs.
- `orchestration-guardrails` reads retrieval indexes for grounding and citations.

No runtime imports are shared across projects.

