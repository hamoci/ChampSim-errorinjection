#!/bin/bash
# Experiment 2 @ retirement threshold 256, rate 1e-8, pinning ON + OFF, SPEC.
# 2x simulation instructions (500M; warmup 50M unchanged).
# Separate result dir so it does not mix with the 250M runs.
set -euo pipefail
source "$(dirname "$0")/run_common.sh"
SIM=500000000   # 2x the default 250M
CONFIGS=(
  "${CONFIG_BASE}/2_retirement_threshold/pinning_on/threshold_256_1e-8.json"
  "${CONFIG_BASE}/2_retirement_threshold/pinning_off/threshold_256_1e-8.json"
)
run_experiment_configs "2_retirement_threshold_256_500M" "${CONFIGS[@]}"
