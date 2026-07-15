#!/usr/bin/env python3
"""
LLC Pin vs Not-Pin Average IPC Comparison Script
Compares GMEAN IPC between cache pinning and not-pinning across MTBCE (error rates).
- CSV: GMEAN IPC values
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

# Pin directories
PIN_SPEC_DIR = os.path.join(BASE_DIR, "results/cache_pinning/spec_pinned/64B_addressing")
PIN_GAP_DIR = os.path.join(BASE_DIR, "results/cache_pinning/gap_pinned")

# Not-pin directories
NOTPIN_SPEC_DIR = os.path.join(BASE_DIR, "results/not_cache_pinned/SPEC_not_cache_pinned/_32gb")
NOTPIN_GAP_DIR = os.path.join(BASE_DIR, "results/not_cache_pinned/gaps_not_cache_pinned/_32gb")

OUTPUT_DIR = SCRIPT_DIR

# Error rates (MTBCE) to analyze
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

def extract_workload_name_pin(filename, suite):
    """Extract workload name from pin filename."""
    if suite == "spec":
        match = re.search(r'champsim_\w+_error_32gb_[\de-]+_cache_pinning_(\d+\.\w+)', filename)
        if match:
            return match.group(1)
    elif suite == "gap":
        match = re.search(r'champsim_\w+_error_32gb_[\de-]+_cache_pinning_(.+?)\.trace\.gz\.txt', filename)
        if match:
            return match.group(1)
    return None

def extract_workload_name_notpin(filename, suite):
    """Extract workload name from not-pin filename."""
    if suite == "spec":
        match = re.search(r'champsim_\w+_error_32gb_[\de-]+_(\d+\.\w+)', filename)
        if match:
            return match.group(1)
    elif suite == "gap":
        match = re.search(r'champsim_\w+_error_32gb_[\de-]+_(.+?)\.trace\.gz\.txt', filename)
        if match:
            return match.group(1)
    return None

def collect_data_pin(suite_dir, suite_name):
    """Collect IPC data for pinned benchmark suite."""
    data = {}
    for page_size in PAGE_SIZES:
        for error_rate in ERROR_RATES:
            pattern = os.path.join(suite_dir, f"champsim_{page_size}_error_32gb_{error_rate}_cache_pinning_*")
            files = glob.glob(pattern)
            for filepath in files:
                filename = os.path.basename(filepath)
                workload = extract_workload_name_pin(filename, suite_name)
                if workload:
                    if workload not in data:
                        data[workload] = {ps: {er: None for er in ERROR_RATES} for ps in PAGE_SIZES}
                    ipc = extract_ipc(filepath)
                    if ipc:
                        data[workload][page_size][error_rate] = ipc
    return data

def collect_data_notpin(suite_dir, suite_name):
    """Collect IPC data for not-pinned benchmark suite."""
    data = {}
    for page_size in PAGE_SIZES:
        for error_rate in ERROR_RATES:
            pattern = os.path.join(suite_dir, f"champsim_{page_size}_error_32gb_{error_rate}_*")
            files = glob.glob(pattern)
            for filepath in files:
                filename = os.path.basename(filepath)
                # Skip if it's a cache_pinning file
                if 'cache_pinning' in filename:
                    continue
                workload = extract_workload_name_notpin(filename, suite_name)
                if workload:
                    if workload not in data:
                        data[workload] = {ps: {er: None for er in ERROR_RATES} for ps in PAGE_SIZES}
                    ipc = extract_ipc(filepath)
                    if ipc:
                        data[workload][page_size][error_rate] = ipc
    return data

def calculate_gmean(data, workloads, page_size, error_rate):
    """Calculate geometric mean for given parameters."""
    values = [data[w][page_size][error_rate] for w in workloads if data[w][page_size][error_rate]]
    return gmean(values) if values else None

def main():
    # Collect data
    pin_spec = collect_data_pin(PIN_SPEC_DIR, "spec")
    pin_gap = collect_data_pin(PIN_GAP_DIR, "gap")
    notpin_spec = collect_data_notpin(NOTPIN_SPEC_DIR, "spec")
    notpin_gap = collect_data_notpin(NOTPIN_GAP_DIR, "gap")

    print(f"Pin SPEC: {len(pin_spec)}, Pin GAP: {len(pin_gap)}")
    print(f"NotPin SPEC: {len(notpin_spec)}, NotPin GAP: {len(notpin_gap)}")

    # Calculate GMEANs for each error rate
    results = {'SPEC': {}, 'GAP': {}, 'Overall': {}}

    for error_rate in ERROR_RATES:
        # SPEC
        results['SPEC'][error_rate] = {
            'pin_4kb': calculate_gmean(pin_spec, pin_spec.keys(), '4kb', error_rate),
            'pin_2mb': calculate_gmean(pin_spec, pin_spec.keys(), '2mb', error_rate),
            'notpin_4kb': calculate_gmean(notpin_spec, notpin_spec.keys(), '4kb', error_rate),
            'notpin_2mb': calculate_gmean(notpin_spec, notpin_spec.keys(), '2mb', error_rate),
        }
        # GAP
        results['GAP'][error_rate] = {
            'pin_4kb': calculate_gmean(pin_gap, pin_gap.keys(), '4kb', error_rate),
            'pin_2mb': calculate_gmean(pin_gap, pin_gap.keys(), '2mb', error_rate),
            'notpin_4kb': calculate_gmean(notpin_gap, notpin_gap.keys(), '4kb', error_rate),
            'notpin_2mb': calculate_gmean(notpin_gap, notpin_gap.keys(), '2mb', error_rate),
        }
        # Overall (combine SPEC and GAP)
        all_pin = {**pin_spec, **pin_gap}
        all_notpin = {**notpin_spec, **notpin_gap}
        results['Overall'][error_rate] = {
            'pin_4kb': calculate_gmean(all_pin, all_pin.keys(), '4kb', error_rate),
            'pin_2mb': calculate_gmean(all_pin, all_pin.keys(), '2mb', error_rate),
            'notpin_4kb': calculate_gmean(all_notpin, all_notpin.keys(), '4kb', error_rate),
            'notpin_2mb': calculate_gmean(all_notpin, all_notpin.keys(), '2mb', error_rate),
        }

    # Save to CSV
    csv_rows = []
    for suite in ['SPEC', 'GAP', 'Overall']:
        for error_rate in ERROR_RATES:
            row = {
                'Suite': suite,
                'MTBCE': error_rate,
                'Pin_4KB': results[suite][error_rate]['pin_4kb'],
                'Pin_2MB': results[suite][error_rate]['pin_2mb'],
                'NotPin_4KB': results[suite][error_rate]['notpin_4kb'],
                'NotPin_2MB': results[suite][error_rate]['notpin_2mb'],
            }
            csv_rows.append(row)

    df = pd.DataFrame(csv_rows)
    csv_path = os.path.join(OUTPUT_DIR, "llc_pin_notpin_avg_ipc_comparison.csv")
    df.to_csv(csv_path, index=False)
    print(f"CSV saved to: {csv_path}")

    # Create combined plot (SPEC | GAP | Overall)
    fig, ax = plt.subplots(1, 1, figsize=(14, 4))

    # Colors (4KB = red tones, 2MB = blue tones)
    colors = {
        'pin_4kb': '#F1948A',      # Light red
        'notpin_4kb': '#922B21',   # Dark red
        'pin_2mb': '#7FB3D5',      # Light blue
        'notpin_2mb': '#1A5276',   # Dark blue
    }

    bar_width = 0.18
    suites = ['SPEC', 'GAP', 'Overall']
    num_error_rates = len(ERROR_RATES)
    group_width = num_error_rates + 0.3  # Reduced space between groups

    all_pin_4kb, all_pin_2mb, all_notpin_4kb, all_notpin_2mb = [], [], [], []
    x_positions = []
    x_labels = []

    for suite_idx, suite in enumerate(suites):
        base_x = suite_idx * group_width
        for er_idx, er in enumerate(ERROR_RATES):
            x_pos = base_x + er_idx
            x_positions.append(x_pos)
            x_labels.append(er)
            all_pin_4kb.append(results[suite][er]['pin_4kb'] or 0)
            all_pin_2mb.append(results[suite][er]['pin_2mb'] or 0)
            all_notpin_4kb.append(results[suite][er]['notpin_4kb'] or 0)
            all_notpin_2mb.append(results[suite][er]['notpin_2mb'] or 0)

    x = np.array(x_positions)

    # Draw bars (NotPin first, then Pin) - 4KB group, then 2MB group
    ax.bar(x - 1.5*bar_width, all_notpin_4kb, bar_width, label='NotPin 4KB', color=colors['notpin_4kb'], edgecolor='black', linewidth=0.3)
    bars_pin_4kb = ax.bar(x - 0.5*bar_width, all_pin_4kb, bar_width, label='Pin 4KB', color=colors['pin_4kb'], edgecolor='black', linewidth=0.3)
    ax.bar(x + 0.5*bar_width, all_notpin_2mb, bar_width, label='NotPin 2MB', color=colors['notpin_2mb'], edgecolor='black', linewidth=0.3)
    bars_pin_2mb = ax.bar(x + 1.5*bar_width, all_pin_2mb, bar_width, label='Pin 2MB', color=colors['pin_2mb'], edgecolor='black', linewidth=0.3)

    # Calculate and display IPC change percentage between NotPin and Pin bars
    for i, (bar, pin_val, notpin_val) in enumerate(zip(bars_pin_4kb, all_pin_4kb, all_notpin_4kb)):
        if notpin_val > 0 and pin_val > 0:
            pct = (pin_val - notpin_val) / notpin_val * 100
            sign = '+' if pct >= 0 else ''
            text_x = x[i] - bar_width
            text_y = max(pin_val, notpin_val)
            ax.text(text_x, text_y, f'{sign}{pct:.1f}%',
                    ha='center', va='bottom', fontsize=5)

    for i, (bar, pin_val, notpin_val) in enumerate(zip(bars_pin_2mb, all_pin_2mb, all_notpin_2mb)):
        if notpin_val > 0 and pin_val > 0:
            pct = (pin_val - notpin_val) / notpin_val * 100
            sign = '+' if pct >= 0 else ''
            text_x = x[i] + bar_width
            text_y = max(pin_val, notpin_val)
            ax.text(text_x, text_y, f'{sign}{pct:.1f}%',
                    ha='center', va='bottom', fontsize=5)

    # Adjust Y-axis to data range (not starting from 0)
    all_vals = [v for v in all_pin_4kb + all_pin_2mb + all_notpin_4kb + all_notpin_2mb if v > 0]
    if all_vals:
        min_val = min(all_vals)
        max_val = max(all_vals)
        margin = (max_val - min_val) * 0.3  # Extra margin for labels
        ax.set_ylim(min_val - (max_val - min_val) * 0.1, max_val + margin)

    # Add vertical dashed lines to separate SPEC, GAP, Overall
    for suite_idx in range(1, len(suites)):
        line_x = suite_idx * group_width - 0.65
        ax.axvline(x=line_x, color='gray', linestyle='--', linewidth=1.5, alpha=0.7)

    # Add suite labels at the top
    y_top = ax.get_ylim()[1]
    y_bottom = ax.get_ylim()[0]
    label_y = y_top - (y_top - y_bottom) * 0.08  # Position slightly below top
    for suite_idx, suite in enumerate(suites):
        center_x = suite_idx * group_width + (num_error_rates - 1) / 2
        ax.text(center_x, label_y, suite, ha='center', va='top',
                fontsize=10, fontweight='bold')

    # Customize
    ax.set_xlabel('MTBCE', fontsize=10)
    ax.set_ylabel('IPC (GMEAN)', fontsize=10)
    ax.set_xticks(x)
    ax.set_xticklabels(x_labels, fontsize=7)
    ax.tick_params(axis='y', labelsize=7)
    ax.yaxis.grid(True, linestyle='--', alpha=0.5, linewidth=0.5)
    ax.set_axisbelow(True)
    ax.legend(loc='upper right', fontsize=7, ncol=4, framealpha=0.9)

    # Reduce left/right margins
    ax.set_xlim(x[0] - 0.6, x[-1] + 0.6)

    plt.tight_layout(pad=0.5)

    # Save plot
    png_path = os.path.join(OUTPUT_DIR, "llc_pin_notpin_avg_ipc_comparison.png")
    plt.savefig(png_path, dpi=300, bbox_inches='tight', facecolor='white', edgecolor='none')
    print(f"PNG saved to: {png_path}")

    plt.close()

    # Print summary
    print("\n=== Summary ===")
    for suite in ['SPEC', 'GAP', 'Overall']:
        print(f"\n{suite}:")
        print(f"{'MTBCE':<8} {'Pin 4KB':<10} {'Pin 2MB':<10} {'NotPin 4KB':<12} {'NotPin 2MB':<12}")
        for error_rate in ERROR_RATES:
            r = results[suite][error_rate]
            p4 = f"{r['pin_4kb']:.4f}" if r['pin_4kb'] else "N/A"
            p2 = f"{r['pin_2mb']:.4f}" if r['pin_2mb'] else "N/A"
            n4 = f"{r['notpin_4kb']:.4f}" if r['notpin_4kb'] else "N/A"
            n2 = f"{r['notpin_2mb']:.4f}" if r['notpin_2mb'] else "N/A"
            print(f"{error_rate:<8} {p4:<10} {p2:<10} {n4:<12} {n2:<12}")

if __name__ == "__main__":
    main()
