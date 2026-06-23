# Nexus Enterprise AI Platform — Vulnerabilities & Changes Overview

This document tracks all the security vulnerabilities identified and patched in the codebase, the workspace and repository configuration changes, and the current list of simulated features (mocks) that remain to be built for a full production transition.

---

## 🛡️ Security Vulnerabilities Fixed

We have identified and fixed the two primary security vulnerabilities in the platform codebase:

### 1. Path Traversal in Experience Gateway (Layer 5)
* **Vulnerability**: In `nexus/experience-api-engagement/src/nexus_experience/gateway.py`, the path-resolution function did not check if the resolved path stayed inside the workspace base directory boundary. A modified config could exploit this to execute scripts/binaries outside the project root.
* **Update**: Added a recursive directory-containment check using `_is_within()`. Resolving paths outside the workspace boundary now triggers a `GatewaySecurityError`.
* **Verified**: Programmatically validated that the experience-api layer test suite (34 tests) continues to pass successfully.

### 2. Predictable KMS Salt in Platform Key Derivation
* **Vulnerability**: In `veloxs-platform/backend/app/kms.py`, the local KMS provider used raw, static tenant slugs directly as salts for HKDF-SHA256 key derivation.
* **Update**: Re-engineered key derivation to use a salt cryptographically derived from the SHA-256 hash of the `tenant_id` combined with the private master key (`self._master`). This secures the salt against pre-computation dictionary attacks (rainbow tables) even if the database containing ciphertexts is leaked.
* **Verified**: Confirmed all 9 FastAPI backend integration tests for `veloxs-platform` pass with the upgraded key derivation.

---

## 🧹 Repository Configurations & Build Updates

### 1. pyproject.toml Classifiers Fix
* **Issue**: The `pyproject.toml` files in the root `nexus` and all of its seven layers contained the deprecated `"License :: Other/Proprietary License"` classifier. This caused newer versions of Python packaging/setuptools tools to abort installation with validation errors.
* **Update**: Removed the invalid classifier from all 8 `pyproject.toml` files. The platform is now fully installable via standard pip commands: `pip install -e ".[dev]"`.

### 2. Git Status Clean-Up (.gitignore)
* **Issue**: Installing the layers in editable mode generated several untracked `.egg-info` directories which polluted the git state.
* **Update**: Added `*.egg-info/` ignore rules to `nexus/.gitignore` to keep the repository clean.
* **Verified**: Ran `git status` and confirmed no untracked files remain.

---

## ⚙️ Summary of Missing vs. Updated Features

Below is a roadmap of what has been updated and what features remain simulated/mocked for future production development:

| Component / Layer | What Was Updated | What is Still Missing (Mocks/Stubs) |
|---|---|---|
| **Root Platform & CLI** | Fixed setuptools build error in `pyproject.toml`. Added `*.egg-info/` to `.gitignore`. | None. Fully functional local CLI orchestrator. |
| **Layer 1: Pipeline** | Fixed setuptools build error in `pyproject.toml`. | Real database CDC log connectors, S3 cloud object-store adapter, and live Kafka streams. |
| **Layer 2: Processing** | Fixed setuptools build error in `pyproject.toml`. | Advanced BPE/tiktoken tokenizers for text chunking. |
| **Layer 3: Retrieval** | Fixed setuptools build error in `pyproject.toml`. | Machine Learning semantic embeddings generator. ANN/HNSW scaling for large vector directories (linear scans are used). |
| **Layer 4: Guardrails** | Fixed setuptools build error in `pyproject.toml`. | Integration with actual LLM API providers. Hallucination scoring relies on token overlaps instead of neural logic. |
| **Layer 5: Experience** | **Patched path-traversal vulnerability in subprocess gateway.** | Non-FastAPI assistant adapters (e.g. Slack/Teams channels are stubs). |
| **Layer 6: Security** | Fixed setuptools build error in `pyproject.toml`. | AWS KMS envelope encryption requires boto3 dependencies. |
| **Layer 7: Observability** | Fixed setuptools build error in `pyproject.toml`. | Real HTTP/gRPC exporter pushes to Prometheus/OTel endpoints (stubs only validate configs). |
| **Veloxs Platform** | **Patched predictable HKDF salt in Local KMS Provider.** | Background asynchronous task runner (Celery/FastAPI BackgroundTasks) to trigger real CLI runs. |
