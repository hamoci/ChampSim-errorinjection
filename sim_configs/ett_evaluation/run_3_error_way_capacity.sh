#!/bin/bash
# Experiment 3: Error Way Capacity (1/4/8 ways) x 4 rates
# 12 configs x 10 traces = 120 runs
#
# Usage: MAX_PARALLEL=8 ./run_3_error_way_capacity.sh
set -euo pipefail
source "$(dirname "$0")/run_common.sh"

echo "=========================================="
echo " Experiment 3: Error Way Capacity"
echo " Configs: 12, Traces: ${#SPEC_TRACES[@]}"
echo " Max parallel: ${MAX_PARALLEL}"
echo "=========================================="

run_experiment "3_error_way_capacity" "3_error_way_capacity"
