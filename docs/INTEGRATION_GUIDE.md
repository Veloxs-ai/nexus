# Nexus — Integration Guide

Nexus — the **Enterprise Intelligence Framework** — is built to be consumed as a standalone, modular package. You can integrate Nexus into your data pipelines and applications using two main patterns:

1. **Direct Python Library Import** (for single-process in-memory integration).
2. **Subprocess/CLI Wrapper** (for isolated execution, multi-language pipelines, or microservices).

---

## 🛠️ Installation & Environment Setup

Nexus requires **Python 3.11 or 3.12**. Any environment manager works — the
examples below use the standard library's `venv`, which needs nothing extra
installed. Conda, `uv`, `pipenv`, and Poetry all work equally well.

### Option A: Install from PyPI (recommended for integrators)

```bash
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
python -m pip install --upgrade pip

pip install veloxs-nexus
```

Optional extras:

```bash
pip install "veloxs-nexus[postgres]"   # pgvector + SQLAlchemy persistence
pip install "veloxs-nexus[yaml]"       # YAML configuration files
```

Verify:

```bash
python -c "import nexus; print(nexus.__version__)"
nexus --help
```

### Option B: Install from source (for development)

```bash
git clone https://github.com/Veloxs-ai/nexus.git
cd nexus

python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip

# Root package, with development tools
python -m pip install -e ".[dev]"
```

The root install already exposes every layer under the `nexus.*` namespace.
Install a layer separately only when you want to run its own CLI or test
suite in isolation:

```bash
for layer in enterprise-data-pipeline data-processing-enrichment \
             embedding-retrieval-intelligence orchestration-guardrails \
             experience-api-engagement security-governance \
             observability-monitoring; do
  (cd "$layer" && python -m pip install -e ".[dev]")
done
```

> Each `-e` flag needs its own `pip install` invocation — a single
> `pip install -e a -e b` is not valid.

Run the test suite to confirm the install:

```bash
python -m pytest -q
```

---

## 🚀 Pattern A: Direct Python Library Import

This is the most efficient integration pattern. Import the `NexusPlatform` class directly into your data pipeline script.

### 1. Basic In-Memory Ask Query

```python
from pathlib import Path
from nexus import NexusPlatform

# 1. Initialize the platform using your configuration YAML
config_file = Path("configs/nexus.json")
platform = NexusPlatform.from_config(config_file)

# 2. Query the experience layer directly
query = "What is the security policy regarding Multi-Factor Authentication (MFA)?"
response = platform.ask(query, channel="assistant")

print("--- AI Grounded Response ---")
print(response)
```

### 2. Running Demo Ingestion and Indexing Flows

If you want to run the pipeline ingestion (Layer 1), data processing (Layer 2), and build retrieval indexes (Layer 3) programmatically:

```python
from pathlib import Path
from nexus import NexusPlatform

platform = NexusPlatform.from_config(Path("configs/nexus.json"))

# Triggers Layer 2 (transform/chunk) and Layer 3 (indexing/vector store build)
print("Building pipelines...")
logs = platform.prepare_demo()

for log_output in logs:
    print(log_output)
```

---

## 💻 Pattern B: Subprocess & CLI Integration

If you are calling Nexus from a non-Python environment (e.g. Node.js, Go, or a shell script) or want strict process boundary separation, use the subprocess CLI pattern.

### 1. Validate Platform Configuration
Check that all configured layers exist and contain the required layout files (`pyproject.toml`, `README.md`, etc.):

```bash
nexus validate-platform configs/nexus.json
```

*Expected output:*
```text
enterprise-data-pipeline: ready
data-processing-enrichment: ready
embedding-retrieval-intelligence: ready
orchestration-guardrails: ready
experience-api-engagement: ready
security-governance: ready
observability-monitoring: ready
platform_ready: true
```

### 2. Programmatic CLI Queries
Run queries from the command line:

```bash
nexus ask configs/nexus.json "What is the policy for password changes?"
```

---

## 🎛️ Configurations & Environment Variables

Nexus relies on environment variables for cryptographic materials, security authentications, and file paths.

### 1. Main Platform Configuration (`configs/nexus.json`)

Define the path directories and packages of the active layers.

```yaml
platform:
  name: Nexus
  version: 0.1.0

layers:
  enterprise-data-pipeline:
    package: enterprise-data-pipeline
    project_path: enterprise-data-pipeline
    cli_module: nexus_pipeline.cli
    config_path: enterprise-data-pipeline/configs/sources.json
    responsibility: ingest enterprise data from source systems
  
  data-processing-enrichment:
    package: data-processing-enrichment
    project_path: data-processing-enrichment
    cli_module: nexus_processing.cli
    config_path: data-processing-enrichment/configs/processing.json
    responsibility: transform, chunk, and enrich processed data

  # [Include other layers here...]
```

### 2. Environment Variables Checklist

Ensure these variables are loaded in your runtime shell:

Nexus reads these environment variables directly:

| Environment Variable | Read by | Description |
|---|---|---|
| `NEXUS_SECURITY_KEY` | `nexus.security` | Master key material used to derive encryption keys via HKDF-SHA256. The name is configurable per deployment via the `key_material_env` config field; this is the default. Encryption **fails closed** when it is unset. |
| `NEXUS_FPE_KEY` | `nexus.processing` | Key material for FF1 format-preserving tokenization of sensitive fields. |
| `NEXUS_EXPERIENCE_CONFIG` | `nexus.experience` | Path to the engagement config, used when the REST service is started without an explicit config path. |

Nexus never reads a secret from the environment as a silent fallback inside
library code. Where a secret is needed, pass it explicitly, or name the
variable in config so the indirection is visible:

| Config field | Where | Names the variable holding… |
|---|---|---|
| `key_material_env` | `security-governance/configs/security.json` | encryption key material |
| `auth_env` | `enterprise-data-pipeline/configs/sources.json` | a connector's bearer token (e.g. `CRM_API_TOKEN`) |
| `api_key_env` | `observability-monitoring/configs/observability.json` | an exporter's API key (e.g. `DATADOG_API_KEY`) |

> Set these in your process environment or secret manager — never commit them
> to a config file. See [SECURITY.md](../SECURITY.md).

---

## 🔒 Security Best Practices for Clients

> [!IMPORTANT]
> **Subprocess Gateway Safety**
> When deploying the experience-api layer in `subprocess_cli` mode, make sure to configure absolute paths for `guardrails_project` and `guardrails_config` in your settings to avoid directory resolution errors.
