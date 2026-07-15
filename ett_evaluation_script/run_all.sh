#!/bin/bash
set -e
cd "$(dirname "$0")"

echo "=== Fig 1: Motivation ==="
python3 1_motivation_normalized_ipc.py

echo ""
echo "=== Fig 2: BER Sweep ==="
python3 2_ber_sweep_scalability.py

echo ""
echo "=== Fig 3: Pinning Mechanism ==="
python3 3_pinning_mechanism.py

echo ""
echo "=== Fig 4: Retirement Threshold ==="
python3 4_retire_threshold_sensitivity.py

echo ""
echo "=== Fig 5: ETT Entry Sensitivity ==="
python3 5_ett_entry_sensitivity.py

echo ""
echo "=== Done ==="
