#!/bin/bash
# Experiment 2 @ retirement threshold 256, rate 1e-8, pinning ON + OFF.
# SPEC traces. Outputs into results/normal_evaluation/2_retirement_threshold/
# so it joins the existing threshold sweep (skip-if-done logic applies).
set -euo pipefail
source "$(dirname "$0")/run_common.sh"
CONFIGS=(
  "${CONFIG_BASE}/2_retirement_threshold/pinning_on/threshold_256_1e-8.json"
  "${CONFIG_BASE}/2_retirement_threshold/pinning_off/threshold_256_1e-8.json"
)
run_experiment_configs "2_retirement_threshold" "${CONFIGS[@]}"
