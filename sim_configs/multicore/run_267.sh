#!/bin/bash
# Multicore Exp 2'/6'/7' runner (clustered injection, see generate_configs_267.py).
#
# Usage:
#   FAMILY=main MAX_PARALLEL=38 ./run_267.sh all          # this machine: SPEC(M1/C1/H1) + real-world
#   FAMILY=gap  MAX_PARALLEL=38 ./run_267.sh all          # other machine: GAP homogeneous mixes
#   ./run_267.sh 2                                        # single experiment (2|6|7|all)
#   ./run_267.sh 6 M1 XS                                  # experiment + selected mixes
#   Env: WARMUP/SIM (50M/250M), RUN_TIMEOUT (e.g. 36h), TRACE_DIR, MAX_PARALLEL(38)
#
# Mixes
#   main: M1/C1/H1 (SPEC representative, plan A-2) +
#         LL/RA/RC/XS (real-world homogeneous 4-copy: llama2, redis-ycsba,
#         redis-ycsbc, xsbench — rate-mode multiprogramming)
#   gap : G_BC/G_BFS/G_CC/G_PR/G_SSSP (homogeneous 4-copy, one per GAP app)
set -euo pipefail

CHAMPSIM_DIR="$(cd "$(dirname "$0")/../.." && pwd)"
TRACE_DIR="${TRACE_DIR:-${CHAMPSIM_DIR}/test_traces}"
WARMUP="${WARMUP:-50000000}"
SIM="${SIM:-250000000}"
MAX_PARALLEL="${MAX_PARALLEL:-38}"
RUN_TIMEOUT="${RUN_TIMEOUT:-}"
FAMILY="${FAMILY:-main}"

declare -A T=(
  [gcc]="602.gcc_s-1850B.champsimtrace.xz"
  [bwaves]="603.bwaves_s-2931B.champsimtrace.xz"
  [mcf]="605.mcf_s-994B.champsimtrace.xz"
  [cactuBSSN]="607.cactuBSSN_s-2421B.champsimtrace.xz"
  [omnetpp]="620.omnetpp_s-141B.champsimtrace.xz"
  [wrf]="621.wrf_s-6673B.champsimtrace.xz"
  [xalancbmk]="623.xalancbmk_s-592B.champsimtrace.xz"
  [pop2]="628.pop2_s-17B.champsimtrace.xz"
  [fotonik3d]="649.fotonik3d_s-10881B.champsimtrace.xz"
  [roms]="654.roms_s-1007B.champsimtrace.xz"
  [llama]="llama2.c-llama2_7b.1.champsimtrace.gz"
  [redisa]="redis-8.8.0_ycsba.champsimtrace.xz"
  [redisc]="redis-8.8.0_ycsbc.champsimtrace.xz"
  [xsbench]="xsbench_event_large-18.3B.champsimtrace.xz"
  [bc]="gap/bc-3.trace.gz"
  [bfs]="gap/bfs-3.trace.gz"
  [cc]="gap/cc-5.trace.gz"
  [pr]="gap/pr-3.trace.gz"
  [sssp]="gap/sssp-3.trace.gz"
)

declare -A MIXES=(
  [M1]="mcf fotonik3d gcc bwaves"
  [C1]="xalancbmk pop2 roms wrf"
  [H1]="mcf fotonik3d xalancbmk pop2"
  [LL]="llama llama llama llama"
  [RA]="redisa redisa redisa redisa"
  [RC]="redisc redisc redisc redisc"
  [XS]="xsbench xsbench xsbench xsbench"
  [G_BC]="bc bc bc bc"
  [G_BFS]="bfs bfs bfs bfs"
  [G_CC]="cc cc cc cc"
  [G_PR]="pr pr pr pr"
  [G_SSSP]="sssp sssp sssp sssp"
)
MAIN_ORDER=(M1 C1 H1 LL RA RC XS)
GAP_ORDER=(G_BC G_BFS G_CC G_PR G_SSSP)

EXP2_BINS=(); EXP6_BINS=(); EXP7_BINS=()
for thr in 2 4 8 16 32; do
  EXP2_BINS+=("champsim_4core_8mb_pin_thr${thr}_clu_1e-8" "champsim_4core_8mb_off_thr${thr}_clu_1e-8")
done
for w in 1 2 4 6 8 10 12; do
  for rate in 1e-5 1e-6 1e-7 1e-8; do EXP6_BINS+=("champsim_4core_8mb_pin_mw${w}_clu_${rate}"); done
done
for w in 8 9 10 11 12 13 14 15; do EXP7_BINS+=("champsim_4core_8mb_noerr_w${w}"); done

EXP="${1:-all}"; shift || true
if [[ $# -gt 0 ]]; then SELECTED=("$@");
elif [[ "${FAMILY}" == "gap" ]]; then SELECTED=("${GAP_ORDER[@]}");
else SELECTED=("${MAIN_ORDER[@]}"); fi

PIDS=(); total=0

run_batch() {
  local exp="$1"; shift
  local -a bins=("$@")
  local result_dir="${CHAMPSIM_DIR}/results/multicore/${exp}"
  mkdir -p "${result_dir}"
  local log="${result_dir}/run_267.log"
  for mix in "${SELECTED[@]}"; do
    [[ -n "${MIXES[$mix]:-}" ]] || { echo "SKIP unknown mix ${mix}"; continue; }
    traces=()
    for wname in ${MIXES[$mix]}; do
      tp="${TRACE_DIR}/${T[$wname]}"
      [[ -f "${tp}" ]] || { echo "[$(date '+%F %T')] ERROR trace missing: ${tp}" | tee -a "${log}"; continue 2; }
      traces+=("${tp}")
    done
    for binary in "${bins[@]}"; do
      [[ -x "${CHAMPSIM_DIR}/bin/${binary}" ]] || { echo "[$(date '+%F %T')] SKIP no binary ${binary}" | tee -a "${log}"; continue; }
      out="${result_dir}/${binary}_${mix}.txt"
      if [[ -f "${out}" ]] && grep -q "Simulation complete" "${out}" 2>/dev/null; then
        echo "[$(date '+%F %T')] SKIP (done): ${binary} x ${mix}" | tee -a "${log}"; continue
      fi
      while true; do
        alive=0
        for pid in "${PIDS[@]:-}"; do [[ -n "${pid}" ]] && kill -0 "${pid}" 2>/dev/null && alive=$((alive+1)); done
        [[ ${alive} -lt ${MAX_PARALLEL} ]] && break
        sleep 5
      done
      total=$((total+1))
      echo "[$(date '+%F %T')] START [${total}]: ${binary} x ${mix}" | tee -a "${log}"
      (
        t0=$(date +%s); ec=0
        if [[ -n "${RUN_TIMEOUT}" ]]; then
          timeout "${RUN_TIMEOUT}" "${CHAMPSIM_DIR}/bin/${binary}" \
            --warmup-instructions "${WARMUP}" --simulation-instructions "${SIM}" \
            "${traces[@]}" > "${out}" 2>&1 || ec=$?
        else
          "${CHAMPSIM_DIR}/bin/${binary}" \
            --warmup-instructions "${WARMUP}" --simulation-instructions "${SIM}" \
            "${traces[@]}" > "${out}" 2>&1 || ec=$?
        fi
        t1=$(date +%s); el=$((t1-t0))
        if [[ ${ec} -eq 0 ]] && grep -q "Simulation complete" "${out}" 2>/dev/null; then
          echo "[$(date '+%F %T')] DONE : ${binary} x ${mix} elapsed=${el}s" >> "${log}"
        else
          echo "[$(date '+%F %T')] FAIL : ${binary} x ${mix} elapsed=${el}s exit=${ec}" >> "${log}"
        fi
      ) &
      PIDS+=($!)
    done
  done
}

case "${EXP}" in
  2)   run_batch 2_retirement_threshold "${EXP2_BINS[@]}" ;;
  6)   run_batch 6_llc_way_sweep "${EXP6_BINS[@]}" ;;
  7)   run_batch 7_no_error_way_sweep "${EXP7_BINS[@]}" ;;
  all) run_batch 2_retirement_threshold "${EXP2_BINS[@]}"
       run_batch 6_llc_way_sweep "${EXP6_BINS[@]}"
       run_batch 7_no_error_way_sweep "${EXP7_BINS[@]}" ;;
  *) echo "usage: $0 [2|6|7|all] [mixes...]"; exit 1 ;;
esac

wait
echo "[$(date '+%F %T')] === run_267 finished (${total} started, family=${FAMILY}, exp=${EXP}) ==="
