#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
PY="${PARLANT_GATEWAY_PYTHON:-$ROOT/.venv/bin/python3}"
LOG_DIR="$ROOT/var/governance"
mkdir -p "$LOG_DIR"
LOG_FILE="$LOG_DIR/run_pipeline_$(date +%Y%m%d_%H%M%S).log"

{
  "$PY" -m data_pipeline.cli
  "$PY" "$ROOT/scripts/print_manifest_fingerprint.py" "$ROOT/artifacts/manifest.json"
} 2>&1 | tee "$LOG_FILE"

echo "[gate] run_pipeline_output=$LOG_FILE"
