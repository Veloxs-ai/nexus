# Copyright 2026 Veloxs AI Inc. All rights reserved.
# SPDX-License-Identifier: LicenseRef-Veloxs-AI-Proprietary
"""Generate a sample enterprise dataset for the Nexus client demo.

Writes policy documents and customer profiles (with realistic PII, so masking is
visible) into the data-processing layer's raw landing zone. Deterministic and fully
offline. Re-run any time, then `nexus prepare-demo` to rebuild indexes.
"""
from __future__ import annotations

import json
from pathlib import Path

RAW = Path(__file__).resolve().parents[1] / "data-processing-enrichment" / "data" / "raw"

POLICY_DOCUMENTS = [
    {"document_id": "doc-001", "title": "Security Access Policy", "department": "information security",
     "body": "All employees must use MFA for sensitive systems. Access reviews are required quarterly. "
             "Encryption is mandatory for confidential exports. Contact security@veloxsdemo.com for exceptions."},
    {"document_id": "doc-002", "title": "Data Encryption Standard", "department": "information security",
     "body": "Confidential data must be encrypted at rest and in transit using approved algorithms. "
             "TLS 1.2 or higher is required for all access to internal systems. Keys are rotated annually."},
    {"document_id": "doc-003", "title": "Account Access Review Procedure", "department": "information security",
     "body": "Access to customer accounts follows least privilege. Quarterly access reviews remove stale "
             "permissions. Privileged access requires manager approval and is logged for audit."},
    {"document_id": "doc-004", "title": "Invoice Handling Procedure", "department": "finance",
     "body": "Invoices must be reviewed before payment. Revenue-impacting adjustments require finance approval. "
             "Send invoice questions to ap@veloxsdemo.com by the monthly close date."},
    {"document_id": "doc-005", "title": "Payment and Refund Policy", "department": "finance",
     "body": "Customer payments are reconciled weekly. Refunds above the threshold require finance approval. "
             "Disputed invoices are escalated to the revenue team within two business days."},
    {"document_id": "doc-006", "title": "Customer Support SLA", "department": "customer success",
     "body": "Support requests receive a first response within four business hours. Renewal and account "
             "questions are routed to customer success. Critical issues are escalated to on-call support."},
]

CUSTOMER_PROFILES = [
    {"customer_id": "c001", "customer_name": " Acme Corp ", "status": " ACTIVE ",
     "notes": "Contact jane.doe@acme.com or call 415-555-0132 about renewal on 2026-06-15. "
              "Account has open support questions."},
    {"customer_id": "c002", "customer_name": "Northwind", "status": "prospect", "lifecycle_stage": "sales",
     "notes": "Payment discussion scheduled with finance team. Expected revenue review next month."},
    {"customer_id": "c003", "customer_name": " Globex ", "status": "active",
     "notes": "Renewal due 2026-09-01. Primary contact sam@globex.com. Strong support satisfaction."},
    {"customer_id": "c004", "customer_name": "Initech", "status": "at_risk", "lifecycle_stage": "retention",
     "notes": "Escalated support tickets last quarter. Renewal at risk; finance reviewing invoice disputes."},
    {"customer_id": "c005", "customer_name": "Umbrella Health", "status": "prospect",
     "notes": "Evaluating security and encryption controls. Contact dana@umbrella.example by 2026-07-10."},
]


def _write(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row) + "\n")
    print(f"wrote {len(rows):>2} records -> {path.relative_to(RAW.parents[2])}")


def main() -> None:
    _write(RAW / "policy_documents.jsonl", POLICY_DOCUMENTS)
    _write(RAW / "customer_profiles.jsonl", CUSTOMER_PROFILES)
    print("Sample enterprise data generated. Next: nexus prepare-demo configs/nexus.yaml")


if __name__ == "__main__":
    main()
