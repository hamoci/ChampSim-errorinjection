#!/bin/bash
# Experiment 1: Error Rate Sweep (1e-5 ~ 1e-8) x Pinning ON/OFF
# 8 configs x 10 traces = 80 runs
#
# Usage: MAX_PARALLEL=8 ./run_1_error_rate_sweep.sh
set -euo pipefail
source "$(dirname "$0")/run_common.sh"

echo "=========================================="
echo " Experiment 1: Error Rate Sweep"
echo " Configs: 8, Traces: ${#SPEC_TRACES[@]}"
echo " Max parallel: ${MAX_PARALLEL}"
echo "=========================================="

run_experiment "1_error_rate_sweep" "1_error_rate_sweep"
