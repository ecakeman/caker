#!/usr/bin/env bash
# Run every scenario in data/sim_scenarios/scenarios.json serially (one full run each).
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
TURNS="${CUSTOMER_SIM_TURNS:-20}"

STAMP="$(date +%Y%m%d_%H%M%S)"
BATCH_DIR="${GOVERNANCE_BATCH_DIR:-$ROOT/var/customer_sim/batch_${STAMP}_all_scenarios}"
mkdir -p "$BATCH_DIR"
LOG="$BATCH_DIR/batch.log"

exec > >(tee -a "$LOG") 2>&1

echo "[batch] started at $(date -Iseconds)"
echo "[batch] turns_per_scenario=$TURNS base_url=$BASE_URL"
echo "[batch] log=$LOG"

if ! curl -sf --max-time 2 "${BASE_URL}/healthz" >/dev/null; then
  echo "[batch] ERROR: gateway not healthy: ${BASE_URL}/healthz" >&2
  exit 3
fi

mapfile -t SCENARIO_IDS < <(
  "$PY_BIN" - <<'PY'
import json
from pathlib import Path
rows = json.loads(Path("data/sim_scenarios/scenarios.json").read_text(encoding="utf-8"))
for s in rows:
    print(s["id"])
PY
)

total="${#SCENARIO_IDS[@]}"
echo "[batch] scenarios=$total"

idx=0
for sid in "${SCENARIO_IDS[@]}"; do
  idx=$((idx + 1))
  echo ""
  echo "[batch] ===== [$idx/$total] scenario=$sid turns=$TURNS ====="
  started="$(date -Iseconds)"
  if "$PY_BIN" "$ROOT/scripts/customer_sim_multiscenario.py" \
    --base-url "$BASE_URL" \
    --scenario "$sid" \
    --turns "$TURNS"; then
    status=ok
  else
    status=failed
  fi
  ended="$(date -Iseconds)"
  run_dir="$("$PY_BIN" - "$ROOT" "$sid" <<'PY'
import sys
from pathlib import Path
root = Path(sys.argv[1])
sid = sys.argv[2]
matches = sorted((root / "var" / "customer_sim").glob(f"20*_{sid}"))
print(matches[-1] if matches else "")
PY
)"
  echo "[batch] [$idx/$total] scenario=$sid status=$status started=$started ended=$ended run_dir=$run_dir"
  echo "$sid,$status,$started,$ended,$run_dir" >> "$BATCH_DIR/results.csv"
  sleep 2
done

echo ""
echo "[batch] finished at $(date -Iseconds)"
echo "[batch] results=$BATCH_DIR/results.csv"
if [[ -n "${RUN_PIPELINE_OUTPUT:-}" ]]; then
  mkdir -p "$BATCH_DIR/gate"
  printf '%s\n' "$RUN_PIPELINE_OUTPUT" > "$BATCH_DIR/gate/run_pipeline_output.path"
fi
if [[ -n "${RESTART_GATEWAY_OUTPUT:-}" ]]; then
  mkdir -p "$BATCH_DIR/gate"
  printf '%s\n' "$RESTART_GATEWAY_OUTPUT" > "$BATCH_DIR/gate/restart_gateway_output.path"
fi
"$PY_BIN" "$ROOT/scripts/build_batch_governance_summary.py" "$BATCH_DIR"
