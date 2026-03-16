#!/bin/bash
set -euo pipefail

cd /home/hamoci/Study/ChampSim

configs=(
  "./sim_configs/only_for_test/_2MBLLC_2MBPage_DRAM_Error_1e-8_psc_thrash.json"
  "./sim_configs/only_for_test/_2MBLLC_4KBPage_DRAM_Error_1e-8_psc_thrash.json"
)

for config in "${configs[@]}"; do
  if [[ ! -f "${config}" ]]; then
    echo "Config not found: ${config}"
    exit 1
  fi
done

for config in "${configs[@]}"; do
  echo "Building from config: ${config}"
  ./config.sh "${config}"
  make -j"$(nproc)"
done

echo "All only_for_test configs built successfully."
