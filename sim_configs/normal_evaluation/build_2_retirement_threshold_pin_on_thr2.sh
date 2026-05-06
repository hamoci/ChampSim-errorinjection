#!/bin/bash
# Build only retirement-threshold=2 configs with LLC pinning enabled.
set -euo pipefail

CHAMPSIM_DIR="$(cd "$(dirname "$0")/../.." && pwd)"
cd "${CHAMPSIM_DIR}"

CONFIG_BASE="sim_configs/normal_evaluation"
CONFIG_DIR="${CONFIG_BASE}/2_retirement_threshold/pinning_on"
CONFIGS=("${CONFIG_DIR}"/threshold_2_1e-*.json)

if [[ ! -e "${CONFIGS[0]}" ]]; then
  echo "Missing threshold=2 pinning_on configs."
  echo "Create them first with:"
  echo "  python3 ${CONFIG_BASE}/generate_2_retirement_threshold_pin_on_thr2.py"
  exit 1
fi

echo "=== Building retirement threshold=2, pinning_on (${#CONFIGS[@]} configs) ==="
for config in "${CONFIGS[@]}"; do
  echo "  config.sh ${config}"
  ./config.sh "${config}"
  make -j"$(nproc)" 2>&1 | tail -1
done

echo ""
echo "Build complete."
