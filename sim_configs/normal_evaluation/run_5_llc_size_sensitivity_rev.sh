#!/bin/bash
set -euo pipefail
source "$(dirname "$0")/run_common_rev.sh"
run_experiment "5_llc_size_sensitivity" "5_llc_size_sensitivity"
