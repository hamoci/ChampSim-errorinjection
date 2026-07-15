#!/bin/bash
# Integrate the threshold-256 SPEC runs into the paper figures.
#   1) copy the 256 result .txt into paper_figures/results (where
#      generate_raw_data.py reads SPEC results from)
#   2) regenerate raw_data.xlsx  (RE_RETIRE auto-discovers threshold 256)
#   3) re-render fig12 (protected lines) + fig12b (CE/UE) with the 256 column
set -euo pipefail
PF="$(cd "$(dirname "$0")" && pwd)"
SRC="${PF}/../../results/normal_evaluation/2_retirement_threshold"
DST="${PF}/results/2_retirement_threshold"

mkdir -p "${DST}"
cp -v "${SRC}"/retire_o*_256_1e-8_*.txt "${DST}/"

cd "${PF}"
python3 generate_raw_data.py
python3 fig12_protected_lines.py
python3 fig12b_ce_ue_breakdown.py
echo ""
echo "Done -> fig12_protected_lines.{png,pdf}  fig12b_ce_ue_breakdown.{png,pdf}"
