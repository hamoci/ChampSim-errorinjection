#!/bin/bash
# Build all ETT evaluation configs
# Usage: ./build_all.sh [experiment_number]
#   ./build_all.sh        # build all
#   ./build_all.sh 1      # build only experiment 1
#   ./build_all.sh 2      # build only experiment 2
set -euo pipefail

CHAMPSIM_DIR="$(cd "$(dirname "$0")/../.." && pwd)"
cd "${CHAMPSIM_DIR}"

CONFIG_BASE="sim_configs/ett_evaluation"
FILTER="${1:-all}"

build_configs() {
  local dir="$1"
  local configs
  configs=$(find "${CONFIG_BASE}/${dir}" -name "*.json" | sort)
  local count
  count=$(echo "${configs}" | wc -l)
  echo "=== Building ${dir} (${count} configs) ==="

  for config in ${configs}; do
    echo "  config.sh ${config}"
    ./config.sh "${config}"
    make -j"$(nproc)" 2>&1 | tail -1
  done
}

if [[ "${FILTER}" == "all" || "${FILTER}" == "1" ]]; then
  build_configs "1_error_rate_sweep"
fi
if [[ "${FILTER}" == "all" || "${FILTER}" == "2" ]]; then
  build_configs "2_ett_sensitivity"
fi
if [[ "${FILTER}" == "all" || "${FILTER}" == "3" ]]; then
  build_configs "3_error_way_capacity"
fi
if [[ "${FILTER}" == "all" || "${FILTER}" == "4" ]]; then
  build_configs "4_llc_size_baseline"
fi

echo ""
echo "Build complete."
