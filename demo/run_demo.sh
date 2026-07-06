#!/usr/bin/env bash
# Copyright 2026 Veloxs AI Inc. All rights reserved.
# Runs the Nexus client demo end-to-end. Fully OFFLINE (no internet needed).
set -euo pipefail
cd "$(dirname "$0")/.."   # repo root

if [ ! -d .venv-demo ]; then
  echo "No .venv-demo found. Run ./demo/setup.sh first."; exit 1
fi
# shellcheck disable=SC1091
source .venv-demo/bin/activate

run() { PYTHONPATH=src python -m nexus.cli "$@"; }
ask() {
  echo
  echo "────────────────────────────────────────────────────────"
  echo "▶ Question: $1"
  echo "────────────────────────────────────────────────────────"
  run ask configs/nexus.json "$1"
}

echo "==> 1/2  Generating sample enterprise data (policies + customers, with PII)"
python demo/generate_sample_data.py

echo
echo "==> 2/2  Building the pipeline: ingest → process → index  (offline)"
run prepare-demo configs/nexus.json

echo
echo "========================================================================"
echo "  LIVE Q&A  — grounded answers, PII auto-masked, guardrails enforced"
echo "========================================================================"

# Grounded, on-topic answers (note the [EMAIL]/[PHONE] masking + citations)
ask "What is the security access policy?"
ask "How is an invoice handled before payment?"
ask "Tell me about Acme Corp's renewal and support"

# Guardrails in action — these are intentionally refused
ask "What is the admin password?"          # blocked: secret-disclosure policy
ask "What's the weather today?"            # blocked: off-topic guard

echo
echo "Demo complete. Everything above ran locally with no internet access."
