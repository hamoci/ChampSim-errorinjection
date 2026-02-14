#!/bin/bash
set -euo pipefail

cd /home/hamoci/Study/ChampSim

RESULT_DIR="./results/real_final_spec"
MAX_PARALLEL="${MAX_PARALLEL:-4}"

mkdir -p "${RESULT_DIR}"
start_epoch=$(date +%s)

# SPEC trace 목록 (6*.champsimtrace.xz)
mapfile -t traces < <(find ./test_traces -maxdepth 1 -type f -name '6*.champsimtrace.xz' | sort)
if [[ ${#traces[@]} -eq 0 ]]; then
  echo "No SPEC traces found under ./test_traces (pattern: 6*.champsimtrace.xz)"
  exit 1
fi

# real_final config 전체 수집
mapfile -t all_configs < <(find ./sim_configs/real_final -type f -name '*.json' | sort)
if [[ ${#all_configs[@]} -eq 0 ]]; then
  echo "No configs found under ./sim_configs/real_final"
  exit 1
fi

# 조건에 맞게 config 필터링
selected_configs=()
for cfg in "${all_configs[@]}"; do
  # Rule 1: 4KB/2MB 모두 no_cache_pinning 에서는 1e-9 제외
  if [[ "${cfg}" == *"/no_cache_pinning/"* && "${cfg}" == *"_Error_1e-9.json" ]]; then
    continue
  fi

  # Rule 2: 2MB + no_cache_pinning 에서는 1e-8 제외
  if [[ "${cfg}" == *"/no_cache_pinning/"* && "${cfg}" == *"2MBPage"* && "${cfg}" == *"_Error_1e-8.json" ]]; then
    continue
  fi

  selected_configs+=("${cfg}")
done

if [[ ${#selected_configs[@]} -eq 0 ]]; then
  echo "No configs selected after filtering rules"
  exit 1
fi

# 필터된 config -> 바이너리 목록 생성 (중복 제거)
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

# 바이너리 존재 확인
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
echo "Selected configs: ${#selected_configs[@]} / ${#all_configs[@]}"
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

echo "All real_final SPEC runs complete: $(date)"
echo "Total elapsed time: ${elapsed_h}h ${elapsed_m}m ${elapsed_s}s (${elapsed_sec}s)"
echo "Result files in ${RESULT_DIR}"
