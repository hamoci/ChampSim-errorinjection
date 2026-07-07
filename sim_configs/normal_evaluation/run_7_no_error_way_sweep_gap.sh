#!/bin/bash
# Run experiment 7 (no-error LLC way sweep) against GAP benchmark traces.
set -euo pipefail
source "$(dirname "$0")/run_common.sh"
source "$(dirname "$0")/run_gap_common.sh"
run_experiment "7_no_error_way_sweep" "7_no_error_way_sweep_gap"
