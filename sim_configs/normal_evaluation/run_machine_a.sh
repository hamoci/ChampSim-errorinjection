#!/bin/bash
# Machine A (38-core, this machine): experiments 1, 2, 6
#   1_error_rate_sweep      —  80 runs (BER baseline)
#   2_retirement_threshold  — 400 runs (retirement threshold sweep)
#   6_llc_way_sweep         — 420 runs (LLC way count sweep)
# Total: ~900 runs
#
# Uses POOLED dispatch (queue_experiment + wait_all): a slow straggler in one
# experiment does NOT block jobs from later experiments. Slots free up → next
# job starts immediately, regardless of which experiment it belongs to.
#
# Override:
#   TRACE_DIR=/path  MAX_PARALLEL=N  ./run_machine_a.sh
set -euo pipefail

# 38 physical cores; leave 2 for OS/IO. Tune down if memory-bound.
# IMPORTANT: must be set BEFORE sourcing run_common.sh, since run_common.sh
# locks MAX_PARALLEL to 4 if unset at source time.
export MAX_PARALLEL="${MAX_PARALLEL:-36}"

source "$(dirname "$0")/run_common.sh"

queue_experiment 1_error_rate_sweep      1_error_rate_sweep
queue_experiment 2_retirement_threshold  2_retirement_threshold
queue_experiment 6_llc_way_sweep         6_llc_way_sweep

wait_all
log_msg "========== Machine A: all queued experiments complete =========="
