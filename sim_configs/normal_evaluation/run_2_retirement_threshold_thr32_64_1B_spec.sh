#!/bin/bash
# SPEC, 1B sim, retirement thresholds 32 & 64, pinning ON + OFF.
# Tests whether a lower retirement threshold caps SPEC's accumulating error set
# below the 16,384-slot error-way capacity, preventing the pinning-only collapse
# seen at threshold 256 @1B (78.7% protected). Co-located with the 256 1B dir so
# all 1B SPEC threshold runs (32/64/256) sit together for comparison.
set -euo pipefail
source "$(dirname "$0")/run_common.sh"
SIM=1000000000   # 1B
CONFIGS=(
  "${CONFIG_BASE}/2_retirement_threshold/pinning_on/threshold_32_1e-8.json"
  "${CONFIG_BASE}/2_retirement_threshold/pinning_off/threshold_32_1e-8.json"
  "${CONFIG_BASE}/2_retirement_threshold/pinning_on/threshold_64_1e-8.json"
  "${CONFIG_BASE}/2_retirement_threshold/pinning_off/threshold_64_1e-8.json"
)
run_experiment_configs "2_retirement_threshold_256_1B" "${CONFIGS[@]}"
