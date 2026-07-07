#!/bin/bash
# Experiment 6: Combined Sweep — ett_entries(3) x threshold(3) x max_ways(3) x error_rate(4)
# 108 configs x 10 traces = 1080 runs
#
# Usage:
#   MAX_PARALLEL=8 ./run_6_combined_sweep.sh        # run all
#   MAX_PARALLEL=8 ./run_6_combined_sweep.sh 1       # run part 1/3 (e16_*)
#   MAX_PARALLEL=8 ./run_6_combined_sweep.sh 2       # run part 2/3 (e64_*)
#   MAX_PARALLEL=8 ./run_6_combined_sweep.sh 3       # run part 3/3 (e128_*)
set -euo pipefail
source "$(dirname "$0")/run_common.sh"

PART="${1:-all}"

case "${PART}" in
  1)
    CONFIG_DIR="6_combined_sweep/e16"
    LABEL="Part 1/3 (e16: 36 configs)"
    ;;
  2)
    CONFIG_DIR="6_combined_sweep/e64"
    LABEL="Part 2/3 (e64: 36 configs)"
    ;;
  3)
    CONFIG_DIR="6_combined_sweep/e128"
    LABEL="Part 3/3 (e128: 36 configs)"
    ;;
  all)
    CONFIG_DIR="6_combined_sweep"
    LABEL="All (108 configs)"
    ;;
  *)
    echo "Usage: $0 [1|2|3|all]"
    exit 1
    ;;
esac

echo "=========================================="
echo " Experiment 6: Combined Sweep"
echo " ${LABEL}"
echo " Traces: ${#SPEC_TRACES[@]}"
echo " Max parallel: ${MAX_PARALLEL}"
echo "=========================================="

run_experiment "${CONFIG_DIR}" "6_combined_sweep"
