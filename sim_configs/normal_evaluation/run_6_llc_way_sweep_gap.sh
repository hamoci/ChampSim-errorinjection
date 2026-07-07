#!/bin/bash
# Run experiment 6 (LLC size x Error Way Capacity sweep) against GAP benchmark traces.
set -euo pipefail
source "$(dirname "$0")/run_common.sh"
source "$(dirname "$0")/run_gap_common.sh"
run_experiment "6_llc_way_sweep" "6_llc_way_sweep_gap"
