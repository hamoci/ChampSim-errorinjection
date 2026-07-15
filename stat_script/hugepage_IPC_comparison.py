#!/usr/bin/env python3
"""
4KB Page vs 2MB Page IPC Comparison Script
Extracts IPC data from ChampSim simulation results and generates comparison graphs.
- CSV: IPC values
- PNG: Speedup graph (4KB Page as baseline)
"""

import os
import re
import glob
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from scipy.stats import gmean

# Paths (relative to script location)
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
BASE_DIR = os.path.dirname(SCRIPT_DIR)
BASELINE_DIR = os.path.join(BASE_DIR, "results/no_error_baseline")
OUTPUT_DIR = SCRIPT_DIR

def extract_ipc(filepath):
    """Extract cumulative IPC from ChampSim result file."""
    with open(filepath, 'r') as f:
        content = f.read()

    # Find "CPU 0 cumulative IPC: X.XXXX" in Region of Interest Statistics
    match = re.search(r'CPU 0 cumulative IPC:\s+([\d.]+)', content)
    if match:
        return float(match.group(1))
    return None

def extract_workload_name(filename, suite):
    """Extract workload name from filename."""
    # Remove prefix and suffix
    # e.g., "champsim_4kb_32gb_602.gcc_s-1850B.txt" -> "602.gcc_s"
    # e.g., "champsim_4kb_32gb_bc-12.trace.gz.txt" -> "bc-12"

    name = filename.replace("champsim_4kb_32gb_", "").replace("champsim_2mb_32gb_", "")

    if suite == "spec":
        # Remove ".txt" and extract benchmark name
        name = name.replace(".txt", "")
        # Extract benchmark name (e.g., "602.gcc_s-1850B" -> "gcc_s")
        match = re.match(r'(\d+)\.(\w+)-\w+', name)
        if match:
            return f"{match.group(1)}.{match.group(2)}"
    elif suite == "gap":
        # Remove ".trace.gz.txt"
        name = name.replace(".trace.gz.txt", "")
        return name

    return name

def collect_data(suite):
    """Collect IPC data for a benchmark suite."""
    suite_dir = os.path.join(BASELINE_DIR, suite)

    data = {}

    # Get all 4kb files
    files_4kb = glob.glob(os.path.join(suite_dir, "champsim_4kb_32gb_*"))

    for f4kb in files_4kb:
        filename = os.path.basename(f4kb)
        workload = extract_workload_name(filename, suite)

        # Find corresponding 2mb file
        f2mb = f4kb.replace("_4kb_", "_2mb_")

        if os.path.exists(f2mb):
            ipc_4kb = extract_ipc(f4kb)
            ipc_2mb = extract_ipc(f2mb)

            if ipc_4kb and ipc_2mb:
                data[workload] = {
                    '4KB': ipc_4kb,
                    '2MB': ipc_2mb
                }

    return data

def main():
    # Collect data for SPEC and GAP
    spec_data = collect_data("spec")
    gap_data = collect_data("gap")

    print(f"Collected {len(spec_data)} SPEC workloads")
    print(f"Collected {len(gap_data)} GAP workloads")

    # Sort workloads
    spec_workloads = sorted(spec_data.keys())
    gap_workloads = sorted(gap_data.keys())

    # Prepare data for CSV and plotting
    all_workloads = []
    ipc_4kb_list = []
    ipc_2mb_list = []
    categories = []

    # Add SPEC workloads
    for w in spec_workloads:
        all_workloads.append(w)
        ipc_4kb_list.append(spec_data[w]['4KB'])
        ipc_2mb_list.append(spec_data[w]['2MB'])
        categories.append('SPEC')

    # Add GAP workloads
    for w in gap_workloads:
        all_workloads.append(w)
        ipc_4kb_list.append(gap_data[w]['4KB'])
        ipc_2mb_list.append(gap_data[w]['2MB'])
        categories.append('GAP')

    # Calculate GMEANs
    spec_4kb_values = [spec_data[w]['4KB'] for w in spec_workloads]
    spec_2mb_values = [spec_data[w]['2MB'] for w in spec_workloads]
    gap_4kb_values = [gap_data[w]['4KB'] for w in gap_workloads]
    gap_2mb_values = [gap_data[w]['2MB'] for w in gap_workloads]

    spec_gmean_4kb = gmean(spec_4kb_values) if spec_4kb_values else 0
    spec_gmean_2mb = gmean(spec_2mb_values) if spec_2mb_values else 0
    gap_gmean_4kb = gmean(gap_4kb_values) if gap_4kb_values else 0
    gap_gmean_2mb = gmean(gap_2mb_values) if gap_2mb_values else 0
    total_gmean_4kb = gmean(ipc_4kb_list) if ipc_4kb_list else 0
    total_gmean_2mb = gmean(ipc_2mb_list) if ipc_2mb_list else 0

    # Add GMEANs to lists
    all_workloads.extend(['SPEC\nGMEAN', 'GAP\nGMEAN', 'Total\nGMEAN'])
    ipc_4kb_list.extend([spec_gmean_4kb, gap_gmean_4kb, total_gmean_4kb])
    ipc_2mb_list.extend([spec_gmean_2mb, gap_gmean_2mb, total_gmean_2mb])
    categories.extend(['GMEAN', 'GMEAN', 'GMEAN'])

    # Create DataFrame for CSV (IPC values)
    df = pd.DataFrame({
        'Workload': all_workloads,
        '4KB_IPC': ipc_4kb_list,
        '2MB_IPC': ipc_2mb_list,
        'Category': categories
    })

    # Save to CSV
    csv_path = os.path.join(OUTPUT_DIR, "hugepage_IPC_comparison.csv")
    df.to_csv(csv_path, index=False)
    print(f"CSV saved to: {csv_path}")

    # Calculate Speedup percentage for text labels
    speedup_pct = [(ipc_2mb_list[i] / ipc_4kb_list[i] - 1) * 100 for i in range(len(ipc_4kb_list))]

    # Create compact plot for paper
    fig, ax = plt.subplots(figsize=(10, 2.5))

    x = np.arange(len(all_workloads))
    width = 0.38

    # Color scheme (matching parse_cache_size_analysis.py)
    color_4kb = '#EE5A6F'  # Red/Pink
    color_2mb = '#4A90E2'  # Blue

    # Draw bars
    bars1 = ax.bar(x - width/2, ipc_4kb_list, width, label='4KB Page', color=color_4kb, edgecolor='black', linewidth=0.3)
    bars2 = ax.bar(x + width/2, ipc_2mb_list, width, label='2MB Page', color=color_2mb, edgecolor='black', linewidth=0.3)

    # Add Speedup % text above each pair of bars
    for i in range(len(all_workloads)):
        max_height = max(ipc_4kb_list[i], ipc_2mb_list[i])
        pct = speedup_pct[i]
        sign = '+' if pct >= 0 else ''
        ax.text(x[i], max_height + 0.02, f'{sign}{pct:.0f}%', ha='center', va='bottom', fontsize=5, fontweight='bold', color='#333333')

    # Customize plot
    #ax.set_xlabel('Workload', fontsize=8)
    ax.set_ylabel('IPC', fontsize=8)
    ax.set_xticks(x)
    ax.set_xticklabels(all_workloads, rotation=45, ha='right', fontsize=5)
    ax.tick_params(axis='y', labelsize=6)
    ax.legend(loc='upper right', fontsize=6, framealpha=0.9)

    # Add grid
    ax.yaxis.grid(True, linestyle='--', alpha=0.5, linewidth=0.5)
    ax.set_axisbelow(True)

    # Adjust y-axis to make room for text labels
    y_max = max(max(ipc_4kb_list), max(ipc_2mb_list))
    ax.set_ylim(0, y_max * 1.18)

    # Reduce left/right margins
    ax.set_xlim(-0.6, len(all_workloads) - 0.4)
    ax.margins(x=0.01)

    # Highlight GMEAN bars with different edge
    for i in range(-3, 0):
        bars1[i].set_edgecolor('black')
        bars1[i].set_linewidth(1.5)
        bars2[i].set_edgecolor('black')
        bars2[i].set_linewidth(1.5)

    plt.tight_layout(pad=0.3)

    # Save plot
    png_path = os.path.join(OUTPUT_DIR, "hugepage_IPC_comparison.png")
    plt.savefig(png_path, dpi=300, bbox_inches='tight', facecolor='white', edgecolor='none')
    print(f"PNG saved to: {png_path}")

    plt.close()

    # Print summary
    print("\n=== Summary ===")
    print(f"SPEC GMEAN - 4KB: {spec_gmean_4kb:.4f}, 2MB: {spec_gmean_2mb:.4f}, Speedup: {spec_gmean_2mb/spec_gmean_4kb:.4f}")
    print(f"GAP GMEAN  - 4KB: {gap_gmean_4kb:.4f}, 2MB: {gap_gmean_2mb:.4f}, Speedup: {gap_gmean_2mb/gap_gmean_4kb:.4f}")
    print(f"Total GMEAN - 4KB: {total_gmean_4kb:.4f}, 2MB: {total_gmean_2mb:.4f}, Speedup: {total_gmean_2mb/total_gmean_4kb:.4f}")

if __name__ == "__main__":
    main()
