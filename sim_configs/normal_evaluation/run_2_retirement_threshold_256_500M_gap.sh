#!/bin/bash
# Experiment 2 @ retirement threshold 256, rate 1e-8, pinning ON + OFF, GAP (19 traces).
# 2x simulation instructions (500M). Separate result dir. (heavy — run when ready)
set -euo pipefail
source "$(dirname "$0")/run_common.sh"
source "$(dirname "$0")/run_gap_common.sh"
SPEC_TRACES=( "${TRACE_DIR}"/gap/*.trace.gz )   # full 19-trace GAP set
SIM=500000000   # 2x the default 250M
CONFIGS=(
  "${CONFIG_BASE}/2_retirement_threshold/pinning_on/threshold_256_1e-8.json"
  "${CONFIG_BASE}/2_retirement_threshold/pinning_off/threshold_256_1e-8.json"
)
run_experiment_configs "2_retirement_threshold_256_500M_gap" "${CONFIGS[@]}"
