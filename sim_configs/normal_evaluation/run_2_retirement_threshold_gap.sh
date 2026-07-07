#!/bin/bash
# Run experiment 2 (retirement threshold sweep) against GAP benchmark traces.
set -euo pipefail
source "$(dirname "$0")/run_common.sh"
source "$(dirname "$0")/run_gap_common.sh"
run_experiment "2_retirement_threshold" "2_retirement_threshold_gap"
