#!/bin/bash
set -euo pipefail
source "$(dirname "$0")/run_common_rev.sh"
run_experiment "4_llc_size_baseline" "4_llc_size_baseline"
