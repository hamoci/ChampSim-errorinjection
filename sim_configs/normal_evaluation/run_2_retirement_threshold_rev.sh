#!/bin/bash
set -euo pipefail
source "$(dirname "$0")/run_common_rev.sh"
run_experiment "2_retirement_threshold" "2_retirement_threshold"
