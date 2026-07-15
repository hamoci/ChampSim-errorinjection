#!/usr/bin/env python3
"""
LLC Cache Way Usage Analysis Script
Extracts Cache Pinning statistics from ChampSim simulation results.
- Allocated Error Ways per Set: shown as dots (scatter plot)
- Used Error Way Slot percentage: shown as bar graph
All error rates (1e-6 ~ 1e-9) in a single graph.
"""

import os
import re
import glob
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt

# Paths (relative to script location)
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
BASE_DIR = os.path.dirname(SCRIPT_DIR)
RESULTS_DIR = os.path.join(BASE_DIR, "results/cache_pinning")
SPEC_DIR = os.path.join(RESULTS_DIR, "spec_pinned/64B_addressing")
GAP_DIR = os.path.join(RESULTS_DIR, "gap_pinned")
OUTPUT_DIR = SCRIPT_DIR

# Error rates and page sizes
ERROR_RATES = ['1e-6', '1e-7', '1e-8', '1e-9']
PAGE_SIZES = ['4kb', '2mb']

# Color scheme (matching llc_pin_ipc_comparison.py)
COLORS_4KB = ['#FADBD8', '#F1948A', '#E74C3C', '#922B21']  # Light to dark red
COLORS_2MB = ['#D4E6F1', '#7FB3D5', '#2980B9', '#1A5276']  # Light to dark blue


def extract_cache_way_stats(filepath):
    """Extract LLC Error Way Statistics from ChampSim result file."""
    try:
        with open(filepath, 'r') as f:
            content = f.read()
    except FileNotFoundError:
        return None

    alloc_match = re.search(r'Allocated Error Ways per Set:\s+(\d+)', content)
    used_match = re.search(r'Used Error Way Slots:\s+\d+\s+\(([\d.]+)%\)', content)

    if alloc_match and used_match:
        return {
            'allocated_ways': int(alloc_match.group(1)),
            'used_pct': float(used_match.group(1))
        }
    return None


def extract_workload_name(filename, suite):
    """Extract workload name from filename."""
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
    """Collect cache way usage data for a benchmark suite."""
    # data[workload][page_size][error_rate] = {'allocated_ways': X, 'used_pct': Y}
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

                    stats = extract_cache_way_stats(filepath)
                    if stats:
                        data[workload][page_size][error_rate] = stats

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
                stats = spec_data[workload][page_size][error_rate]
                row[f'{page_size}_{error_rate}_alloc'] = stats['allocated_ways'] if stats else None
                row[f'{page_size}_{error_rate}_used'] = stats['used_pct'] if stats else None
        csv_rows.append(row)

    for workload in gap_workloads:
        row = {'Workload': workload, 'Category': 'GAP'}
        for page_size in PAGE_SIZES:
            for error_rate in ERROR_RATES:
                stats = gap_data[workload][page_size][error_rate]
                row[f'{page_size}_{error_rate}_alloc'] = stats['allocated_ways'] if stats else None
                row[f'{page_size}_{error_rate}_used'] = stats['used_pct'] if stats else None
        csv_rows.append(row)

    # Save CSV
    df = pd.DataFrame(csv_rows)
    csv_path = os.path.join(OUTPUT_DIR, "llc_cache_way_usage.csv")
    df.to_csv(csv_path, index=False)
    print(f"CSV saved to: {csv_path}")

    # Combine all data
    all_data = {**spec_data, **gap_data}

    # Create plot
    fig, ax = plt.subplots(figsize=(14, 3.5))

    n_workloads = len(all_workloads)
    n_bars_per_workload = len(PAGE_SIZES) * len(ERROR_RATES)  # 8 bars

    bar_width = 0.1
    group_width = bar_width * n_bars_per_workload + 0.15

    x_positions = np.arange(n_workloads) * group_width

    # Secondary y-axis for Allocated Ways
    ax2 = ax.twinx()

    # Draw bars and dots for each workload
    for i, workload in enumerate(all_workloads):
        data = all_data[workload]
        bar_idx = 0

        # Collect positions and values for line connection
        x_4kb = []
        y_4kb = []
        x_2mb = []
        y_2mb = []

        # 4KB bars (all error rates)
        for j, error_rate in enumerate(ERROR_RATES):
            stats = data['4kb'][error_rate]
            if stats:
                # Bar for Used %
                ax.bar(x_positions[i] + bar_idx * bar_width, stats['used_pct'], bar_width,
                       color=COLORS_4KB[j], edgecolor='black', linewidth=0.3)
                # Collect for line
                x_4kb.append(x_positions[i] + bar_idx * bar_width)
                y_4kb.append(stats['allocated_ways'])
            bar_idx += 1

        # 2MB bars (all error rates)
        for j, error_rate in enumerate(ERROR_RATES):
            stats = data['2mb'][error_rate]
            if stats:
                # Bar for Used %
                ax.bar(x_positions[i] + bar_idx * bar_width, stats['used_pct'], bar_width,
                       color=COLORS_2MB[j], edgecolor='black', linewidth=0.3)
                # Collect for line
                x_2mb.append(x_positions[i] + bar_idx * bar_width)
                y_2mb.append(stats['allocated_ways'])
            bar_idx += 1

        # Draw connected lines with dots for 4KB (red)
        if x_4kb:
            ax2.plot(x_4kb, y_4kb, color='#E74C3C', linewidth=1.2, zorder=5)
            ax2.scatter(x_4kb, y_4kb, s=15, color='#E74C3C', marker='o', edgecolors='black', linewidths=0.3, zorder=6)

        # Draw connected lines with dots for 2MB (blue)
        if x_2mb:
            ax2.plot(x_2mb, y_2mb, color='#2980B9', linewidth=1.2, zorder=5)
            ax2.scatter(x_2mb, y_2mb, s=15, color='#2980B9', marker='o', edgecolors='black', linewidths=0.3, zorder=6)

    # Create legend (bars + lines)
    legend_elements = []
    for j, error_rate in enumerate(ERROR_RATES):
        legend_elements.append(plt.Rectangle((0,0),1,1, facecolor=COLORS_4KB[j], edgecolor='black', linewidth=0.3, label=f'4KB {error_rate}'))
    for j, error_rate in enumerate(ERROR_RATES):
        legend_elements.append(plt.Rectangle((0,0),1,1, facecolor=COLORS_2MB[j], edgecolor='black', linewidth=0.3, label=f'2MB {error_rate}'))
    # Add line legends for Allocated Ways
    legend_elements.append(plt.Line2D([0], [0], marker='o', color='#E74C3C', markerfacecolor='#E74C3C', markersize=4, linewidth=1.2, label='4KB Alloc Ways'))
    legend_elements.append(plt.Line2D([0], [0], marker='o', color='#2980B9', markerfacecolor='#2980B9', markersize=4, linewidth=1.2, label='2MB Alloc Ways'))

    ax.legend(handles=legend_elements, loc='upper right', fontsize=5, ncol=5, framealpha=0.9)

    # Customize plot
    ax.set_ylabel('Used Error Way Slots (%)', fontsize=8)
    ax.set_ylim(0, 115)
    ax.set_xticks(x_positions + (n_bars_per_workload - 1) * bar_width / 2)
    ax.set_xticklabels(all_workloads, rotation=45, ha='right', fontsize=5)
    ax.tick_params(axis='y', labelsize=6)

    ax2.set_ylabel('Allocated Error Ways per Set', fontsize=8)
    ax2.set_ylim(0, 10)
    ax2.tick_params(axis='y', labelsize=6)

    # Add grid
    ax.yaxis.grid(True, linestyle='--', alpha=0.5, linewidth=0.5)
    ax.set_axisbelow(True)

    # Reduce margins
    ax.set_xlim(-0.1, x_positions[-1] + n_bars_per_workload * bar_width + 0.1)

    # Add vertical separator between SPEC and GAP
    if spec_workloads and gap_workloads:
        separator_x = x_positions[len(spec_workloads)] - group_width / 2 + 0.02
        ax.axvline(x=separator_x, color='gray', linestyle='--', linewidth=1, alpha=0.7)

    plt.tight_layout(pad=0.3)

    # Save plot
    png_path = os.path.join(OUTPUT_DIR, "llc_cache_way_usage.png")
    plt.savefig(png_path, dpi=300, bbox_inches='tight', facecolor='white', edgecolor='none')
    print(f"PNG saved to: {png_path}")

    plt.close()

    # Print summary
    print("\n=== Summary Statistics ===")
    for page_size in PAGE_SIZES:
        print(f"\n{page_size.upper()} Page:")
        for error_rate in ERROR_RATES:
            alloc_list = []
            used_list = []
            for workload in all_workloads:
                stats = all_data[workload][page_size][error_rate]
                if stats:
                    alloc_list.append(stats['allocated_ways'])
                    used_list.append(stats['used_pct'])
            if alloc_list:
                print(f"  {error_rate}: Avg Allocated = {np.mean(alloc_list):.2f}, Avg Used = {np.mean(used_list):.2f}%")

    # === Create Average Graph (SPEC | GAP | Overall) ===
    print("\nGenerating average graph...")

    # Calculate averages for each category
    def calc_avg(data, workloads, page_size, error_rate):
        alloc_list = []
        used_list = []
        for w in workloads:
            stats = data[w][page_size][error_rate]
            if stats:
                alloc_list.append(stats['allocated_ways'])
                used_list.append(stats['used_pct'])
        if alloc_list:
            return {'alloc': np.mean(alloc_list), 'used': np.mean(used_list)}
        return None

    # Build results structure
    results = {'SPEC': {}, 'GAP': {}, 'Overall': {}}
    for error_rate in ERROR_RATES:
        results['SPEC'][error_rate] = {
            '4kb': calc_avg(spec_data, spec_workloads, '4kb', error_rate),
            '2mb': calc_avg(spec_data, spec_workloads, '2mb', error_rate),
        }
        results['GAP'][error_rate] = {
            '4kb': calc_avg(gap_data, gap_workloads, '4kb', error_rate),
            '2mb': calc_avg(gap_data, gap_workloads, '2mb', error_rate),
        }
        results['Overall'][error_rate] = {
            '4kb': calc_avg(all_data, all_workloads, '4kb', error_rate),
            '2mb': calc_avg(all_data, all_workloads, '2mb', error_rate),
        }

    # Create average plot
    fig, ax = plt.subplots(figsize=(10, 4))

    bar_width = 0.18
    suites = ['SPEC', 'GAP', 'Overall']
    num_error_rates = len(ERROR_RATES)
    group_width = num_error_rates + 0.5

    # Collect data for plotting
    used_4kb, used_2mb = [], []
    alloc_4kb, alloc_2mb = [], []
    x_positions = []
    x_labels = []

    for suite_idx, suite in enumerate(suites):
        base_x = suite_idx * group_width
        for er_idx, er in enumerate(ERROR_RATES):
            x_pos = base_x + er_idx
            x_positions.append(x_pos)
            x_labels.append(er)

            r_4kb = results[suite][er]['4kb']
            r_2mb = results[suite][er]['2mb']

            used_4kb.append(r_4kb['used'] if r_4kb else 0)
            used_2mb.append(r_2mb['used'] if r_2mb else 0)
            alloc_4kb.append(r_4kb['alloc'] if r_4kb else 0)
            alloc_2mb.append(r_2mb['alloc'] if r_2mb else 0)

    x = np.array(x_positions)

    # Draw bars for Used %
    ax.bar(x - bar_width/2, used_4kb, bar_width, label='4KB Used %', color='#E74C3C', edgecolor='black', linewidth=0.3)
    ax.bar(x + bar_width/2, used_2mb, bar_width, label='2MB Used %', color='#2980B9', edgecolor='black', linewidth=0.3)

    # Secondary y-axis for Allocated Ways (line + dot)
    ax2 = ax.twinx()

    # Prepare line data per suite
    for suite_idx, suite in enumerate(suites):
        base_x = suite_idx * group_width
        suite_x = [base_x + er_idx for er_idx in range(num_error_rates)]

        suite_alloc_4kb = []
        suite_alloc_2mb = []
        for er in ERROR_RATES:
            r_4kb = results[suite][er]['4kb']
            r_2mb = results[suite][er]['2mb']
            suite_alloc_4kb.append(r_4kb['alloc'] if r_4kb else 0)
            suite_alloc_2mb.append(r_2mb['alloc'] if r_2mb else 0)

        # Draw lines within each suite group
        ax2.plot(suite_x, suite_alloc_4kb, color='#C0392B', linewidth=2, zorder=5)
        ax2.scatter(suite_x, suite_alloc_4kb, s=40, color='#E74C3C', marker='o', edgecolors='black', linewidths=0.5, zorder=6)

        ax2.plot(suite_x, suite_alloc_2mb, color='#1A5276', linewidth=2, zorder=5)
        ax2.scatter(suite_x, suite_alloc_2mb, s=40, color='#2980B9', marker='s', edgecolors='black', linewidths=0.5, zorder=6)

    # Customize axes
    ax.set_ylabel('Used Error Way Slots (%)', fontsize=9)
    ax.set_ylim(0, 115)
    ax.set_xticks(x)
    ax.set_xticklabels(x_labels, fontsize=7)
    ax.tick_params(axis='y', labelsize=7)

    ax2.set_ylabel('Allocated Error Ways per Set', fontsize=9)
    ax2.set_ylim(0, 10)
    ax2.tick_params(axis='y', labelsize=7)

    # Add vertical dashed lines to separate SPEC, GAP, Overall
    for suite_idx in range(1, len(suites)):
        line_x = suite_idx * group_width - 0.75
        ax.axvline(x=line_x, color='gray', linestyle='--', linewidth=1.5, alpha=0.7)

    # Add suite labels (positioned lower to avoid legend overlap)
    for suite_idx, suite in enumerate(suites):
        center_x = suite_idx * group_width + (num_error_rates - 1) / 2
        ax.text(center_x, 85, suite, ha='center', va='bottom', fontsize=10, fontweight='bold')

    # Grid
    ax.yaxis.grid(True, linestyle='--', alpha=0.5, linewidth=0.5)
    ax.set_axisbelow(True)

    # Legend
    legend_elements = [
        plt.Rectangle((0,0),1,1, facecolor='#E74C3C', edgecolor='black', linewidth=0.3, label='4KB Used %'),
        plt.Rectangle((0,0),1,1, facecolor='#2980B9', edgecolor='black', linewidth=0.3, label='2MB Used %'),
        plt.Line2D([0], [0], marker='o', color='#C0392B', markerfacecolor='#E74C3C', markersize=6, linewidth=2, label='4KB Alloc Ways'),
        plt.Line2D([0], [0], marker='s', color='#1A5276', markerfacecolor='#2980B9', markersize=6, linewidth=2, label='2MB Alloc Ways'),
    ]
    ax.legend(handles=legend_elements, loc='upper left', fontsize=7, ncol=2, framealpha=0.9)

    ax.set_xlabel('MTBCE', fontsize=9)
    ax.set_xlim(x[0] - 0.6, x[-1] + 0.6)

    plt.tight_layout(pad=0.5)

    # Save average plot
    avg_png_path = os.path.join(OUTPUT_DIR, "llc_cache_way_usage_avg.png")
    plt.savefig(avg_png_path, dpi=300, bbox_inches='tight', facecolor='white', edgecolor='none')
    print(f"Average PNG saved to: {avg_png_path}")

    plt.close()

    # Save average CSV
    avg_csv_rows = []
    for suite in suites:
        for er in ERROR_RATES:
            r_4kb = results[suite][er]['4kb']
            r_2mb = results[suite][er]['2mb']
            avg_csv_rows.append({
                'Suite': suite,
                'MTBCE': er,
                '4KB_Alloc': r_4kb['alloc'] if r_4kb else None,
                '4KB_Used': r_4kb['used'] if r_4kb else None,
                '2MB_Alloc': r_2mb['alloc'] if r_2mb else None,
                '2MB_Used': r_2mb['used'] if r_2mb else None,
            })
    avg_df = pd.DataFrame(avg_csv_rows)
    avg_csv_path = os.path.join(OUTPUT_DIR, "llc_cache_way_usage_avg.csv")
    avg_df.to_csv(avg_csv_path, index=False)
    print(f"Average CSV saved to: {avg_csv_path}")


if __name__ == "__main__":
    main()
