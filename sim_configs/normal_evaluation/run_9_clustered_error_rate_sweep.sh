#!/bin/bash
# Experiment 9: clustered fault-injection sweep (Poisson cluster model).
# Same rate scale as experiment 1 (BER 1e-5..1e-8 -> error_cycle_interval),
# but error_spatial_model=clustered (FIT mode mix 18.6:8.2:10.0, seed 54321).
# Comparison baseline: existing results/normal_evaluation/1_error_rate_sweep
# (uniform mode is bit-identical to the pre-clustered binaries, so the old
# uniform results stay valid — only the clustered side needs runs).
#
#   clu_pin_{on,off}_{1e-5..1e-8} x 14 traces -> results/normal_evaluation/9_clustered_error_rate_sweep/
#
# Mirrors run_8_care_proactive_scrub.sh conventions: skip-if-done, elapsed log.
# Usage: MAX_PARALLEL=38 ./run_9_clustered_error_rate_sweep.sh
set -euo pipefail

CHAMPSIM_DIR="$(cd "$(dirname "$0")/../.." && pwd)"
TRACE_DIR="${TRACE_DIR:-${CHAMPSIM_DIR}/test_traces}"
RESULT_DIR="${CHAMPSIM_DIR}/results/normal_evaluation/9_clustered_error_rate_sweep"

WARMUP="${WARMUP:-50000000}"
SIM="${SIM:-250000000}"
MAX_PARALLEL="${MAX_PARALLEL:-38}"

MAIN_TRACES=(
  "${TRACE_DIR}/602.gcc_s-1850B.champsimtrace.xz"
  "${TRACE_DIR}/603.bwaves_s-2931B.champsimtrace.xz"
  "${TRACE_DIR}/605.mcf_s-994B.champsimtrace.xz"
  "${TRACE_DIR}/607.cactuBSSN_s-2421B.champsimtrace.xz"
  "${TRACE_DIR}/620.omnetpp_s-141B.champsimtrace.xz"
  "${TRACE_DIR}/621.wrf_s-6673B.champsimtrace.xz"
  "${TRACE_DIR}/623.xalancbmk_s-592B.champsimtrace.xz"
  "${TRACE_DIR}/628.pop2_s-17B.champsimtrace.xz"
  "${TRACE_DIR}/649.fotonik3d_s-10881B.champsimtrace.xz"
  "${TRACE_DIR}/654.roms_s-1007B.champsimtrace.xz"
  "${TRACE_DIR}/xsbench_event_large-18.3B.champsimtrace.xz"
  "${TRACE_DIR}/llama2.c-llama2_7b.1.champsimtrace.gz"
  "${TRACE_DIR}/redis-8.8.0_ycsba.champsimtrace.xz"
  "${TRACE_DIR}/redis-8.8.0_ycsbc.champsimtrace.xz"
)

mkdir -p "${RESULT_DIR}"
LOG_FILE="${RESULT_DIR}/run_log.txt"

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

launch() {
  local binary="$1" trace="$2"
  [[ -f "${trace}" ]] || { log_msg "SKIP: trace not found: ${trace}"; return; }
  [[ -x "${CHAMPSIM_DIR}/bin/${binary}" ]] || { log_msg "SKIP: binary not found: ${binary}"; return; }
  local trace_tag
  trace_tag="$(basename "${trace}" | sed 's/\.champsimtrace\.xz$//' | sed 's/\.champsimtrace\.gz$//' | sed 's/\.champsim\.trace\.gz$//')"
  local out="${RESULT_DIR}/${binary}_${trace_tag}.txt"
  if [[ -f "${out}" ]] && grep -q "Simulation complete" "${out}" 2>/dev/null; then
    log_msg "SKIP (done): ${binary} x ${trace_tag}"
    return
  fi
  wait_for_slot
  total=$((total + 1))
  log_msg "START [${total}]: ${binary} x ${trace_tag}"
  (
    t0=$(date +%s); ec=0
    "${CHAMPSIM_DIR}/bin/${binary}" \
      --warmup-instructions "${WARMUP}" \
      --simulation-instructions "${SIM}" \
      "${trace}" > "${out}" 2>&1 || ec=$?
    t1=$(date +%s); elapsed=$((t1 - t0))
    if [[ ${ec} -eq 0 ]] && grep -q "Simulation complete" "${out}" 2>/dev/null; then
      echo "[$(date '+%Y-%m-%d %H:%M:%S')] DONE : ${binary} x ${trace_tag} elapsed=${elapsed}s ($(fmt_elapsed ${elapsed}))" >> "${LOG_FILE}"
    else
      echo "[$(date '+%Y-%m-%d %H:%M:%S')] FAIL : ${binary} x ${trace_tag} elapsed=${elapsed}s ($(fmt_elapsed ${elapsed})) exit=${ec}" >> "${LOG_FILE}"
    fi
  ) &
  PIDS+=($!)
}

for rate in 1e-8 1e-7 1e-6 1e-5; do
  for scheme in clu_pin_on clu_pin_off; do
    for trace in "${MAIN_TRACES[@]}"; do
      launch "${scheme}_${rate}" "${trace}"
    done
  done
done

wait
log_msg "=== All runs finished (${total} started) ==="
