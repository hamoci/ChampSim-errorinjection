#!/bin/bash
# Run experiment 6: LLC size x Error Way Capacity sweep (selected workloads only)
set -euo pipefail

source "$(dirname "$0")/run_common.sh"

# Override SPEC_TRACES with selected workloads only
# SPEC_TRACES=(
#   "${CHAMPSIM_DIR}/test_traces/603.bwaves_s-2931B.champsimtrace.xz"
#   "${CHAMPSIM_DIR}/test_traces/605.mcf_s-994B.champsimtrace.xz"
#   "${CHAMPSIM_DIR}/test_traces/620.omnetpp_s-141B.champsimtrace.xz"
#   "${CHAMPSIM_DIR}/test_traces/621.wrf_s-6673B.champsimtrace.xz"
# )

run_experiment "6_llc_way_sweep" "6_llc_way_sweep"
