# Security & Governance Layer

> Part of **[Nexus — Enterprise Intelligence Framework](../README.md)**, the open-source framework for secure, governed AI applications.
> This layer provides the **Governance** capability.


Enforces end-to-end security, governance, and observability across the platform. This layer protects data and AI interactions through access control, tenant isolation, encryption controls, audit logging, and monitoring-friendly events.

## Capabilities

- **Role-Based Access Control (RBAC)**: Fine-grained permission checks based on user roles and responsibilities.
- **Tenant-Level Data Isolation**: Prevents cross-tenant access by validating tenant context on every request.
- **Encryption**: Provides local encryption helpers for data at rest and TLS configuration checks for data in transit.
- **Audit Logging**: Records user actions, AI operations, authorization decisions, and governance events for traceability and compliance.
- **Observability**: Emits structured operational events for monitoring system behavior, security posture, and AI usage.

## Current Status

This project is runnable locally and includes:

- config-driven roles, permissions, and tenant policies
- RBAC authorization service
- tenant isolation checks
- deterministic local encryption helper
- TLS policy validation
- JSONL audit logger
- observability event recorder
- CLI commands
- automated tests

The implementation is intentionally loosely coupled. It does not import code from ingestion, processing, retrieval, guardrails, or engagement layers. Other layers can call its CLI/service contract or mirror its config policy contract.

## Project Layout

```text
security-governance/
  configs/
    security.json
  data/
    audit/
      .gitkeep
    telemetry/
      .gitkeep
  docs/
    architecture.md
  src/nexus_security/
    audit.py
    cli.py
    config.py
    encryption.py
    models.py
    observability.py
    rbac.py
    service.py
    tenant.py
  tests/
    conftest.py
    test_audit.py
    test_cli.py
    test_config.py
    test_encryption.py
    test_observability.py
    test_rbac.py
    test_service.py
    test_tenant.py
  pyproject.toml
```

## Prerequisites

Install:

- Python 3.11 or newer
- `pip`

Check Python:

```bash
python3 --version
```

## Setup

From the repository root:

```bash
cd path/to/nexus/security-governance
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

Confirm the CLI:

```bash
security --help
```

Without package installation:

```bash
PYTHONPATH=src python -m nexus_security.cli --help
```

## Configuration

Security policies are configured in [configs/security.json](configs/security.json).

The config includes:

- loose references to other architecture layers
- tenants and allowed data scopes
- roles and permissions
- encryption settings
- audit log destination
- observability event destination

Example integration references:

```json
{
  "integration": {
    "experience_project": "../experience-api-engagement",
    "guardrails_project": "../orchestration-guardrails",
    "retrieval_project": "../embedding-retrieval-intelligence",
    "processing_project": "../data-processing-enrichment",
    "ingestion_project": "../enterprise-data-pipeline"
  }
}
```

These are config references only. This project does not import upstream layer code.

## Validate Config

```bash
security validate-config configs/security.json
```

Expected output:

```text
Loaded 3 roles and 2 tenants.
```

Without package installation:

```bash
PYTHONPATH=src python -m nexus_security.cli validate-config configs/security.json
```

## Check Access

```bash
security check-access configs/security.json analyst read:data tenant-a tenant-a
```

Arguments:

- role: `analyst`
- permission: `read:data`
- user tenant: `tenant-a`
- resource tenant: `tenant-a`

Expected:

```text
allowed: true
```

Cross-tenant access is denied unless the role has explicit cross-tenant permission:

```bash
security check-access configs/security.json analyst read:data tenant-a tenant-b
```

## Encrypt And Decrypt Local Values

```bash
security encrypt configs/security.json "sensitive text"
security decrypt configs/security.json "<ciphertext>"
```

The local helper uses key-derived XOR plus base64 for deterministic development behavior. Production should replace it with KMS, Vault, cloud key management, or envelope encryption.

## Write Audit Events

```bash
security audit configs/security.json user.login u001 tenant-a allowed
```

Audit records are written to:

```text
data/audit/audit.jsonl
```

## Run Tests

Run all tests:

```bash
python -m pytest
```

Run one test file:

```bash
python -m pytest tests/test_rbac.py
```

Run with verbose output:

```bash
python -m pytest -v
```

Expected result:

```text
26 passed
```

## Integration Flow

The intended architecture flow is:

1. `experience-api-engagement` receives user and system requests.
2. `security-governance` validates tenant, role, and permission decisions.
3. `orchestration-guardrails` enforces AI safety and response governance.
4. `security-governance` records audit and observability events for all critical operations.
5. Downstream layers use tenant and policy context when reading, processing, retrieving, and serving data.

The projects remain loosely coupled through config and service/CLI contracts.

## Production Next Steps

1. Replace local encryption with KMS, Vault, or cloud key management.
2. Add OIDC/JWT authentication and token claim mapping.
3. Add policy-as-code integration such as OPA.
4. Stream audit logs to SIEM or data lake.
5. Add metrics exporters for Prometheus/OpenTelemetry.
6. Add immutable audit storage and retention policies.
