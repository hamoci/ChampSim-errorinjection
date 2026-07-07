#!/bin/bash
# Experiment 2 @ retirement threshold 256, rate 1e-8, pinning ON + OFF, 500M sim.
# SPEC + GAP share ONE slot pool: no barrier between suites — whenever any run
# finishes, the next queued run (SPEC or GAP) immediately takes the freed slot.
# Results split into separate 500M dirs (SPEC / GAP).
set -euo pipefail
source "$(dirname "$0")/run_common.sh"
SIM=500000000   # 2x the default 250M
CONFIGS=(
  "${CONFIG_BASE}/2_retirement_threshold/pinning_on/threshold_256_1e-8.json"
  "${CONFIG_BASE}/2_retirement_threshold/pinning_off/threshold_256_1e-8.json"
)
PIDS=()
# SPEC (default SPEC_TRACES) -> 500M dir; queue_* does NOT wait, shares the pool
queue_experiment_configs "2_retirement_threshold_256_500M" "${CONFIGS[@]}"
# GAP (full 19-trace set) -> 500M_gap dir; same pool, queued right after SPEC
source "$(dirname "$0")/run_gap_common.sh"
SPEC_TRACES=( "${TRACE_DIR}"/gap/*.trace.gz )
queue_experiment_configs "2_retirement_threshold_256_500M_gap" "${CONFIGS[@]}"
wait_all
