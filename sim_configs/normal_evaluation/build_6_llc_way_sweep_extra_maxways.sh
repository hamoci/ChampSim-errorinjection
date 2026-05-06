#!/bin/bash
# Build only the newly added experiment-6 maxway cases: 6/10/12 at 1e-7/1e-8.
set -euo pipefail

CHAMPSIM_DIR="$(cd "$(dirname "$0")/../.." && pwd)"
cd "${CHAMPSIM_DIR}"

CONFIG_DIR="sim_configs/normal_evaluation/6_llc_way_sweep"
EXPECTED_CONFIGS=18

mapfile -t CONFIGS < <(
  find "${CONFIG_DIR}" -maxdepth 1 -type f \
    \( -name "LLC_*_maxway_6_1e-7.json" \
    -o -name "LLC_*_maxway_6_1e-8.json" \
    -o -name "LLC_*_maxway_10_1e-7.json" \
    -o -name "LLC_*_maxway_10_1e-8.json" \
    -o -name "LLC_*_maxway_12_1e-7.json" \
    -o -name "LLC_*_maxway_12_1e-8.json" \) | sort
)

if [[ "${1:-}" == "--list" ]]; then
  printf '%s\n' "${CONFIGS[@]}"
  exit 0
fi

if [[ ${#CONFIGS[@]} -ne ${EXPECTED_CONFIGS} ]]; then
  echo "ERROR: expected ${EXPECTED_CONFIGS} extra configs, found ${#CONFIGS[@]}."
  printf '%s\n' "${CONFIGS[@]}"
  exit 1
fi

echo "=== Building 6_llc_way_sweep extra maxways (${#CONFIGS[@]} configs) ==="

for config in "${CONFIGS[@]}"; do
  echo "  config.sh ${config}"
  ./config.sh "${config}"
  make -j"$(nproc)" 2>&1 | tail -1
done

echo ""
echo "Build complete."
