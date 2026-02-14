#!/bin/bash
set -euo pipefail

cd /home/hamoci/Study/ChampSim

mapfile -t configs < <(find ./sim_configs/real_final -type f -name "*.json" | sort)

if [[ ${#configs[@]} -eq 0 ]]; then
  echo "No config files found under ./sim_configs/real_final"
  exit 1
fi

echo "Found ${#configs[@]} config files in ./sim_configs/real_final"

for config in "${configs[@]}"; do
  echo "Building config: ${config}"
  ./config.sh "${config}"
  make -j"$(nproc)"
  echo "Successfully built: ${config}"
  echo "----------------------------------------"
done

echo "All real_final configs built successfully."
