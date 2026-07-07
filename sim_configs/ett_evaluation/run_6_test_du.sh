#!/bin/bash
# Experiment 6 quick test: du_sh trace only, no warmup/sim limits
# Standalone script — does not use run_common.sh
#
# Usage:
#   MAX_PARALLEL=8 ./run_6_test_du.sh        # all 108 configs
#   MAX_PARALLEL=8 ./run_6_test_du.sh 1      # e16 only (36)
#   MAX_PARALLEL=8 ./run_6_test_du.sh 2      # e64 only (36)
#   MAX_PARALLEL=8 ./run_6_test_du.sh 3      # e128 only (36)
set -euo pipefail

CHAMPSIM_DIR="$(cd "$(dirname "$0")/../.." && pwd)"
CONFIG_BASE="${CHAMPSIM_DIR}/sim_configs/ett_evaluation"
TRACE="${CHAMPSIM_DIR}/test_traces/du_sh_trace.chamsim"
MAX_PARALLEL="${MAX_PARALLEL:-4}"
PART="${1:-all}"

case "${PART}" in
  1)   CONFIG_DIR="${CONFIG_BASE}/6_combined_sweep/e16";  LABEL="Part 1/3 (e16)" ;;
  2)   CONFIG_DIR="${CONFIG_BASE}/6_combined_sweep/e64";  LABEL="Part 2/3 (e64)" ;;
  3)   CONFIG_DIR="${CONFIG_BASE}/6_combined_sweep/e128"; LABEL="Part 3/3 (e128)" ;;
  all) CONFIG_DIR="${CONFIG_BASE}/6_combined_sweep";      LABEL="All" ;;
  *)   echo "Usage: $0 [1|2|3|all]"; exit 1 ;;
esac

RESULT_DIR="${CHAMPSIM_DIR}/results/ett_evaluation/6_combined_sweep_du_test"
mkdir -p "${RESULT_DIR}"
LOG_FILE="${RESULT_DIR}/run_log.txt"

log_msg() { local m="[$(date '+%Y-%m-%d %H:%M:%S')] $1"; echo "${m}"; echo "${m}" >> "${LOG_FILE}"; }

PIDS=()
wait_for_slot() {
  while true; do
    local new_pids=() alive=0
    for pid in "${PIDS[@]}"; do
      if kill -0 "${pid}" 2>/dev/null; then alive=$((alive+1)); new_pids+=("${pid}"); fi
    done
    PIDS=("${new_pids[@]+"${new_pids[@]}"}")
    [[ ${alive} -lt ${MAX_PARALLEL} ]] && break
    sleep 1
  done
}

echo "=========================================="
echo " Experiment 6: Combined Sweep (du test)"
echo " ${LABEL}"
echo " Trace: du_sh_trace.chamsim (no warmup)"
echo " Max parallel: ${MAX_PARALLEL}"
echo "=========================================="

if [[ ! -f "${TRACE}" ]]; then echo "ERROR: trace not found: ${TRACE}"; exit 1; fi

configs=$(find "${CONFIG_DIR}" -name "*.json" | sort)
started=0

for config in ${configs}; do
  binary=$(sed -n 's/^[[:space:]]*"executable_name":[[:space:]]*"\([^"]*\)".*/\1/p' "${config}" | head -n1)
  if [[ ! -x "${CHAMPSIM_DIR}/bin/${binary}" ]]; then
    log_msg "SKIP: bin/${binary} not found"
    continue
  fi

  output="${RESULT_DIR}/${binary}_du_sh_trace.txt"
  if [[ -f "${output}" ]] && grep -q "Simulation complete" "${output}" 2>/dev/null; then
    log_msg "SKIP (done): ${binary}"
    continue
  fi

  wait_for_slot
  started=$((started+1))
  log_msg "START [${started}]: ${binary}"

  (
    "${CHAMPSIM_DIR}/bin/${binary}" "${TRACE}" > "${output}" 2>&1
    if [[ $? -eq 0 ]] && grep -q "Simulation complete" "${output}" 2>/dev/null; then
      echo "[$(date '+%Y-%m-%d %H:%M:%S')] DONE: ${binary}" >> "${LOG_FILE}"
    else
      echo "[$(date '+%Y-%m-%d %H:%M:%S')] FAIL: ${binary}" >> "${LOG_FILE}"
    fi
  ) &
  PIDS+=($!)
done

for pid in "${PIDS[@]}"; do wait "${pid}" 2>/dev/null || true; done
log_msg "Complete. Started: ${started}"
