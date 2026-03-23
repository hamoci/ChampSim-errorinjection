#!/bin/bash
# Experiment 1 + 3 + 4 combined (240 runs)
# Usage: MAX_PARALLEL=8 ./run_134.sh
set -euo pipefail
source "$(dirname "$0")/run_common.sh"

TOTAL_CONFIGS=$(find "${CONFIG_BASE}/1_error_rate_sweep" "${CONFIG_BASE}/3_error_way_capacity" "${CONFIG_BASE}/4_llc_size_baseline" -name "*.json" | wc -l)

echo "=========================================="
echo " Experiment 1 + 3 + 4 Combined"
echo " Configs: ${TOTAL_CONFIGS}, Traces: ${#SPEC_TRACES[@]}"
echo " Max parallel: ${MAX_PARALLEL}"
echo "=========================================="

run_experiment "1_error_rate_sweep" "1_error_rate_sweep"
run_experiment "3_error_way_capacity" "3_error_way_capacity"
run_experiment "4_llc_size_baseline" "4_llc_size_baseline"

echo "=== All (1+3+4) complete ==="
