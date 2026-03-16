#!/bin/bash
set -euo pipefail

cd /home/hamoci/Study/ChampSim

SRC_DIR="./results/0219_finished/real_final_spec"
DRY_RUN="${DRY_RUN:-0}"

if [[ ! -d "${SRC_DIR}" ]]; then
  echo "Source directory not found: ${SRC_DIR}"
  exit 1
fi

move_count=0
skip_count=0

classify_target() {
  local name="$1"

  # Baseline (no error)
  if [[ "$name" == champsim_2mb_32gb_* || "$name" == champsim_4kb_32gb_* ]]; then
    echo "baseline"
    return
  fi

  # LLC size bucket
  local llc_dir=""
  if [[ "$name" == champsim_4mb_* ]]; then
    llc_dir="llc_4mb"
  elif [[ "$name" == champsim_8mb_* ]]; then
    llc_dir="llc_8mb"
  else
    # default to 2MB LLC naming (champsim_2mb_error_... / champsim_4kb_error_...)
    llc_dir="llc_2mb"
  fi

  local pin_dir="no_cache_pinning"
  if [[ "$name" == *"_cache_pinning_"* ]]; then
    pin_dir="cache_pinning"
  fi

  echo "${llc_dir}/${pin_dir}"
}

while IFS= read -r -d '' f; do
  base="$(basename "$f")"
  target_rel="$(classify_target "$base")"
  target_dir="${SRC_DIR}/${target_rel}"
  target_path="${target_dir}/${base}"

  # already organized file safeguard
  if [[ "$f" == "$target_path" ]]; then
    ((skip_count+=1))
    continue
  fi

  mkdir -p "$target_dir"

  if [[ -e "$target_path" ]]; then
    echo "[SKIP] exists: $target_path"
    ((skip_count+=1))
    continue
  fi

  if [[ "$DRY_RUN" == "1" ]]; then
    echo "[DRY] $base -> $target_rel/"
  else
    mv "$f" "$target_path"
    echo "[MOVE] $base -> $target_rel/"
  fi
  ((move_count+=1))

done < <(find "$SRC_DIR" -maxdepth 1 -type f -name '*.txt' -print0)

if [[ "$DRY_RUN" == "1" ]]; then
  echo "Dry run complete. candidates=$move_count skipped=$skip_count"
else
  echo "Organize complete. moved=$move_count skipped=$skip_count"
fi
