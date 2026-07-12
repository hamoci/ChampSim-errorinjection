#!/bin/bash
# Experiment 8 (rev): CARE + demand scrubbing, separate result dir so the
# original scrub-off results in results/normal_evaluation/8_care_comparison/
# stay untouched.
set -euo pipefail
source "$(dirname "$0")/run_common.sh"
run_experiment "8_care_comparison_scrub" "8_care_comparison_scrub"
