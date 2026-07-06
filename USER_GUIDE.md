# Nexus Enterprise AI Platform — User & Integration Guide

Nexus is built to be consumed as a standalone, modular package. You can integrate Nexus into your data pipelines and applications using two main patterns:

1. **Direct Python Library Import** (for single-process in-memory integration).
2. **Subprocess/CLI Wrapper** (for isolated execution, multi-language pipelines, or microservices).

---

## 🛠️ Installation & Environment Setup

Before using Nexus, you must set up the `conda` command-line package and environment manager. You can install it using either **Anaconda** (full suite) or **Miniconda** (lightweight bootstrap).

### Step 1: Install Conda / Anaconda / Miniconda

#### Option A: Installing Miniconda (Recommended & Lightweight)
Miniconda is a small bootstrap version that includes only conda, Python, their dependencies, and a few other packages.
1. Download the Miniconda installer for your operating system from the [official Miniconda download page](https://docs.conda.io/en/latest/miniconda.html).
2. For macOS (Command Line Installer):
   ```bash
   curl -O https://repo.anaconda.com/miniconda/Miniconda3-latest-MacOSX-arm64.sh
   bash Miniconda3-latest-MacOSX-arm64.sh
   ```
3. Follow the prompts on the installer screen. Restart your terminal session after completion.

#### Option B: Installing Anaconda (Full Suite)
Anaconda includes conda, Python, and over 250 automatically installed scientific and data science packages.
1. Download the installer from the [official Anaconda website](https://www.anaconda.com/download).
2. Run the graphical or command-line installer.
3. Verify your installation in a new terminal window:
   ```bash
   conda --version
   ```

---

### Step 2: Initialize & Configure Environment

Once `conda` is installed, create the Python 3.11 environment for Nexus and install all layer packages in editable mode:

```bash
# 1. Clone the repository
git clone https://github.com/Veloxs-ai/nexus.git
cd nexus

# 2. Create the conda environment
conda create -n nexus python=3.11 -y

# 3. Activate the environment
conda activate nexus

# 4. Install the core platform and all layers in editable mode
pip install -e . \
  -e enterprise-data-pipeline \
  -e data-processing-enrichment \
  -e embedding-retrieval-intelligence \
  -e orchestration-guardrails \
  -e experience-api-engagement \
  -e security-governance \
  -e observability-monitoring
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
  name: Nexus Enterprise AI Platform
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

| Environment Variable | Description | Example Value |
|---|---|---|
| `NEXUS_KEY_MATERIAL` | Master key used to derive layer encryption keys via HKDF. | `super-secret-master-encryption-seed-value` |
| `API_TOKEN` | Auth credential for HTTP Rest Connectors. | `bearer-token-1234` |
| `NEXORA_NEXUS_ROOT` | (For platform integration) Path to the root nexus folder. | `/opt/nexus` |

---

## 🔒 Security Best Practices for Clients

> [!IMPORTANT]
> **Subprocess Gateway Safety**
> When deploying the experience-api layer in `subprocess_cli` mode, make sure to configure absolute paths for `guardrails_project` and `guardrails_config` in your settings to avoid directory resolution errors.
