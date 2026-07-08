#!/bin/bash
# Track A: 4-core SPEC mix experiment
#   10 mixes x 5 binaries (noerr, off/pin x 1e-6/1e-7) = 50 runs
#
# Mix composition (SPEC CPU 2017 only, 2MB-page RBMPKI ranking from
# stat_script_rev/baseline_workloads_rbmpki_ipc.csv):
#   memory-intensive pool (High RBMPKI): mcf(21.4) fotonik3d(21.0) gcc(17.8) bwaves(16.3) omnetpp(13.3)
#   cpu-intensive pool (Mid/Low RBMPKI): cactuBSSN(8.1) wrf(6.1) roms(5.0) pop2(4.5) xalancbmk(2.8)
#   M1-M4 / C1-C4: leave-one-out rotations of each 5-workload pool
#   H1-H2: 2 mem + 2 cpu hybrids
#
# Usage:
#   MAX_PARALLEL=4 ./run_mixes.sh           # all runs
#   MAX_PARALLEL=4 ./run_mixes.sh M1 C2 H1  # selected mixes only
#   WARMUP/SIM env-overridable (default 50M/250M per core, per paper outline)
set -euo pipefail

CHAMPSIM_DIR="$(cd "$(dirname "$0")/../.." && pwd)"
TRACE_DIR="${TRACE_DIR:-${CHAMPSIM_DIR}/test_traces}"
RESULT_DIR="${RESULT_DIR:-${CHAMPSIM_DIR}/results/multicore/1_headline}"
LOG_FILE="${RESULT_DIR}/run_mixes.log"

WARMUP="${WARMUP:-50000000}"
SIM="${SIM:-250000000}"
MAX_PARALLEL="${MAX_PARALLEL:-4}"

BINARIES=(
  champsim_4core_8mb_noerr
  champsim_4core_8mb_off_1e-6
  champsim_4core_8mb_off_1e-7
  champsim_4core_8mb_pin_1e-6
  champsim_4core_8mb_pin_1e-7
)

# SPEC trace filenames
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
)

# mix name -> 4 workloads (assigned to CPU0..CPU3 in order)
declare -A MIXES=(
  # memory-intensive: leave-one-out of {mcf fotonik3d gcc bwaves omnetpp}
  [M1]="mcf fotonik3d gcc bwaves"       # -omnetpp
  [M2]="mcf fotonik3d gcc omnetpp"      # -bwaves
  [M3]="mcf fotonik3d bwaves omnetpp"   # -gcc
  [M4]="mcf gcc bwaves omnetpp"         # -fotonik3d
  # cpu-intensive: leave-one-out of {cactuBSSN wrf roms pop2 xalancbmk}
  [C1]="xalancbmk pop2 roms wrf"        # -cactuBSSN
  [C2]="xalancbmk pop2 roms cactuBSSN"  # -wrf
  [C3]="xalancbmk pop2 wrf cactuBSSN"   # -roms
  [C4]="xalancbmk roms wrf cactuBSSN"   # -pop2
  # hybrid: 2 mem + 2 cpu
  [H1]="mcf fotonik3d xalancbmk pop2"
  [H2]="gcc omnetpp wrf roms"
)
MIX_ORDER=(M1 M2 M3 M4 C1 C2 C3 C4 H1 H2)

mkdir -p "${RESULT_DIR}"

log_msg() {
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "${LOG_FILE}"
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

# Selected mixes (default: all)
if [[ $# -gt 0 ]]; then
  SELECTED=("$@")
else
  SELECTED=("${MIX_ORDER[@]}")
fi

log_msg "=== Track A: 4-core SPEC mixes | warmup=${WARMUP} sim=${SIM} parallel=${MAX_PARALLEL} ==="

PIDS=()
total=0
for mix in "${SELECTED[@]}"; do
  if [[ -z "${MIXES[$mix]:-}" ]]; then
    log_msg "SKIP: unknown mix '${mix}'"
    continue
  fi

  # Resolve trace paths for this mix
  traces=()
  for w in ${MIXES[$mix]}; do
    tp="${TRACE_DIR}/${T[$w]}"
    if [[ ! -f "${tp}" ]]; then
      log_msg "ERROR: trace not found: ${tp} (mix ${mix})"
      continue 2
    fi
    traces+=("${tp}")
  done

  for binary in "${BINARIES[@]}"; do
    if [[ ! -x "${CHAMPSIM_DIR}/bin/${binary}" ]]; then
      log_msg "SKIP: binary not found: ${binary}"
      continue
    fi

    out="${RESULT_DIR}/${binary}_${mix}.txt"
    if [[ -f "${out}" ]] && grep -q "Simulation complete" "${out}" 2>/dev/null; then
      log_msg "SKIP (done): ${binary} x ${mix}"
      continue
    fi

    wait_for_slot
    total=$((total + 1))
    log_msg "START [${total}]: ${binary} x ${mix} (${MIXES[$mix]})"

    (
      "${CHAMPSIM_DIR}/bin/${binary}" \
        --warmup-instructions "${WARMUP}" \
        --simulation-instructions "${SIM}" \
        "${traces[@]}" > "${out}" 2>&1
      ec=$?
      if [[ ${ec} -eq 0 ]] && grep -q "Simulation complete" "${out}" 2>/dev/null; then
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] DONE : ${binary} x ${mix}" >> "${LOG_FILE}"
      else
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] FAIL : ${binary} x ${mix} (exit=${ec})" >> "${LOG_FILE}"
      fi
    ) &
    PIDS+=($!)
  done
done

wait
log_msg "=== All runs finished (${total} started) ==="
