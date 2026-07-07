#!/usr/bin/env python3
"""Compare IPC between 500M instruction runs (ett_evaluation) and 2B instruction runs (real_final_spec baseline)."""

import matplotlib.pyplot as plt
import numpy as np

# Benchmark order (same for both)
benchmarks = [
    "602.gcc_s",
    "603.bwaves_s",
    "605.mcf_s",
    "607.cactuBSSN_s",
    "620.omnetpp_s",
    "621.wrf_s",
    "623.xalancbmk_s",
    "628.pop2_s",
    "649.fotonik3d_s",
    "654.roms_s",
]

# IPC values extracted from simulation output (matched by file order)
ipc_500M = [0.2248, 0.8764, 0.4122, 1.147, 0.4801, 0.6577, 1.328, 1.426, 0.4815, 0.747]
ipc_2B   = [0.2281, 0.8705, 0.3481, 1.157, 0.4816, 0.9628, 1.346, 1.385, 0.4998, 0.9033]

# Calculate percentage difference: (2B - 500M) / 500M * 100
pct_diff = [(b - a) / a * 100 for a, b in zip(ipc_500M, ipc_2B)]

fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(14, 9), gridspec_kw={'height_ratios': [3, 1.2]})

x = np.arange(len(benchmarks))
width = 0.35

bars1 = ax1.bar(x - width/2, ipc_500M, width, label='500M instructions', color='#4C72B0', edgecolor='black', linewidth=0.5)
bars2 = ax1.bar(x + width/2, ipc_2B, width, label='2B instructions', color='#DD8452', edgecolor='black', linewidth=0.5)

# Add value labels on bars
for bar in bars1:
    h = bar.get_height()
    ax1.text(bar.get_x() + bar.get_width()/2., h + 0.01, f'{h:.3f}', ha='center', va='bottom', fontsize=7.5)
for bar in bars2:
    h = bar.get_height()
    ax1.text(bar.get_x() + bar.get_width()/2., h + 0.01, f'{h:.3f}', ha='center', va='bottom', fontsize=7.5)

ax1.set_ylabel('IPC', fontsize=12)
ax1.set_title('IPC Comparison: 500M vs 2B Instructions (2MB Page, Baseline)', fontsize=13)
ax1.set_xticks(x)
ax1.set_xticklabels(benchmarks, rotation=30, ha='right', fontsize=10)
ax1.legend(fontsize=11)
ax1.set_ylim(0, max(max(ipc_500M), max(ipc_2B)) * 1.15)
ax1.grid(axis='y', alpha=0.3)

# Bottom plot: percentage difference
colors = ['#2ca02c' if d >= 0 else '#d62728' for d in pct_diff]
bars3 = ax2.bar(x, pct_diff, 0.5, color=colors, edgecolor='black', linewidth=0.5)
for bar, d in zip(bars3, pct_diff):
    h = bar.get_height()
    va = 'bottom' if h >= 0 else 'top'
    ax2.text(bar.get_x() + bar.get_width()/2., h, f'{d:+.1f}%', ha='center', va=va, fontsize=8.5, fontweight='bold')

ax2.set_ylabel('IPC Difference (%)', fontsize=11)
ax2.set_title('Relative IPC Difference: (2B − 500M) / 500M × 100', fontsize=11)
ax2.set_xticks(x)
ax2.set_xticklabels(benchmarks, rotation=30, ha='right', fontsize=10)
ax2.axhline(y=0, color='black', linewidth=0.8)
ax2.grid(axis='y', alpha=0.3)

plt.tight_layout()
plt.savefig('/home/hamoci/Study/ChampSim/stat_script_rev/compare_ipc_500M_vs_2B.png', dpi=200, bbox_inches='tight')
plt.savefig('/home/hamoci/Study/ChampSim/stat_script_rev/compare_ipc_500M_vs_2B.pdf', bbox_inches='tight')
print("Saved to stat_script_rev/compare_ipc_500M_vs_2B.png and .pdf")

# Print summary
print("\n=== IPC Summary ===")
print(f"{'Benchmark':<22} {'500M':>8} {'2B':>8} {'Diff%':>8}")
print("-" * 50)
for i, b in enumerate(benchmarks):
    print(f"{b:<22} {ipc_500M[i]:>8.4f} {ipc_2B[i]:>8.4f} {pct_diff[i]:>+7.1f}%")
print("-" * 50)
avg_abs_diff = np.mean(np.abs(pct_diff))
print(f"{'Average |diff|':<22} {'':>8} {'':>8} {avg_abs_diff:>7.1f}%")
