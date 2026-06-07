#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
PY="${PARLANT_GATEWAY_PYTHON:-$ROOT/.venv/bin/python3}"
exec "$PY" main.py
