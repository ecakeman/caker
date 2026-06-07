#!/usr/bin/env bash
# Strong-gate entry: run all 15 scenarios serially and build batch-level summary/diff.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

STAMP="$(date +%Y%m%d_%H%M%S)"
export GOVERNANCE_BATCH_DIR="${GOVERNANCE_BATCH_DIR:-$ROOT/var/customer_sim/batch_${STAMP}_all_scenarios}"
mkdir -p "$GOVERNANCE_BATCH_DIR/gate"

latest_file() {
  local pattern="$1"
  python3 - "$pattern" <<'PY'
import glob, sys
matches = sorted(glob.glob(sys.argv[1]))
print(matches[-1] if matches else "")
PY
}

export RUN_PIPELINE_OUTPUT="${RUN_PIPELINE_OUTPUT:-$(latest_file "$ROOT/var/governance/run_pipeline_*.log")}"
export RESTART_GATEWAY_OUTPUT="${RESTART_GATEWAY_OUTPUT:-$(latest_file "$ROOT/var/governance/restart_gateway_*.log")}"
printf '%s\n' "$RUN_PIPELINE_OUTPUT" > "$GOVERNANCE_BATCH_DIR/gate/run_pipeline_output.path"
printf '%s\n' "$RESTART_GATEWAY_OUTPUT" > "$GOVERNANCE_BATCH_DIR/gate/restart_gateway_output.path"

exec bash "$ROOT/scripts/customer_sim_all_scenarios.sh"
