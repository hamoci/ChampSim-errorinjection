#!/bin/bash
# Machine B (24-core): experiments 3, 4, 5, 7
#   3_error_way_capacity    — 160 runs (error-way capacity sweep)
#   4_llc_size_baseline     —  40 runs (LLC size baseline)
#   5_llc_size_sensitivity  — 160 runs (LLC size sensitivity)
#   7_no_error_way_sweep    — 180 runs (no-error-way variant)
# Total: ~540 runs
#
# Uses POOLED dispatch (queue_experiment + wait_all): a slow straggler in one
# experiment does NOT block jobs from later experiments. Slots free up → next
# job starts immediately, regardless of which experiment it belongs to.
#
# Override:
#   TRACE_DIR=/path  MAX_PARALLEL=N  ./run_machine_b.sh
set -euo pipefail

# 24 physical cores; leave 2 for OS/IO. Tune down if memory-bound.
# IMPORTANT: must be set BEFORE sourcing run_common.sh, since run_common.sh
# locks MAX_PARALLEL to 4 if unset at source time.
export MAX_PARALLEL="${MAX_PARALLEL:-22}"

# Machine B keeps traces on a separate SSD.
export TRACE_DIR="${TRACE_DIR:-/mnt/980pro/hamoci_traces/test_traces}"

source "$(dirname "$0")/run_common.sh"

queue_experiment 3_error_way_capacity    3_error_way_capacity
queue_experiment 4_llc_size_baseline     4_llc_size_baseline
queue_experiment 5_llc_size_sensitivity  5_llc_size_sensitivity
queue_experiment 7_no_error_way_sweep    7_no_error_way_sweep

wait_all
log_msg "========== Machine B: all queued experiments complete =========="
