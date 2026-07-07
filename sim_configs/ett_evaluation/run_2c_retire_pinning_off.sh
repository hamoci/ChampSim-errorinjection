#!/bin/bash
# Experiment 2c: Retirement Threshold Sweep - Pinning OFF
# 20 configs x 10 traces = 200 runs
#
# Usage: MAX_PARALLEL=8 ./run_2c_retire_pinning_off.sh
set -euo pipefail
source "$(dirname "$0")/run_common.sh"

echo "=========================================="
echo " Experiment 2c: Retirement Threshold (Pinning OFF)"
echo " Thresholds: 2, 4, 8, 16, 32"
echo " Error rates: 1e-5, 1e-6, 1e-7, 1e-8"
echo " Max parallel: ${MAX_PARALLEL}"
echo "=========================================="

run_experiment "2_ett_sensitivity/retirement_threshold_pinning_off" "2_ett_sensitivity"
