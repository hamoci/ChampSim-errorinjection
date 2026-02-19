#!/bin/bash
set -euo pipefail

cd /home/hamoci/Study/ChampSim

configs=(
  "./sim_configs/real_final/no_error_hugepage/_2MBLLC_4KBPage_DRAM.json"
  "./sim_configs/real_final/no_error_hugepage/_2MBLLC_2MBPage_DRAM.json"
)

for cfg in "${configs[@]}"; do
  if [[ ! -f "${cfg}" ]]; then
    echo "Missing baseline config: ${cfg}"
    exit 1
  fi
done

echo "Building baseline binaries..."
for cfg in "${configs[@]}"; do
  echo "  - config: ${cfg}"
  ./config.sh "${cfg}"
  make -j"$(nproc)"
done

echo "Baseline build complete."
