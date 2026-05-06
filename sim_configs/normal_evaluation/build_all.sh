#!/bin/bash
# Build all normal evaluation configs
# Usage: ./build_all.sh [experiment_number]
#   ./build_all.sh        # build all
#   ./build_all.sh 1      # build only experiment 1
#   ./build_all.sh 6-extra # build only new experiment-6 6/10/12-way cases
set -euo pipefail

CHAMPSIM_DIR="$(cd "$(dirname "$0")/../.." && pwd)"
cd "${CHAMPSIM_DIR}"

CONFIG_BASE="sim_configs/normal_evaluation"
FILTER="${1:-all}"

if [[ "${FILTER}" == "6-extra" ]]; then
  "${CONFIG_BASE}/build_6_llc_way_sweep_extra_maxways.sh"
  exit 0
fi

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
  build_configs "2_retirement_threshold"
fi
if [[ "${FILTER}" == "all" || "${FILTER}" == "3" ]]; then
  build_configs "3_error_way_capacity"
fi
if [[ "${FILTER}" == "all" || "${FILTER}" == "4" ]]; then
  build_configs "4_llc_size_baseline"
fi
if [[ "${FILTER}" == "all" || "${FILTER}" == "5" ]]; then
  build_configs "5_llc_size_sensitivity"
fi
if [[ "${FILTER}" == "all" || "${FILTER}" == "6" ]]; then
  build_configs "6_llc_way_sweep"
fi
if [[ "${FILTER}" == "all" || "${FILTER}" == "7" ]]; then
  build_configs "7_no_error_way_sweep"
fi

echo ""
echo "Build complete."
