#!/bin/bash
# Run experiment 7: No-error LLC way sweep (static reservation reference).
# Reduces LLC ways 16 -> 8 at fixed sets (2MB and 4MB capacity bases),
# without errors. Serves as a lower-bound reference for pinning experiments.
set -euo pipefail

source "$(dirname "$0")/run_common.sh"

run_experiment "7_no_error_way_sweep" "7_no_error_way_sweep"
