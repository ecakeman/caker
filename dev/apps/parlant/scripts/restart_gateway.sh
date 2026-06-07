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

PORT="${PARLANT_PORT:-8084}"
TOOL_PORT="${PARLANT_TOOL_SERVICE_PORT:-9019}"

if [[ -n "${PARLANT_GATEWAY_PYTHON:-}" ]]; then
  PY_BIN="$PARLANT_GATEWAY_PYTHON"
elif [[ -x "$ROOT/.venv/bin/python3" ]]; then
  PY_BIN="$ROOT/.venv/bin/python3"
elif [[ -x "$ROOT/.venv/bin/python" ]]; then
  PY_BIN="$ROOT/.venv/bin/python"
elif [[ -n "${PYTHON:-}" ]]; then
  PY_BIN="$PYTHON"
else
  PY_BIN="$(command -v python3)"
fi
LOG_DIR="${GATEWAY_LOG_DIR:-var/gateway/process}"
LOG_FILE="${GATEWAY_LOG_FILE:-${LOG_DIR}/gateway.log}"
PID_FILE="${GATEWAY_PID_FILE:-${LOG_DIR}/gateway.pid}"
GATE_LOG_DIR="var/governance"
GATE_LOG_FILE="${GATE_LOG_DIR}/restart_gateway_$(date +%Y%m%d_%H%M%S).log"

mkdir -p "$LOG_DIR"
mkdir -p "$GATE_LOG_DIR"
exec > >(tee -a "$GATE_LOG_FILE") 2>&1

list_port_pids() {
  local port="$1"
  ss -lptn "sport = :${port}" 2>/dev/null \
    | sed -n 's/.*pid=\([0-9][0-9]*\).*/\1/p' \
    | sort -u
}

stop_port() {
  local port="$1"
  local label="$2"
  local pids
  pids="$(list_port_pids "$port" || true)"
  if [[ -z "$pids" ]]; then
    echo "[restart-gateway] ${label} port ${port}: free"
    return
  fi

  echo "[restart-gateway] ${label} port ${port}: stopping pid(s): ${pids//$'\n'/ }"
  # shellcheck disable=SC2086
  kill $pids 2>/dev/null || true

  for _ in $(seq 1 20); do
    sleep 0.5
    if [[ -z "$(list_port_pids "$port" || true)" ]]; then
      echo "[restart-gateway] ${label} port ${port}: stopped"
      return
    fi
  done

  pids="$(list_port_pids "$port" || true)"
  if [[ -n "$pids" ]]; then
    echo "[restart-gateway] ${label} port ${port}: force stopping pid(s): ${pids//$'\n'/ }"
    # shellcheck disable=SC2086
    kill -9 $pids 2>/dev/null || true
  fi
}

stop_port "$PORT" "gateway"
stop_port "$TOOL_PORT" "tool-service"

echo "[restart-gateway] expect (local) health: http://127.0.0.1:${PORT}/healthz"
echo "[restart-gateway] starting gateway with ${PY_BIN}"
echo "[restart-gateway] log: ${LOG_FILE}"
echo "[restart-gateway] PARLANT_PERFORMANCE_POLICY=${PARLANT_PERFORMANCE_POLICY:-null}"
echo "[restart-gateway] PARLANT_MAX_ENGINE_ITERATIONS=${PARLANT_MAX_ENGINE_ITERATIONS:-1}"
echo "[restart-gateway] PARLANT_RESPONSE_MODE=${PARLANT_RESPONSE_MODE:-one_shot}"
if [[ -f "$ROOT/artifacts/manifest.json" ]]; then
  "$PY_BIN" "$ROOT/scripts/print_manifest_fingerprint.py" "$ROOT/artifacts/manifest.json" || true
fi
nohup env PYTHON="$PY_BIN" bash scripts/run_gateway.sh >"$LOG_FILE" 2>&1 &
pid="$!"
echo "$pid" >"$PID_FILE"
echo "[restart-gateway] pid: ${pid}"

health_url="http://127.0.0.1:${PORT}/healthz"
for _ in $(seq 1 90); do
  if curl -sf --max-time 2 "$health_url" >/dev/null; then
    echo "[restart-gateway] OK: ${health_url}"
    echo "[gate] restart_gateway_output=$GATE_LOG_FILE"
    if [[ -f "$LOG_FILE" ]]; then
      echo "[restart-gateway] loaded manifest fingerprint from gateway log:"
      grep -E "manifest_(sha256|fingerprint)|bootstrap completed" "$LOG_FILE" | tail -5 || true
    fi
    exit 0
  fi

  if ! kill -0 "$pid" 2>/dev/null; then
    echo "[restart-gateway] ERROR: gateway exited before health check passed" >&2
    echo "[restart-gateway] last log lines:" >&2
    tail -80 "$LOG_FILE" >&2 || true
    exit 1
  fi
  sleep 1
done

echo "[restart-gateway] ERROR: health check timed out: ${health_url}" >&2
echo "[restart-gateway] last log lines:" >&2
tail -80 "$LOG_FILE" >&2 || true
exit 1
