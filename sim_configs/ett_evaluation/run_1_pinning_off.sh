#!/bin/bash
# Experiment 1: Error Rate Sweep - Pinning OFF only
# 4 configs x 10 traces = 40 runs
#
# Usage: MAX_PARALLEL=8 ./run_1_pinning_off.sh
set -euo pipefail
source "$(dirname "$0")/run_common.sh"

echo "=========================================="
echo " Experiment 1: Error Rate Sweep (Pinning OFF)"
echo " Configs: 4, Traces: ${#SPEC_TRACES[@]}"
echo " Max parallel: ${MAX_PARALLEL}"
echo "=========================================="

run_experiment "1_error_rate_sweep/pinning_off" "1_error_rate_sweep"
