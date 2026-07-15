#!/usr/bin/env python3
"""
LLC Cache Pinning IPC Comparison Script
Compares IPC across different error rates (1e-6 ~ 1e-9) and page sizes (4KB, 2MB).
- CSV: IPC values
- PNG: Bar graph comparison
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
RESULTS_DIR = os.path.join(BASE_DIR, "results/cache_pinning")
SPEC_DIR = os.path.join(RESULTS_DIR, "spec_pinned/64B_addressing")
GAP_DIR = os.path.join(RESULTS_DIR, "gap_pinned")
OUTPUT_DIR = SCRIPT_DIR

# Error rates to analyze
ERROR_RATES = ['1e-6', '1e-7', '1e-8', '1e-9']
PAGE_SIZES = ['4kb', '2mb']

def extract_ipc(filepath):
    """Extract cumulative IPC from ChampSim result file."""
    try:
        with open(filepath, 'r') as f:
            content = f.read()
        match = re.search(r'CPU 0 cumulative IPC:\s+([\d.]+)', content)
        if match:
            return float(match.group(1))
    except:
        pass
    return None

def extract_workload_name(filename, suite):
    """Extract workload name from filename."""
    # Pattern: champsim_{pagesize}_error_32gb_{errorrate}_cache_pinning_{workload}.txt
    if suite == "spec":
        match = re.search(r'champsim_\w+_error_32gb_[\de-]+_cache_pinning_(\d+\.\w+)', filename)
        if match:
            return match.group(1)
    elif suite == "gap":
        match = re.search(r'champsim_\w+_error_32gb_[\de-]+_cache_pinning_(.+?)\.trace\.gz\.txt', filename)
        if match:
            return match.group(1)
    return None

def collect_data(suite_dir, suite_name):
    """Collect IPC data for a benchmark suite."""
    # data[workload][page_size][error_rate] = ipc
    data = {}

    for page_size in PAGE_SIZES:
        for error_rate in ERROR_RATES:
            pattern = os.path.join(suite_dir, f"champsim_{page_size}_error_32gb_{error_rate}_cache_pinning_*")
            files = glob.glob(pattern)

            for filepath in files:
                filename = os.path.basename(filepath)
                workload = extract_workload_name(filename, suite_name)

                if workload:
                    if workload not in data:
                        data[workload] = {ps: {er: None for er in ERROR_RATES} for ps in PAGE_SIZES}

                    ipc = extract_ipc(filepath)
                    if ipc:
                        data[workload][page_size][error_rate] = ipc

    return data

def main():
    # Collect data
    spec_data = collect_data(SPEC_DIR, "spec")
    gap_data = collect_data(GAP_DIR, "gap")

    print(f"Collected {len(spec_data)} SPEC workloads")
    print(f"Collected {len(gap_data)} GAP workloads")

    # Sort workloads
    spec_workloads = sorted(spec_data.keys())
    gap_workloads = sorted(gap_data.keys())
    all_workloads = spec_workloads + gap_workloads

    # Prepare data for CSV
    csv_rows = []
    for workload in spec_workloads:
        row = {'Workload': workload, 'Category': 'SPEC'}
        for page_size in PAGE_SIZES:
            for error_rate in ERROR_RATES:
                col_name = f'{page_size}_{error_rate}'
                row[col_name] = spec_data[workload][page_size][error_rate]
        csv_rows.append(row)

    for workload in gap_workloads:
        row = {'Workload': workload, 'Category': 'GAP'}
        for page_size in PAGE_SIZES:
            for error_rate in ERROR_RATES:
                col_name = f'{page_size}_{error_rate}'
                row[col_name] = gap_data[workload][page_size][error_rate]
        csv_rows.append(row)

    # Create DataFrame and save CSV
    df = pd.DataFrame(csv_rows)
    csv_path = os.path.join(OUTPUT_DIR, "llc_pin_ipc_comparison.csv")
    df.to_csv(csv_path, index=False)
    print(f"CSV saved to: {csv_path}")

    # Prepare data for plotting
    # Combine spec and gap data
    all_data = {**spec_data, **gap_data}

    # Create plot
    fig, ax = plt.subplots(figsize=(14, 3))

    n_workloads = len(all_workloads)
    n_bars_per_workload = len(PAGE_SIZES) * len(ERROR_RATES)  # 8 bars

    # Colors: gradient for each page size
    colors_4kb = ['#FADBD8', '#F1948A', '#E74C3C', '#922B21']  # Light to dark red
    colors_2mb = ['#D4E6F1', '#7FB3D5', '#2980B9', '#1A5276']  # Light to dark blue

    bar_width = 0.1
    group_width = bar_width * n_bars_per_workload + 0.15

    x_positions = np.arange(n_workloads) * group_width

    # Draw bars (4KB group first, then 2MB group)
    for i, workload in enumerate(all_workloads):
        data = all_data[workload]
        bar_idx = 0

        # 4KB bars (all error rates)
        ipc_4kb_values = []
        for j, error_rate in enumerate(ERROR_RATES):
            ipc_4kb = data['4kb'][error_rate]
            if ipc_4kb:
                ax.bar(x_positions[i] + bar_idx * bar_width, ipc_4kb, bar_width,
                       color=colors_4kb[j], edgecolor='black', linewidth=0.3)
                ipc_4kb_values.append(ipc_4kb)
            bar_idx += 1

        # Add percentage change at center of 4KB group
        ipc_4kb_1e6 = data['4kb']['1e-6']
        ipc_4kb_1e9 = data['4kb']['1e-9']
        if ipc_4kb_1e6 and ipc_4kb_1e9 and ipc_4kb_values:
            pct_change = ((ipc_4kb_1e9 - ipc_4kb_1e6) / ipc_4kb_1e6) * 100
            sign = '+' if pct_change >= 0 else ''
            center_4kb = x_positions[i] + 1.5 * bar_width  # center of 4 bars (idx 0,1,2,3)
            max_height_4kb = max(ipc_4kb_values)
            ax.text(center_4kb, max_height_4kb + 0.02,
                    f'{sign}{pct_change:.1f}%', ha='center', va='bottom',
                    fontsize=3, color='darkred')

        # 2MB bars (all error rates)
        ipc_2mb_values = []
        for j, error_rate in enumerate(ERROR_RATES):
            ipc_2mb = data['2mb'][error_rate]
            if ipc_2mb:
                ax.bar(x_positions[i] + bar_idx * bar_width, ipc_2mb, bar_width,
                       color=colors_2mb[j], edgecolor='black', linewidth=0.3)
                ipc_2mb_values.append(ipc_2mb)
            bar_idx += 1

        # Add percentage change at center of 2MB group
        ipc_2mb_1e6 = data['2mb']['1e-6']
        ipc_2mb_1e9 = data['2mb']['1e-9']
        if ipc_2mb_1e6 and ipc_2mb_1e9 and ipc_2mb_values:
            pct_change = ((ipc_2mb_1e9 - ipc_2mb_1e6) / ipc_2mb_1e6) * 100
            sign = '+' if pct_change >= 0 else ''
            center_2mb = x_positions[i] + 5.5 * bar_width  # center of 4 bars (idx 4,5,6,7)
            max_height_2mb = max(ipc_2mb_values)
            ax.text(center_2mb, max_height_2mb + 0.02,
                    f'{sign}{pct_change:.1f}%', ha='center', va='bottom',
                    fontsize=3, color='darkblue')

    # Create legend (4KB group, then 2MB group)
    legend_elements = []
    for j, error_rate in enumerate(ERROR_RATES):
        legend_elements.append(plt.Rectangle((0,0),1,1, facecolor=colors_4kb[j], edgecolor='black', linewidth=0.3, label=f'4KB {error_rate}'))
    for j, error_rate in enumerate(ERROR_RATES):
        legend_elements.append(plt.Rectangle((0,0),1,1, facecolor=colors_2mb[j], edgecolor='black', linewidth=0.3, label=f'2MB {error_rate}'))

    ax.legend(handles=legend_elements, loc='upper right', fontsize=5, ncol=4, framealpha=0.9)

    # Customize plot
    ax.set_ylabel('IPC', fontsize=8)
    ax.set_xticks(x_positions + (n_bars_per_workload - 1) * bar_width / 2)
    ax.set_xticklabels(all_workloads, rotation=45, ha='right', fontsize=5)
    ax.tick_params(axis='y', labelsize=6)

    # Add grid
    ax.yaxis.grid(True, linestyle='--', alpha=0.5, linewidth=0.5)
    ax.set_axisbelow(True)

    # Reduce margins
    ax.set_xlim(-0.1, x_positions[-1] + n_bars_per_workload * bar_width + 0.1)

    plt.tight_layout(pad=0.3)

    # Save plot
    png_path = os.path.join(OUTPUT_DIR, "llc_pin_ipc_comparison.png")
    plt.savefig(png_path, dpi=300, bbox_inches='tight', facecolor='white', edgecolor='none')
    print(f"PNG saved to: {png_path}")

    plt.close()

    # Print summary
    print("\n=== Summary ===")
    for error_rate in ERROR_RATES:
        spec_4kb = [spec_data[w]['4kb'][error_rate] for w in spec_workloads if spec_data[w]['4kb'][error_rate]]
        spec_2mb = [spec_data[w]['2mb'][error_rate] for w in spec_workloads if spec_data[w]['2mb'][error_rate]]
        gap_4kb = [gap_data[w]['4kb'][error_rate] for w in gap_workloads if gap_data[w]['4kb'][error_rate]]
        gap_2mb = [gap_data[w]['2mb'][error_rate] for w in gap_workloads if gap_data[w]['2mb'][error_rate]]

        if spec_4kb and spec_2mb:
            print(f"SPEC {error_rate} - 4KB GMEAN: {gmean(spec_4kb):.4f}, 2MB GMEAN: {gmean(spec_2mb):.4f}")
        if gap_4kb and gap_2mb:
            print(f"GAP  {error_rate} - 4KB GMEAN: {gmean(gap_4kb):.4f}, 2MB GMEAN: {gmean(gap_2mb):.4f}")

    # Print average percentage change (1e-6 -> 1e-9)
    print("\n=== Average IPC Change (1e-6 -> 1e-9) ===")

    # Calculate percentage changes for each workload
    spec_pct_4kb = []
    spec_pct_2mb = []
    for w in spec_workloads:
        ipc_1e6_4kb = spec_data[w]['4kb']['1e-6']
        ipc_1e9_4kb = spec_data[w]['4kb']['1e-9']
        ipc_1e6_2mb = spec_data[w]['2mb']['1e-6']
        ipc_1e9_2mb = spec_data[w]['2mb']['1e-9']
        if ipc_1e6_4kb and ipc_1e9_4kb:
            spec_pct_4kb.append(((ipc_1e9_4kb - ipc_1e6_4kb) / ipc_1e6_4kb) * 100)
        if ipc_1e6_2mb and ipc_1e9_2mb:
            spec_pct_2mb.append(((ipc_1e9_2mb - ipc_1e6_2mb) / ipc_1e6_2mb) * 100)

    gap_pct_4kb = []
    gap_pct_2mb = []
    for w in gap_workloads:
        ipc_1e6_4kb = gap_data[w]['4kb']['1e-6']
        ipc_1e9_4kb = gap_data[w]['4kb']['1e-9']
        ipc_1e6_2mb = gap_data[w]['2mb']['1e-6']
        ipc_1e9_2mb = gap_data[w]['2mb']['1e-9']
        if ipc_1e6_4kb and ipc_1e9_4kb:
            gap_pct_4kb.append(((ipc_1e9_4kb - ipc_1e6_4kb) / ipc_1e6_4kb) * 100)
        if ipc_1e6_2mb and ipc_1e9_2mb:
            gap_pct_2mb.append(((ipc_1e9_2mb - ipc_1e6_2mb) / ipc_1e6_2mb) * 100)

    if spec_pct_4kb:
        print(f"SPEC  - 4KB Avg: {np.mean(spec_pct_4kb):+.2f}%, 2MB Avg: {np.mean(spec_pct_2mb):+.2f}%")
    if gap_pct_4kb:
        print(f"GAP   - 4KB Avg: {np.mean(gap_pct_4kb):+.2f}%, 2MB Avg: {np.mean(gap_pct_2mb):+.2f}%")

    total_pct_4kb = spec_pct_4kb + gap_pct_4kb
    total_pct_2mb = spec_pct_2mb + gap_pct_2mb
    if total_pct_4kb:
        print(f"Total - 4KB Avg: {np.mean(total_pct_4kb):+.2f}%, 2MB Avg: {np.mean(total_pct_2mb):+.2f}%")

if __name__ == "__main__":
    main()
