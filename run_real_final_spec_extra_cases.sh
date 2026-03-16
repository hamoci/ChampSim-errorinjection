#!/bin/bash
set -euo pipefail

cd /home/hamoci/Study/ChampSim

RESULT_DIR="./results/real_final_spec_extra_cases"
MAX_PARALLEL="${MAX_PARALLEL:-4}"

mkdir -p "${RESULT_DIR}"
start_epoch=$(date +%s)

# SPEC traces only
mapfile -t traces < <(find ./test_traces -maxdepth 1 -type f -name '6*.champsimtrace.xz' | sort)
if [[ ${#traces[@]} -eq 0 ]]; then
  echo "No SPEC traces found under ./test_traces (pattern: 6*.champsimtrace.xz)"
  exit 1
fi

# Only the two previously-excluded cases
mapfile -t selected_configs < <(
  find ./sim_configs/real_final/error_hugepage -type f -name '*.json' | sort | \
  grep '/no_cache_pinning/' | \
  grep -E '(4KBPage.*_Error_1e-9\.json|2MBPage.*_Error_1e-8\.json)'
)

if [[ ${#selected_configs[@]} -eq 0 ]]; then
  echo "No matching configs for extra cases"
  exit 1
fi

declare -A seen_binaries=()
declare -a binaries=()
for cfg in "${selected_configs[@]}"; do
  exe_name=$(jq -r '.executable_name // empty' "${cfg}")
  if [[ -z "${exe_name}" ]]; then
    echo "Failed to parse executable_name from: ${cfg}"
    exit 1
  fi

  if [[ -z "${seen_binaries[${exe_name}]+x}" ]]; then
    seen_binaries["${exe_name}"]=1
    binaries+=("${exe_name}")
  fi
done

for binary in "${binaries[@]}"; do
  if [[ ! -x "./bin/${binary}" ]]; then
    echo "Binary not found or not executable: ./bin/${binary}"
    echo "Build first with ./build_real_final.sh"
    exit 1
  fi
done

running_jobs=0
wait_for_job_slot() {
  while [[ ${running_jobs} -ge ${MAX_PARALLEL} ]]; do
    sleep 1
    running_jobs=$(jobs -r | wc -l)
  done
}

echo "Simulation start: $(date)"
echo "Selected configs: ${#selected_configs[@]}"
echo "Unique binaries: ${#binaries[@]}"
echo "SPEC traces: ${#traces[@]}"
echo "Total runs: $((${#binaries[@]} * ${#traces[@]}))"
echo "Max parallel jobs: ${MAX_PARALLEL}"
echo "================================"

for binary in "${binaries[@]}"; do
  for trace in "${traces[@]}"; do
    trace_file=$(basename "${trace}")
    trace_name=$(basename "${trace}" .champsimtrace.xz)
    output_file="${RESULT_DIR}/${binary}_${trace_name}.txt"

    wait_for_job_slot

    echo "Running: ./bin/${binary} ${trace_file} -> ${output_file}"
    nohup ./bin/"${binary}" "${trace}" > "${output_file}" 2>&1 &
    running_jobs=$((running_jobs + 1))
  done
done

echo "All simulations started. Waiting for completion..."
wait

echo "================================"
end_epoch=$(date +%s)
elapsed_sec=$((end_epoch - start_epoch))
elapsed_h=$((elapsed_sec / 3600))
elapsed_m=$(((elapsed_sec % 3600) / 60))
elapsed_s=$((elapsed_sec % 60))

echo "All extra-case SPEC runs complete: $(date)"
echo "Total elapsed time: ${elapsed_h}h ${elapsed_m}m ${elapsed_s}s (${elapsed_sec}s)"
echo "Result files in ${RESULT_DIR}"
