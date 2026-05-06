#!/bin/bash
# Run only retirement-threshold=2 configs with LLC pinning enabled.
set -euo pipefail

source "$(dirname "$0")/run_common.sh"

RESULT_TAG="2_retirement_threshold"
RESULT_DIR="${CHAMPSIM_DIR}/results/normal_evaluation/${RESULT_TAG}"
mkdir -p "${RESULT_DIR}"

LOG_FILE="${RESULT_DIR}/run_log.txt"
CONFIGS=("${CONFIG_BASE}/2_retirement_threshold/pinning_on"/threshold_2_1e-*.json)

if [[ ! -e "${CONFIGS[0]}" ]]; then
  log_msg "ERROR: Missing threshold=2 pinning_on configs."
  log_msg "Create them first with: python3 sim_configs/normal_evaluation/generate_2_retirement_threshold_pin_on_thr2.py"
  exit 1
fi

log_msg "========== Starting: ${RESULT_TAG} / pinning_on threshold=2 only =========="
log_msg "Max parallel: ${MAX_PARALLEL}"

total_runs=0
skipped_runs=0
started_runs=0
PIDS=()

for config in "${CONFIGS[@]}"; do
  binary=$(parse_exe_name "${config}")
  if [[ -z "${binary}" ]]; then
    log_msg "ERROR: Failed to parse executable_name from ${config}"
    continue
  fi
  if [[ ! -x "${CHAMPSIM_DIR}/bin/${binary}" ]]; then
    log_msg "ERROR: Binary not found: bin/${binary} (build first)"
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

wait_all
log_msg "========== Complete: ${RESULT_TAG} / pinning_on threshold=2 only =========="
log_msg "Total: ${total_runs}, Skipped: ${skipped_runs}, Ran: ${started_runs}"
