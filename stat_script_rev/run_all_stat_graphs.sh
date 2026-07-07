#!/bin/bash
set -euo pipefail

cd /home/hamoci/Study/ChampSim/stat_script_rev
export OMP_NUM_THREADS=1

python3 hugepage_IPC_comparison.py
python3 llc_pin_ipc_comparison.py
python3 llc_notpin_ipc_comparison.py
python3 llc_pin_notpin_avg_ipc_comparison.py
python3 llc_pin_not_pin_individual_ipc.py
python3 llc_normalized_pinning_effect.py
python3 llc_cache_way_usage.py
python3 llc_capacity_ipc_comparison.py
python3 parse_rbmpki_all_paper.py
python3 parse_results_and_plot.py
python3 pageretirement_limit.py

echo "All stat graphs generated in stat_script_rev/."
