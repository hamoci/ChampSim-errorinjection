#!/bin/bash
# Experiment 2 @ retirement threshold 256, rate 1e-8, pinning ON + OFF, 1B sim.
# SPEC + GAP share ONE slot pool (no barrier: a freed slot immediately picks up
# the next queued run, SPEC or GAP). Separate 1B result dirs (SPEC / GAP).
# Goal: push SPEC's accumulating error set past the 16,384-slot error-way
# capacity to see pinning-only protection degrade (gcc ~31k errors >> capacity).
set -euo pipefail
source "$(dirname "$0")/run_common.sh"
SIM=1000000000   # 1B (4x the default 250M; warmup 50M unchanged)
CONFIGS=(
  "${CONFIG_BASE}/2_retirement_threshold/pinning_on/threshold_256_1e-8.json"
  "${CONFIG_BASE}/2_retirement_threshold/pinning_off/threshold_256_1e-8.json"
)
PIDS=()
queue_experiment_configs "2_retirement_threshold_256_1B" "${CONFIGS[@]}"
source "$(dirname "$0")/run_gap_common.sh"
SPEC_TRACES=( "${TRACE_DIR}"/gap/*.trace.gz )
queue_experiment_configs "2_retirement_threshold_256_1B_gap" "${CONFIGS[@]}"
wait_all
