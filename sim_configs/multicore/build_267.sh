#!/bin/bash
# Build all Exp 2'/6'/7' binaries (one config.sh+make per JSON — configs merge otherwise!)
set -euo pipefail
CHAMPSIM_DIR="$(cd "$(dirname "$0")/../.." && pwd)"
JOBS="${JOBS:-36}"
cd "${CHAMPSIM_DIR}"
for f in sim_configs/multicore/2_retirement_threshold/*.json \
         sim_configs/multicore/6_llc_way_sweep/*.json \
         sim_configs/multicore/7_no_error_way_sweep/*.json; do
  echo "=== ${f}"
  ./config.sh "${f}" > /dev/null
  make -j"${JOBS}" 2>&1 | tail -1 | grep -o "bin/[a-z_0-9-]*" || true
done
echo "=== build_267 done"
