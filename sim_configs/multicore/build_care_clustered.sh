#!/bin/bash
# Build CARE-clustered Exp1 binaries + the noerr baseline (7 configs).
# One config.sh+make per JSON — passing multiple JSONs to config.sh MERGES them!
set -euo pipefail
CHAMPSIM_DIR="$(cd "$(dirname "$0")/../.." && pwd)"
JOBS="${JOBS:-36}"
cd "${CHAMPSIM_DIR}"
for f in sim_configs/multicore/care_clustered/*.json \
         sim_configs/multicore/no_error/*.json; do
  echo "=== ${f}"
  ./config.sh "${f}" > /dev/null
  make -j"${JOBS}" 2>&1 | tail -1 | grep -o "bin/[a-z_0-9-]*" || true
done
echo "=== build_care_clustered done"
