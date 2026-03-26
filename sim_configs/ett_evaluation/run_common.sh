#!/bin/bash
# Common functions for ETT evaluation run scripts
# Source this file, do not execute directly.

CHAMPSIM_DIR="$(cd "$(dirname "$0")/../.." && pwd)"
CONFIG_BASE="${CHAMPSIM_DIR}/sim_configs/ett_evaluation"

# SPEC traces (2MB page)
SPEC_TRACES=(
  "${CHAMPSIM_DIR}/test_traces/602.gcc_s-1850B.champsimtrace.xz"
  "${CHAMPSIM_DIR}/test_traces/603.bwaves_s-2931B.champsimtrace.xz"
  "${CHAMPSIM_DIR}/test_traces/605.mcf_s-994B.champsimtrace.xz"
  "${CHAMPSIM_DIR}/test_traces/607.cactuBSSN_s-2421B.champsimtrace.xz"
  "${CHAMPSIM_DIR}/test_traces/620.omnetpp_s-141B.champsimtrace.xz"
  "${CHAMPSIM_DIR}/test_traces/621.wrf_s-6673B.champsimtrace.xz"
  "${CHAMPSIM_DIR}/test_traces/623.xalancbmk_s-592B.champsimtrace.xz"
  "${CHAMPSIM_DIR}/test_traces/628.pop2_s-17B.champsimtrace.xz"
  "${CHAMPSIM_DIR}/test_traces/649.fotonik3d_s-10881B.champsimtrace.xz"
  "${CHAMPSIM_DIR}/test_traces/654.roms_s-1007B.champsimtrace.xz"
)

WARMUP=50000000
SIM=500000000
MAX_PARALLEL="${MAX_PARALLEL:-4}"

parse_exe_name() {
  local config="$1"
  sed -n 's/^[[:space:]]*"executable_name":[[:space:]]*"\([^"]*\)".*/\1/p' "${config}" | head -n1
}

log_msg() {
  local msg="[$(date '+%Y-%m-%d %H:%M:%S')] $1"
  echo "${msg}"
  echo "${msg}" >> "${LOG_FILE}"
}

wait_for_slot() {
  # Wait until running PIDs drop below MAX_PARALLEL
  while true; do
    local alive=0
    local new_pids=()
    for pid in "${PIDS[@]}"; do
      if kill -0 "${pid}" 2>/dev/null; then
        alive=$((alive + 1))
        new_pids+=("${pid}")
      fi
    done
    PIDS=("${new_pids[@]+"${new_pids[@]}"}")
    if [[ ${alive} -lt ${MAX_PARALLEL} ]]; then
      break
    fi
    sleep 1
  done
}

wait_all() {
  for pid in "${PIDS[@]}"; do
    wait "${pid}" 2>/dev/null || true
  done
  PIDS=()
}

run_experiment() {
  local config_dir="$1"
  local result_tag="$2"

  local result_dir="${CHAMPSIM_DIR}/results/ett_evaluation/${result_tag}"
  mkdir -p "${result_dir}"

  # Log file in result directory
  LOG_FILE="${result_dir}/run_log.txt"
  log_msg "========== Starting: ${result_tag} =========="
  log_msg "Max parallel: ${MAX_PARALLEL}"

  local configs
  configs=$(find "${CONFIG_BASE}/${config_dir}" -name "*.json" | sort)

  local total_runs=0
  local skipped_runs=0
  local started_runs=0
  PIDS=()

  for config in ${configs}; do
    local binary
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
      local trace_tag
      trace_tag=$(basename "${trace}" | sed 's/\.champsimtrace\.xz$//' | sed 's/\.champsim\.trace\.gz$//')
      local output_file="${result_dir}/${binary}_${trace_tag}.txt"

      # Skip if already completed
      if [[ -f "${output_file}" ]] && grep -q "Simulation complete" "${output_file}" 2>/dev/null; then
        log_msg "SKIP (done): ${binary} x ${trace_tag}"
        skipped_runs=$((skipped_runs + 1))
        continue
      fi

      # Wait for available slot
      wait_for_slot

      started_runs=$((started_runs + 1))
      log_msg "START [${started_runs}/${total_runs}]: ${binary} x ${trace_tag}"

      # Wrapper: log completion when done
      (
        "${CHAMPSIM_DIR}/bin/${binary}" \
          --warmup-instructions ${WARMUP} \
          --simulation-instructions ${SIM} \
          "${trace}" > "${output_file}" 2>&1
        local exit_code=$?
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
  log_msg "========== Complete: ${result_tag} =========="
  log_msg "Total: ${total_runs}, Skipped: ${skipped_runs}, Ran: ${started_runs}"
}

# 여러 experiment를 하나의 작업 풀로 실행 (experiment 간 대기 없음)
# Usage: run_experiments_merged "1_error_rate_sweep" "3_error_way_capacity" "4_llc_size_baseline"
run_experiments_merged() {
  local merged_tag="merged_$(echo "$@" | tr ' ' '_')"
  local merged_log_dir="${CHAMPSIM_DIR}/results/ett_evaluation"
  mkdir -p "${merged_log_dir}"
  LOG_FILE="${merged_log_dir}/${merged_tag}_log.txt"

  log_msg "========== Starting merged: $* =========="
  log_msg "Max parallel: ${MAX_PARALLEL}"

  local total_runs=0
  local skipped_runs=0
  local started_runs=0
  PIDS=()

  for experiment in "$@"; do
    local result_dir="${CHAMPSIM_DIR}/results/ett_evaluation/${experiment}"
    mkdir -p "${result_dir}"

    local configs
    configs=$(find "${CONFIG_BASE}/${experiment}" -name "*.json" | sort)

    for config in ${configs}; do
      local binary
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
        local trace_tag
        trace_tag=$(basename "${trace}" | sed 's/\.champsimtrace\.xz$//' | sed 's/\.champsim\.trace\.gz$//')
        local output_file="${result_dir}/${binary}_${trace_tag}.txt"

        if [[ -f "${output_file}" ]] && grep -q "Simulation complete" "${output_file}" 2>/dev/null; then
          log_msg "SKIP (done): [${experiment}] ${binary} x ${trace_tag}"
          skipped_runs=$((skipped_runs + 1))
          continue
        fi

        wait_for_slot

        started_runs=$((started_runs + 1))
        log_msg "START [${started_runs}/${total_runs}]: [${experiment}] ${binary} x ${trace_tag}"

        (
          "${CHAMPSIM_DIR}/bin/${binary}" \
            --warmup-instructions ${WARMUP} \
            --simulation-instructions ${SIM} \
            "${trace}" > "${output_file}" 2>&1
          local exit_code=$?
          if [[ ${exit_code} -eq 0 ]] && grep -q "Simulation complete" "${output_file}" 2>/dev/null; then
            echo "[$(date '+%Y-%m-%d %H:%M:%S')] DONE  [${started_runs}]: [${experiment}] ${binary} x ${trace_tag}" >> "${LOG_FILE}"
          else
            echo "[$(date '+%Y-%m-%d %H:%M:%S')] FAIL  [${started_runs}]: [${experiment}] ${binary} x ${trace_tag} (exit=${exit_code})" >> "${LOG_FILE}"
          fi
        ) &
        PIDS+=($!)
      done
    done
  done

  wait_all
  log_msg "========== Complete merged: $* =========="
  log_msg "Total: ${total_runs}, Skipped: ${skipped_runs}, Ran: ${started_runs}"
}
