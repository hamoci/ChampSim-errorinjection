#!/bin/bash
set -euo pipefail
source "$(dirname "$0")/run_common.sh"
run_experiment "1_error_rate_sweep" "1_error_rate_sweep"
