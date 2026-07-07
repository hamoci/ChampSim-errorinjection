#!/bin/bash
# Experiment 2 @ retirement threshold 256, rate 1e-8, pinning ON + OFF.
# GAP traces. Outputs into results/normal_evaluation/2_retirement_threshold_gap/
# so the 256 point joins the existing GAP threshold sweep (generate_raw_data
# reads GAP from this dir; skip-if-done logic protects the existing 2..32 runs).
set -euo pipefail
source "$(dirname "$0")/run_common.sh"
source "$(dirname "$0")/run_gap_common.sh"
# run_gap_common.sh only enables 8 traces, but the existing GAP threshold sweep
# used all 19. Override with the full GAP set so the 256 point is comparable.
SPEC_TRACES=( "${TRACE_DIR}"/gap/*.trace.gz )
CONFIGS=(
  "${CONFIG_BASE}/2_retirement_threshold/pinning_on/threshold_256_1e-8.json"
  "${CONFIG_BASE}/2_retirement_threshold/pinning_off/threshold_256_1e-8.json"
)
run_experiment_configs "2_retirement_threshold_gap" "${CONFIGS[@]}"
