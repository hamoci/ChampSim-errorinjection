#!/bin/bash
# Experiment 8 (CARE + CARE-scrub) for non-SPEC workload traces.
# Mirrors run_xsbench_267.sh conventions: results merge into the existing
# exp-8 result dirs with per-trace filename tags, skip-if-done, elapsed log.
#
#   care_{1e-5..1e-8}       -> results/normal_evaluation/8_care_comparison/
#   care_scrub_{1e-5..1e-8} -> results/normal_evaluation/8_care_comparison_scrub/
#
# Usage:
#   MAX_PARALLEL=38 ./run_8_care_workloads.sh trace1 [trace2 ...]
#   (trace paths relative to repo or absolute)
set -euo pipefail

CHAMPSIM_DIR="$(cd "$(dirname "$0")/../.." && pwd)"
RESULTS_BASE="${RESULTS_BASE:-${CHAMPSIM_DIR}/results/normal_evaluation}"

WARMUP="${WARMUP:-50000000}"
SIM="${SIM:-250000000}"
MAX_PARALLEL="${MAX_PARALLEL:-4}"

[[ $# -ge 1 ]] || { echo "usage: $0 <trace> [trace ...]"; exit 1; }

LOG_FILE="${RESULTS_BASE}/run_8_care_workloads.log"
mkdir -p "${RESULTS_BASE}/8_care_comparison" "${RESULTS_BASE}/8_care_comparison_scrub"

log_msg() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "${LOG_FILE}"; }
fmt_elapsed() { local s=$1; printf "%d:%02d:%02d" $((s/3600)) $((s%3600/60)) $((s%60)); }

wait_for_slot() {
  while true; do
    local alive=0
    for pid in "${PIDS[@]:-}"; do
      [[ -n "${pid}" ]] && kill -0 "${pid}" 2>/dev/null && alive=$((alive + 1))
    done
    [[ ${alive} -lt ${MAX_PARALLEL} ]] && break
    sleep 5
  done
}

PIDS=()
total=0
for TRACE in "$@"; do
  [[ -f "${TRACE}" ]] || { log_msg "SKIP: trace not found: ${TRACE}"; continue; }
  TRACE_TAG="$(basename "${TRACE}" | sed 's/\.champsimtrace\.xz$//' | sed 's/\.champsimtrace\.gz$//' | sed 's/\.champsim\.trace\.gz$//')"

  for rate in 1e-5 1e-6 1e-7 1e-8; do
    for variant in "care:8_care_comparison" "care_scrub:8_care_comparison_scrub"; do
      binary="${variant%%:*}_${rate}"
      group="${variant##*:}"
      if [[ ! -x "${CHAMPSIM_DIR}/bin/${binary}" ]]; then
        log_msg "SKIP: binary not found: ${binary}"
        continue
      fi
      out="${RESULTS_BASE}/${group}/${binary}_${TRACE_TAG}.txt"
      if [[ -f "${out}" ]] && grep -q "Simulation complete" "${out}" 2>/dev/null; then
        log_msg "SKIP (done): ${binary} x ${TRACE_TAG}"
        continue
      fi
      wait_for_slot
      total=$((total + 1))
      log_msg "START [${total}]: ${binary} x ${TRACE_TAG}"
      (
        t0=$(date +%s); ec=0
        "${CHAMPSIM_DIR}/bin/${binary}" \
          --warmup-instructions "${WARMUP}" \
          --simulation-instructions "${SIM}" \
          "${TRACE}" > "${out}" 2>&1 || ec=$?
        t1=$(date +%s); elapsed=$((t1 - t0))
        if [[ ${ec} -eq 0 ]] && grep -q "Simulation complete" "${out}" 2>/dev/null; then
          echo "[$(date '+%Y-%m-%d %H:%M:%S')] DONE : ${binary} x ${TRACE_TAG} elapsed=${elapsed}s ($(fmt_elapsed ${elapsed}))" >> "${LOG_FILE}"
        else
          echo "[$(date '+%Y-%m-%d %H:%M:%S')] FAIL : ${binary} x ${TRACE_TAG} elapsed=${elapsed}s ($(fmt_elapsed ${elapsed})) exit=${ec}" >> "${LOG_FILE}"
        fi
      ) &
      PIDS+=($!)
    done
  done
done

wait
log_msg "=== All runs finished (${total} started) ==="
