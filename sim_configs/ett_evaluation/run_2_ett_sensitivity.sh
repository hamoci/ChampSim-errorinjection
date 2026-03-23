#!/bin/bash
# Experiment 2: ETT Sensitivity (entries + retirement threshold) x 4 rates
# 32 configs x 10 traces = 320 runs
#
# Usage: MAX_PARALLEL=8 ./run_2_ett_sensitivity.sh
set -euo pipefail
source "$(dirname "$0")/run_common.sh"

echo "=========================================="
echo " Experiment 2: ETT Sensitivity"
echo " Configs: 32, Traces: ${#SPEC_TRACES[@]}"
echo " Max parallel: ${MAX_PARALLEL}"
echo "=========================================="

run_experiment "2_ett_sensitivity" "2_ett_sensitivity"
