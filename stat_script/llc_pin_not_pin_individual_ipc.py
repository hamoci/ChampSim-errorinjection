#!/usr/bin/env python3
"""
LLC Pin vs Not-Pin Individual Workload IPC Comparison Script
Compares IPC between cache pinning and not-pinning for each workload.
- CSV: Individual workload IPC values
- PNG: Subplot grid for each workload
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

def plot_individual_workloads(pin_data, notpin_data, suite_name, output_prefix):
    """Create subplot grid for individual workloads."""
    # Get common workloads
    common_workloads = sorted(set(pin_data.keys()) & set(notpin_data.keys()))

    if not common_workloads:
        print(f"No common workloads found for {suite_name}")
        return None

    num_workloads = len(common_workloads)

    # Calculate grid dimensions
    ncols = 4
    nrows = (num_workloads + ncols - 1) // ncols

    # Create figure (compact size)
    fig, axes = plt.subplots(nrows, ncols, figsize=(12, 1.8 * nrows))

    # Flatten axes for easier indexing
    if nrows == 1:
        axes = axes.reshape(1, -1)
    axes_flat = axes.flatten()

    # Colors (4KB = red tones, 2MB = blue tones)
    colors = {
        'pin_4kb': '#F1948A',      # Light red
        'notpin_4kb': '#922B21',   # Dark red
        'pin_2mb': '#7FB3D5',      # Light blue
        'notpin_2mb': '#1A5276',   # Dark blue
    }

    bar_width = 0.18
    x = np.arange(len(ERROR_RATES))

    # CSV data
    csv_rows = []

    for idx, workload in enumerate(common_workloads):
        ax = axes_flat[idx]

        # Get values for each configuration
        pin_4kb_vals = [pin_data[workload]['4kb'].get(er) or 0 for er in ERROR_RATES]
        pin_2mb_vals = [pin_data[workload]['2mb'].get(er) or 0 for er in ERROR_RATES]
        notpin_4kb_vals = [notpin_data[workload]['4kb'].get(er) or 0 for er in ERROR_RATES]
        notpin_2mb_vals = [notpin_data[workload]['2mb'].get(er) or 0 for er in ERROR_RATES]

        # Draw bars (NotPin first, then Pin) - 4KB group, then 2MB group
        ax.bar(x - 1.5*bar_width, notpin_4kb_vals, bar_width, label='NotPin 4KB',
               color=colors['notpin_4kb'], edgecolor='black', linewidth=0.3)
        bars_pin_4kb = ax.bar(x - 0.5*bar_width, pin_4kb_vals, bar_width, label='Pin 4KB',
               color=colors['pin_4kb'], edgecolor='black', linewidth=0.3)
        ax.bar(x + 0.5*bar_width, notpin_2mb_vals, bar_width, label='NotPin 2MB',
               color=colors['notpin_2mb'], edgecolor='black', linewidth=0.3)
        bars_pin_2mb = ax.bar(x + 1.5*bar_width, pin_2mb_vals, bar_width, label='Pin 2MB',
               color=colors['pin_2mb'], edgecolor='black', linewidth=0.3)

        # Calculate and display IPC change percentage between NotPin and Pin bars
        for i, (bar, pin_val, notpin_val) in enumerate(zip(bars_pin_4kb, pin_4kb_vals, notpin_4kb_vals)):
            if notpin_val > 0 and pin_val > 0:
                pct = (pin_val - notpin_val) / notpin_val * 100
                sign = '+' if pct >= 0 else ''
                # Position between NotPin and Pin bars
                text_x = x[i] - bar_width
                text_y = max(pin_val, notpin_val)
                ax.text(text_x, text_y, f'{sign}{pct:.1f}%',
                        ha='center', va='bottom', fontsize=4)

        for i, (bar, pin_val, notpin_val) in enumerate(zip(bars_pin_2mb, pin_2mb_vals, notpin_2mb_vals)):
            if notpin_val > 0 and pin_val > 0:
                pct = (pin_val - notpin_val) / notpin_val * 100
                sign = '+' if pct >= 0 else ''
                # Position between NotPin and Pin bars
                text_x = x[i] + bar_width
                text_y = max(pin_val, notpin_val)
                ax.text(text_x, text_y, f'{sign}{pct:.1f}%',
                        ha='center', va='bottom', fontsize=4)

        # Customize subplot
        ax.set_title(workload, fontsize=7, fontweight='bold')
        ax.set_xticks(x)
        ax.set_xticklabels(ERROR_RATES, fontsize=5)
        ax.tick_params(axis='y', labelsize=5)
        ax.yaxis.grid(True, linestyle='--', alpha=0.5, linewidth=0.5)
        ax.set_axisbelow(True)

        # Adjust Y-axis to data range (not starting from 0)
        all_vals = [v for v in pin_4kb_vals + pin_2mb_vals + notpin_4kb_vals + notpin_2mb_vals if v > 0]
        if all_vals:
            min_val = min(all_vals)
            max_val = max(all_vals)
            margin = (max_val - min_val) * 0.25  # Extra margin for percentage labels
            ax.set_ylim(min_val - (max_val - min_val) * 0.1, max_val + margin)

        # Add CSV row for each error rate
        for er in ERROR_RATES:
            csv_rows.append({
                'Suite': suite_name,
                'Workload': workload,
                'MTBCE': er,
                'Pin_4KB': pin_data[workload]['4kb'].get(er),
                'Pin_2MB': pin_data[workload]['2mb'].get(er),
                'NotPin_4KB': notpin_data[workload]['4kb'].get(er),
                'NotPin_2MB': notpin_data[workload]['2mb'].get(er),
            })

    # Hide unused subplots
    for idx in range(num_workloads, len(axes_flat)):
        axes_flat[idx].set_visible(False)

    # Add common legend
    handles, labels = axes_flat[0].get_legend_handles_labels()
    fig.legend(handles, labels, loc='upper center', ncol=4, fontsize=7,
               bbox_to_anchor=(0.5, 1.01))

    # Add common labels
    fig.text(0.5, 0.01, 'MTBCE', ha='center', fontsize=9)
    fig.text(0.01, 0.5, 'IPC', va='center', rotation='vertical', fontsize=9)

    plt.suptitle(f'{suite_name} - Individual Workload IPC Comparison (Pin vs Not-Pin)',
                 fontsize=10, fontweight='bold', y=1.03)
    plt.tight_layout(rect=[0.02, 0.02, 1, 0.97])

    # Save plot
    png_path = os.path.join(OUTPUT_DIR, f"{output_prefix}_{suite_name.lower()}.png")
    plt.savefig(png_path, dpi=300, bbox_inches='tight', facecolor='white', edgecolor='none')
    print(f"PNG saved to: {png_path}")
    plt.close()

    return csv_rows

def main():
    # Collect data
    pin_spec = collect_data_pin(PIN_SPEC_DIR, "spec")
    pin_gap = collect_data_pin(PIN_GAP_DIR, "gap")
    notpin_spec = collect_data_notpin(NOTPIN_SPEC_DIR, "spec")
    notpin_gap = collect_data_notpin(NOTPIN_GAP_DIR, "gap")

    print(f"Pin SPEC: {len(pin_spec)}, Pin GAP: {len(pin_gap)}")
    print(f"NotPin SPEC: {len(notpin_spec)}, NotPin GAP: {len(notpin_gap)}")

    all_csv_rows = []

    # Plot SPEC workloads
    csv_rows = plot_individual_workloads(pin_spec, notpin_spec, "SPEC",
                                          "llc_pin_notpin_individual_ipc")
    if csv_rows:
        all_csv_rows.extend(csv_rows)

    # Plot GAP workloads
    csv_rows = plot_individual_workloads(pin_gap, notpin_gap, "GAP",
                                          "llc_pin_notpin_individual_ipc")
    if csv_rows:
        all_csv_rows.extend(csv_rows)

    # Save combined CSV
    if all_csv_rows:
        df = pd.DataFrame(all_csv_rows)
        csv_path = os.path.join(OUTPUT_DIR, "llc_pin_notpin_individual_ipc.csv")
        df.to_csv(csv_path, index=False)
        print(f"CSV saved to: {csv_path}")

    # Print summary
    print("\n=== Summary ===")
    for suite_name, pin_data, notpin_data in [("SPEC", pin_spec, notpin_spec),
                                               ("GAP", pin_gap, notpin_gap)]:
        common_workloads = sorted(set(pin_data.keys()) & set(notpin_data.keys()))
        print(f"\n{suite_name}: {len(common_workloads)} workloads")
        for workload in common_workloads:
            print(f"  - {workload}")

if __name__ == "__main__":
    main()
