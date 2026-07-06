#!/usr/bin/env bash
# Copyright 2026 Veloxs AI Inc. All rights reserved.
# Demonstrates the Nexus Experience REST API the way a client's apps would call it.
# Fully OFFLINE. Starts the API, sends a few requests, then shuts it down.
set -euo pipefail
cd "$(dirname "$0")/.."   # repo root

if [ ! -d .venv-demo ]; then
  echo "No .venv-demo found. Run ./demo/setup.sh first."; exit 1
fi
# shellcheck disable=SC1091
source .venv-demo/bin/activate

PORT="${PORT:-8099}"
B="http://127.0.0.1:${PORT}"

echo "==> Ensuring indexes are built (offline)"
PYTHONPATH=src python -m nexus.cli prepare-demo configs/nexus.json >/dev/null

echo "==> Starting Nexus Experience REST API on ${B}"
PYTHONPATH=experience-api-engagement/src \
NEXUS_EXPERIENCE_CONFIG=experience-api-engagement/configs/engagement.json \
  uvicorn "nexus_experience.api:create_app" --factory --port "${PORT}" --log-level warning &
SERVER_PID=$!
trap 'kill ${SERVER_PID} 2>/dev/null || true' EXIT

curl -s --retry 30 --retry-connrefused --retry-delay 1 "${B}/health" >/dev/null
echo "    API is up."

post() {
  echo
  echo "────────────────────────────────────────────────────────"
  echo "▶ POST /v1/ask   {\"query\": \"$1\"}"
  echo "────────────────────────────────────────────────────────"
  curl -s -X POST "${B}/v1/ask" -H 'Content-Type: application/json' \
    -d "{\"query\": \"$1\", \"channel\": \"assistant\"}" | python3 -m json.tool
}

echo
echo "=== GET /health ==="
curl -s "${B}/health" | python3 -m json.tool

post "What is the security access policy?"          # grounded answer + citations
post "Tell me about Acme Corp renewal and support"  # note [EMAIL]/[PHONE] masking
post "What is the admin password?"                  # blocked by guardrails

echo
echo "Done. Stopping the API. (Auth is disabled in the demo config; enable it in"
echo "engagement.json to require an X-API-Key header.)"
