#!/bin/bash
# Experiment 2 (ETT entries=1,4,8,16): Run small ETT entry configs
# This is a subset of experiment 2 for evaluating ETT overhead justification.
#
# Usage: MAX_PARALLEL=8 ./run_2_ett1_only.sh
set -euo pipefail

CHAMPSIM_DIR="$(cd "$(dirname "$0")/../.." && pwd)"
CONFIG_BASE="${CHAMPSIM_DIR}/sim_configs/ett_evaluation"
source "$(dirname "$0")/run_common.sh"

RESULT_DIR="${CHAMPSIM_DIR}/results/ett_evaluation/2_ett_sensitivity"
mkdir -p "${RESULT_DIR}"

LOG_FILE="${RESULT_DIR}/run_log_ett_small.txt"

ETT_ENTRIES=(1 4 8 16)

echo "=========================================="
echo " Experiment 2: ETT Entries=${ETT_ENTRIES[*]}"
echo " Traces: ${#SPEC_TRACES[@]}"
echo " Max parallel: ${MAX_PARALLEL}"
echo "=========================================="

log_msg "========== Starting: ETT entries=${ETT_ENTRIES[*]} =========="

total_runs=0
skipped_runs=0
started_runs=0
PIDS=()

for entries in "${ETT_ENTRIES[@]}"; do
for config in $(find "${CONFIG_BASE}/2_ett_sensitivity/ett_entries" -name "entries_${entries}_*.json" | sort); do
  binary=$(parse_exe_name "${config}")
  if [[ -z "${binary}" ]]; then
    log_msg "ERROR: Failed to parse executable_name from ${config}"
    continue
  fi
  if [[ ! -x "${CHAMPSIM_DIR}/bin/${binary}" ]]; then
    log_msg "ERROR: Binary not found: bin/${binary} (run build_all.sh 2 first)"
    continue
  fi

  for trace in "${SPEC_TRACES[@]}"; do
    if [[ ! -f "${trace}" ]]; then
      log_msg "SKIP: Trace not found: $(basename "${trace}")"
      continue
    fi

    total_runs=$((total_runs + 1))
    trace_tag=$(basename "${trace}" | sed 's/\.champsimtrace\.xz$//' | sed 's/\.champsim\.trace\.gz$//')
    output_file="${RESULT_DIR}/${binary}_${trace_tag}.txt"

    # Skip if already completed
    if [[ -f "${output_file}" ]] && grep -q "Simulation complete" "${output_file}" 2>/dev/null; then
      log_msg "SKIP (done): ${binary} x ${trace_tag}"
      skipped_runs=$((skipped_runs + 1))
      continue
    fi

    wait_for_slot

    started_runs=$((started_runs + 1))
    log_msg "START [${started_runs}/${total_runs}]: ${binary} x ${trace_tag}"

    (
      "${CHAMPSIM_DIR}/bin/${binary}" \
        --warmup-instructions ${WARMUP} \
        --simulation-instructions ${SIM} \
        "${trace}" > "${output_file}" 2>&1
      exit_code=$?
      if [[ ${exit_code} -eq 0 ]] && grep -q "Simulation complete" "${output_file}" 2>/dev/null; then
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] DONE  [${started_runs}]: ${binary} x ${trace_tag}" >> "${LOG_FILE}"
      else
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] FAIL  [${started_runs}]: ${binary} x ${trace_tag} (exit=${exit_code})" >> "${LOG_FILE}"
      fi
    ) &
    PIDS+=($!)
  done
done
done

wait_all
log_msg "========== Complete: ETT entries=${ETT_ENTRIES[*]} =========="
log_msg "Total: ${total_runs}, Skipped: ${skipped_runs}, Ran: ${started_runs}"
