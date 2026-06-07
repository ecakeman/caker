#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if [[ -f .env ]]; then
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
fi

if [[ "${PARLANT_KEEP_PROXY:-0}" != "1" ]]; then
  unset HTTP_PROXY HTTPS_PROXY ALL_PROXY http_proxy https_proxy all_proxy
fi
export NO_PROXY="127.0.0.1,localhost,0.0.0.0,::1${NO_PROXY:+,$NO_PROXY}"

export PARLANT_PERFORMANCE_POLICY=null

PORT="${PARLANT_PORT:-8084}"
BASE_URL="${PARLANT_BASE_URL:-http://127.0.0.1:${PORT}}"
PY_BIN="${PARLANT_GATEWAY_PYTHON:-${PYTHON:-$ROOT/.venv/bin/python3}}"

_check_health() {
  local attempt=1
  local max=3
  while [[ "$attempt" -le "$max" ]]; do
    if curl -sf --max-time 2 "${BASE_URL}/healthz" >/dev/null; then
      return 0
    fi
    [[ "$attempt" -lt "$max" ]] && sleep $((attempt == 1 ? 2 : 4))
    attempt=$((attempt + 1))
  done
  return 1
}

if ! _check_health; then
  echo "[customer-sim] ERROR: gateway not healthy: ${BASE_URL}/healthz" >&2
  echo "[customer-sim] Run: bash scripts/restart_gateway.sh" >&2
  exit 3
fi

echo "[customer-sim] gateway healthy: ${BASE_URL}"
echo "[customer-sim] mode=scenario_bank (data/sim_scenarios/scenarios.json)"
SIM_ARGS=("$@")
if [[ "$*" != *"--turns"* ]]; then
  SIM_ARGS=(--turns "${CUSTOMER_SIM_TURNS:-20}" "${SIM_ARGS[@]}")
fi
if [[ "$*" != *"--scenario"* ]]; then
  SIM_ARGS=(--scenario "${CUSTOMER_SIM_SCENARIO:-multiscenario}" "${SIM_ARGS[@]}")
fi
exec "$PY_BIN" "$ROOT/scripts/customer_sim_multiscenario.py" --base-url "$BASE_URL" "${SIM_ARGS[@]}"
