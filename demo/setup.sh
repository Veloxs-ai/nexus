#!/usr/bin/env bash
# Copyright 2026 Veloxs AI Inc. All rights reserved.
# One-time demo setup. Needs internet ONCE (to pip install). The demo itself is offline.
set -euo pipefail
cd "$(dirname "$0")/.."   # repo root

echo "==> Creating virtual environment (.venv-demo)"
python3 -m venv .venv-demo
# shellcheck disable=SC1091
source .venv-demo/bin/activate
python -m pip install --upgrade pip >/dev/null

echo "==> Installing the Nexus root + all seven layers (one venv)"
python -m pip install -e . >/dev/null
for layer in enterprise-data-pipeline data-processing-enrichment \
             embedding-retrieval-intelligence orchestration-guardrails \
             security-governance observability-monitoring; do
  echo "    - $layer"
  python -m pip install -e "$layer" >/dev/null
done
echo "    - experience-api-engagement [api]  (adds FastAPI + uvicorn for REST)"
python -m pip install -e "experience-api-engagement[api]" >/dev/null

echo "==> Validating platform"
PYTHONPATH=src python -m nexus.cli validate-platform configs/nexus.json

echo
echo "Setup complete. Run the demo with:  ./demo/run_demo.sh"
