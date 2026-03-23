#!/bin/bash
# Experiment 4: LLC Size Baseline (no error)
# 4 configs x 10 traces = 40 runs
#
# Usage: MAX_PARALLEL=8 ./run_4_llc_size_baseline.sh
set -euo pipefail
source "$(dirname "$0")/run_common.sh"

echo "=========================================="
echo " Experiment 4: LLC Size Baseline"
echo " Configs: 4, Traces: ${#SPEC_TRACES[@]}"
echo " Max parallel: ${MAX_PARALLEL}"
echo "=========================================="

run_experiment "4_llc_size_baseline" "4_llc_size_baseline"
