#!/bin/bash
# Run experiments 2, 6, 7 against GAP benchmark traces in one shot.
# Uses queue_experiment so the parallel slot pool is shared across all three —
# a freed slot from exp 2 immediately picks up the next exp 6/7 job.
set -euo pipefail
source "$(dirname "$0")/run_common.sh"
source "$(dirname "$0")/run_gap_common.sh"

queue_experiment "2_retirement_threshold" "2_retirement_threshold_gap"
queue_experiment "6_llc_way_sweep"        "6_llc_way_sweep_gap"
queue_experiment "7_no_error_way_sweep"   "7_no_error_way_sweep_gap"

wait_all
echo "[$(date '+%Y-%m-%d %H:%M:%S')] All GAP experiments (2/6/7) finished."
