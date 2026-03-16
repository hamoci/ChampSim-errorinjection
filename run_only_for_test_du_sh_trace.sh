#!/bin/bash
set -euo pipefail

cd /home/hamoci/Study/ChampSim

TRACE="./test_traces/du_sh_trace.chamsim"
TRACE_TAG="$(basename "${TRACE}")"
RESULT_DIR="./results/only_for_test_${TRACE_TAG}"
mkdir -p "${RESULT_DIR}"

configs=(
  "./sim_configs/only_for_test/_2MBLLC_2MBPage_DRAM_Error_1e-8_psc_thrash.json"
  #"./sim_configs/only_for_test/_2MBLLC_4KBPage_DRAM_Error_1e-8_psc_thrash.json"
)

if [[ ! -f "${TRACE}" ]]; then
  echo "Trace not found: ${TRACE}"
  exit 1
fi

declare -a binaries=()
for config in "${configs[@]}"; do
  if [[ ! -f "${config}" ]]; then
    echo "Config not found: ${config}"
    exit 1
  fi
  binary=$(sed -n 's/^[[:space:]]*"executable_name":[[:space:]]*"\([^"]*\)".*/\1/p' "${config}" | head -n1)
  if [[ -z "${binary}" ]]; then
    echo "Failed to parse executable_name from: ${config}"
    exit 1
  fi
  binaries+=("${binary}")
done

for binary in "${binaries[@]}"; do
  if [[ ! -x "./bin/${binary}" ]]; then
    echo "Binary not found or not executable: ./bin/${binary}"
    echo "Build first with ./build_only_for_test.sh"
    exit 1
  fi
done

echo "Running ${#binaries[@]} binaries with trace: ${TRACE}"

MAX_PARALLEL=4
running_jobs=0

for binary in "${binaries[@]}"; do
  output_file="${RESULT_DIR}/${binary}_${TRACE_TAG}.txt"
  while [[ ${running_jobs} -ge ${MAX_PARALLEL} ]]; do
    sleep 1
    running_jobs=$(jobs -r | wc -l)
  done

  echo "Running ./bin/${binary} ${TRACE} -> ${output_file}"
  ./bin/"${binary}" "${TRACE}" > "${output_file}" 2>&1 &
  running_jobs=$((running_jobs + 1))
done

wait

echo "All runs complete."
