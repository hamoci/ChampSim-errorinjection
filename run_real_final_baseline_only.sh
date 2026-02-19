#!/bin/bash
set -euo pipefail

cd /home/hamoci/Study/ChampSim

MAX_PARALLEL="${MAX_PARALLEL:-4}"
BASELINE_RESULT_DIR="./results/real_final_spec/baseline"

configs=(
  "./sim_configs/real_final/no_error_hugepage/_2MBLLC_4KBPage_DRAM.json"
  "./sim_configs/real_final/no_error_hugepage/_2MBLLC_2MBPage_DRAM.json"
)

for cfg in "${configs[@]}"; do
  if [[ ! -f "${cfg}" ]]; then
    echo "Missing baseline config: ${cfg}"
    exit 1
  fi
done

mapfile -t traces < <(find ./test_traces -maxdepth 1 -type f -name '6*.champsimtrace.xz' | sort)
if [[ ${#traces[@]} -eq 0 ]]; then
  echo "No SPEC traces found under ./test_traces (pattern: 6*.champsimtrace.xz)"
  exit 1
fi

mkdir -p "${BASELINE_RESULT_DIR}"
start_epoch=$(date +%s)

# Resolve executable names from config files
declare -a binaries=()
for cfg in "${configs[@]}"; do
  exe_name=$(jq -r '.executable_name // empty' "${cfg}")
  if [[ -z "${exe_name}" ]]; then
    echo "Failed to parse executable_name: ${cfg}"
    exit 1
  fi
  binaries+=("${exe_name}")
done

echo "Running baseline simulations..."
echo "Simulation start: $(date)"
echo "Baseline binaries: ${#binaries[@]}"
echo "SPEC traces: ${#traces[@]}"
echo "Total runs: $((${#binaries[@]} * ${#traces[@]}))"
echo "Max parallel jobs: ${MAX_PARALLEL}"
echo "================================"

running_jobs=0
wait_for_job_slot() {
  while [[ ${running_jobs} -ge ${MAX_PARALLEL} ]]; do
    sleep 1
    running_jobs=$(jobs -r | wc -l)
  done
}

for binary in "${binaries[@]}"; do
  if [[ ! -x "./bin/${binary}" ]]; then
    echo "Binary not found or not executable: ./bin/${binary}"
    echo "Build first with: ./build_real_final_baseline_only.sh"
    exit 1
  fi

  for trace in "${traces[@]}"; do
    trace_file=$(basename "${trace}")
    trace_name=$(basename "${trace}" .champsimtrace.xz)
    output_file="${BASELINE_RESULT_DIR}/${binary}_${trace_name}.txt"

    wait_for_job_slot

    echo "Running: ./bin/${binary} ${trace_file} -> ${output_file}"
    nohup ./bin/"${binary}" "${trace}" > "${output_file}" 2>&1 &
    running_jobs=$((running_jobs + 1))
  done
done

echo "All baseline runs started. Waiting for completion..."
wait

echo "================================"
end_epoch=$(date +%s)
elapsed_sec=$((end_epoch - start_epoch))
elapsed_h=$((elapsed_sec / 3600))
elapsed_m=$(((elapsed_sec % 3600) / 60))
elapsed_s=$((elapsed_sec % 60))

echo "All baseline runs complete: $(date)"
echo "Total elapsed time: ${elapsed_h}h ${elapsed_m}m ${elapsed_s}s (${elapsed_sec}s)"
echo "Results in ${BASELINE_RESULT_DIR}"
