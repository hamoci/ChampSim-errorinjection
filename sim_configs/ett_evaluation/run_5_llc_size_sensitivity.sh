#!/bin/bash
# Experiment 5: LLC Size Sensitivity (1MB/2MB/4MB/8MB) x 4 rates, pinning ON, max_error_ways=8
# 16 configs x 10 traces = 160 runs
#
# Usage: MAX_PARALLEL=8 ./run_5_llc_size_sensitivity.sh
set -euo pipefail
source "$(dirname "$0")/run_common.sh"

echo "=========================================="
echo " Experiment 5: LLC Size Sensitivity"
echo " (pinning ON, max_error_ways=8)"
echo " Configs: 16, Traces: ${#SPEC_TRACES[@]}"
echo " Max parallel: ${MAX_PARALLEL}"
echo "=========================================="

run_experiment "5_llc_size_sensitivity" "5_llc_size_sensitivity"
