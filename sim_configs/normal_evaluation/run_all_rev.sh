#!/bin/bash
set -euo pipefail
source "$(dirname "$0")/run_common_rev.sh"

run_experiment "1_error_rate_sweep"      "1_error_rate_sweep"
run_experiment "2_retirement_threshold"  "2_retirement_threshold"
run_experiment "3_error_way_capacity"    "3_error_way_capacity"
run_experiment "4_llc_size_baseline"     "4_llc_size_baseline"
run_experiment "5_llc_size_sensitivity"  "5_llc_size_sensitivity"
