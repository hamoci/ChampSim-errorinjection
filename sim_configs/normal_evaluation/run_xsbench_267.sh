#!/bin/bash
# Run experiments 2/6/7 for a new workload trace (default: XSBench).
# Mirrors the existing per-SPEC-workload matrix exactly (same binaries,
# same warmup/sim), so results merge into the raw_data.xlsx pipeline
# without any parser changes.
#
#   exp2 (2_retirement_threshold): retire_{on,off} x thr{2,4,8,16,32} x {1e-5..1e-8}
#                                  + thr256 x 1e-8                          = 42
#   exp6 (6_llc_way_sweep)       : sweep_{2MB,4MB,8MB}_w{1,2,4,6,8,10,12} x {1e-7,1e-8} = 42
#   exp7 (7_no_error_way_sweep)  : noerr_{2MB,4MB}_w{8..16}                 = 18
#                                                                     total = 102
# Usage:
#   MAX_PARALLEL=38 ./run_xsbench_267.sh              # all three experiments
#   MAX_PARALLEL=38 ./run_xsbench_267.sh 2 7          # selected experiments
#   TRACE=... ./run_xsbench_267.sh                    # different workload trace
set -euo pipefail

CHAMPSIM_DIR="$(cd "$(dirname "$0")/../.." && pwd)"
TRACE="${TRACE:-${CHAMPSIM_DIR}/test_traces/xsbench_event_large-18.3B.champsimtrace.xz}"
RESULTS_BASE="${RESULTS_BASE:-${CHAMPSIM_DIR}/results/normal_evaluation}"

WARMUP="${WARMUP:-50000000}"
SIM="${SIM:-250000000}"
MAX_PARALLEL="${MAX_PARALLEL:-4}"

[[ -f "${TRACE}" ]] || { echo "trace not found: ${TRACE}"; exit 1; }
TRACE_TAG="$(basename "${TRACE}" | sed 's/\.champsimtrace\.xz$//' | sed 's/\.champsimtrace\.gz$//' | sed 's/\.champsim\.trace\.gz$//')"
LOG_FILE="${RESULTS_BASE}/run_xsbench_267_${TRACE_TAG}.log"

# ── Binary lists (must already exist in bin/) ──
BINS_2=()
for mode in on off; do
  for thr in 2 4 8 16 32; do
    for rate in 1e-5 1e-6 1e-7 1e-8; do
      BINS_2+=("retire_${mode}_${thr}_${rate}")
    done
  done
  BINS_2+=("retire_${mode}_256_1e-8")
done

BINS_6=()
for size in 2MB 4MB 8MB; do
  for w in 1 2 4 6 8 10 12; do
    for rate in 1e-7 1e-8; do
      BINS_6+=("sweep_${size}_w${w}_${rate}")
    done
  done
done

BINS_7=()
for size in 2MB 4MB; do
  for w in 8 9 10 11 12 13 14 15 16; do
    BINS_7+=("noerr_${size}_w${w}")
  done
done

mkdir -p "${RESULTS_BASE}/2_retirement_threshold" \
         "${RESULTS_BASE}/6_llc_way_sweep" \
         "${RESULTS_BASE}/7_no_error_way_sweep"

log_msg() {
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "${LOG_FILE}"
}

fmt_elapsed() {
  local s=$1
  printf "%d:%02d:%02d" $((s / 3600)) $((s % 3600 / 60)) $((s % 60))
}

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

run_group() {
  local group_dir="$1"; shift
  local -a bins=("$@")
  for binary in "${bins[@]}"; do
    if [[ ! -x "${CHAMPSIM_DIR}/bin/${binary}" ]]; then
      log_msg "SKIP: binary not found: ${binary}"
      continue
    fi
    local out="${RESULTS_BASE}/${group_dir}/${binary}_${TRACE_TAG}.txt"
    if [[ -f "${out}" ]] && grep -q "Simulation complete" "${out}" 2>/dev/null; then
      log_msg "SKIP (done): ${binary}"
      continue
    fi
    wait_for_slot
    total=$((total + 1))
    log_msg "START [${total}]: ${group_dir}/${binary} x ${TRACE_TAG}"
    (
      t0=$(date +%s)
      ec=0
      "${CHAMPSIM_DIR}/bin/${binary}" \
        --warmup-instructions "${WARMUP}" \
        --simulation-instructions "${SIM}" \
        "${TRACE}" > "${out}" 2>&1 || ec=$?
      t1=$(date +%s); elapsed=$((t1 - t0))
      if [[ ${ec} -eq 0 ]] && grep -q "Simulation complete" "${out}" 2>/dev/null; then
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] DONE : ${binary} elapsed=${elapsed}s ($(fmt_elapsed ${elapsed}))" >> "${LOG_FILE}"
      else
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] FAIL : ${binary} elapsed=${elapsed}s ($(fmt_elapsed ${elapsed})) exit=${ec}" >> "${LOG_FILE}"
      fi
    ) &
    PIDS+=($!)
  done
}

# Selected experiments (default: all)
if [[ $# -gt 0 ]]; then SELECTED=("$@"); else SELECTED=(2 6 7); fi

log_msg "=== XSBench 2/6/7 | trace=${TRACE_TAG} warmup=${WARMUP} sim=${SIM} parallel=${MAX_PARALLEL} ==="

PIDS=()
total=0
for exp in "${SELECTED[@]}"; do
  case "${exp}" in
    2) run_group "2_retirement_threshold" "${BINS_2[@]}" ;;
    6) run_group "6_llc_way_sweep" "${BINS_6[@]}" ;;
    7) run_group "7_no_error_way_sweep" "${BINS_7[@]}" ;;
    *) log_msg "SKIP: unknown experiment '${exp}'" ;;
  esac
done

wait
log_msg "=== All runs finished (${total} started) ==="
