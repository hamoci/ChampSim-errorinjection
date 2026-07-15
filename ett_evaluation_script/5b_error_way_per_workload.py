#!/usr/bin/env python3
"""
Fig 5b: Error Way Capacity — Per-Workload IPC breakdown.

2-panel figure per error rate:
  Top:    Per-workload IPC grouped bar chart (one group per workload, one bar per max ways)
  Bottom: Per-workload Error Way Evictions
"""

import os
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
INPUT_CSV = os.path.join(SCRIPT_DIR, "5_error_way_capacity.csv")
OUTPUT_PNG = os.path.join(SCRIPT_DIR, "5b_error_way_per_workload.png")

TARGET_RATES = [1e-8, 1e-7, 1e-6, 1e-5]
WAYS = [1, 4, 8]
COLORS = ["#E74C3C", "#3498DB", "#2ECC71"]


def make_panels(df, rate, axes_row, rate_label):
    ax_ipc, ax_evict = axes_row

    df_rate = df[np.isclose(df["Error_Rate"], rate)].copy()
    if df_rate.empty:
        for ax in axes_row:
            ax.text(0.5, 0.5, "No data", ha="center", va="center", transform=ax.transAxes)
        return

    existing_ways = sorted(df_rate["Max_Ways"].unique())
    ways = [w for w in WAYS if w in existing_ways]
    if not ways:
        return

    workloads = sorted(df_rate["Workload"].unique())
    short_names = [w.split(".")[1].replace("_s", "") for w in workloads]
    n_wl = len(workloads)
    n_ways = len(ways)
    x = np.arange(n_wl)
    total_width = 0.85
    bar_width = total_width / n_ways

    # IPC
    for idx, w in enumerate(ways):
        ipcs = []
        for wl in workloads:
            row = df_rate[(df_rate["Workload"] == wl) & (df_rate["Max_Ways"] == w)]
            if len(row) > 0 and pd.notna(row["IPC"].values[0]):
                ipcs.append(row["IPC"].values[0])
            else:
                ipcs.append(0)
        offset = (idx - n_ways / 2 + 0.5) * bar_width
        ax_ipc.bar(x + offset, ipcs, bar_width, label=f"{w} ways",
                   color=COLORS[idx % len(COLORS)], edgecolor="black", linewidth=0.3)

    ax_ipc.set_ylabel("IPC", fontsize=10)
    ax_ipc.set_title(f"Error Way Capacity — Per Workload ({rate_label})",
                     fontsize=11, fontweight="bold")
    ax_ipc.set_xticks(x)
    ax_ipc.set_xticklabels(short_names, fontsize=8, rotation=0)
    ax_ipc.legend(title="Max Ways", fontsize=7, title_fontsize=8, loc="upper right", ncol=3)
    ax_ipc.yaxis.grid(True, linestyle="--", alpha=0.5, linewidth=0.5)
    ax_ipc.set_axisbelow(True)
    ax_ipc.tick_params(axis="y", labelsize=8)

    # Evictions
    for idx, w in enumerate(ways):
        evicts = []
        for wl in workloads:
            row = df_rate[(df_rate["Workload"] == wl) & (df_rate["Max_Ways"] == w)]
            if len(row) > 0 and pd.notna(row["Err_Way_Evictions"].values[0]):
                evicts.append(row["Err_Way_Evictions"].values[0])
            else:
                evicts.append(0)
        offset = (idx - n_ways / 2 + 0.5) * bar_width
        ax_evict.bar(x + offset, evicts, bar_width, label=f"{w} ways",
                     color=COLORS[idx % len(COLORS)], edgecolor="black", linewidth=0.3)

    ax_evict.set_ylabel("Error Way Evictions", fontsize=10)
    ax_evict.set_xticks(x)
    ax_evict.set_xticklabels(short_names, fontsize=8, rotation=0)
    ax_evict.legend(title="Max Ways", fontsize=7, title_fontsize=8, loc="upper right", ncol=3)
    ax_evict.yaxis.grid(True, linestyle="--", alpha=0.5, linewidth=0.5)
    ax_evict.set_axisbelow(True)
    ax_evict.tick_params(axis="y", labelsize=8)


def main():
    df = pd.read_csv(INPUT_CSV)

    # Filter to only error rates that exist in data
    existing_rates = sorted(df["Error_Rate"].unique())
    rates = [r for r in TARGET_RATES if r in existing_rates]
    if not rates:
        # Try string matching
        existing_rate_strs = [str(r) for r in existing_rates]
        for r in TARGET_RATES:
            if f"{r}" in existing_rate_strs or f"{r:.0e}" in existing_rate_strs:
                rates.append(r)
    if not rates:
        print(f"No matching error rates. Available: {existing_rates}")
        return

    n_rates = len(rates)
    fig, axes = plt.subplots(n_rates * 2, 1, figsize=(14, 5 * n_rates))
    if n_rates == 1:
        axes = np.array([axes]).flatten() if n_rates * 2 == 1 else axes

    for i, rate in enumerate(rates):
        exp = int(-np.log10(rate))
        rate_label = f"BER = $10^{{-{exp}}}$"
        make_panels(df, rate, axes[i*2 : i*2+2], rate_label)

    plt.tight_layout(pad=0.8)
    plt.savefig(OUTPUT_PNG, dpi=300, bbox_inches="tight", facecolor="white", edgecolor="none")
    plt.close()
    print(f"PNG saved: {OUTPUT_PNG}")


if __name__ == "__main__":
    main()
