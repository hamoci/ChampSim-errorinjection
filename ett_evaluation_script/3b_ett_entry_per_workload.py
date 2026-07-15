#!/usr/bin/env python3
"""
ETT Entry Sensitivity — Per-Workload IPC breakdown.

2-panel figure:
  Top:    Per-workload IPC grouped bar chart (one group per workload, one bar per entry count) at 1e-8
  Bottom: Per-workload ETT Evictions at 1e-8
"""

import os
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
INPUT_CSV = os.path.join(SCRIPT_DIR, "3_ett_entry_sensitivity.csv")
OUTPUT_PNG = os.path.join(SCRIPT_DIR, "3b_ett_entry_per_workload.png")

TARGET_RATE = 1e-8
ENTRY_COUNTS = [1, 4, 8, 16, 32, 64, 128, 256]
COLORS = ["#E74C3C", "#E67E22", "#F1C40F", "#2ECC71", "#1ABC9C", "#3498DB", "#9B59B6", "#34495E"]


def main():
    df = pd.read_csv(INPUT_CSV)
    df = df[df["Error_Rate"] == TARGET_RATE].copy()

    if df.empty:
        print(f"No data for {TARGET_RATE}")
        return

    # Filter to only entry counts that exist in data
    existing_entries = sorted(df["Entries"].unique())
    entries = [e for e in ENTRY_COUNTS if e in existing_entries]
    if not entries:
        print("No matching entry counts")
        return

    workloads = sorted(df["Workload"].unique())
    short_names = [w.split(".")[1].replace("_s", "") for w in workloads]

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(14, 7))

    n_entries = len(entries)
    n_wl = len(workloads)
    x = np.arange(n_wl)
    total_width = 0.85
    bar_width = total_width / n_entries

    # ── Top: IPC per workload ──
    for idx, ent in enumerate(entries):
        ipcs = []
        for wl in workloads:
            row = df[(df["Workload"] == wl) & (df["Entries"] == ent)]
            ipcs.append(row["IPC"].values[0] if len(row) > 0 and pd.notna(row["IPC"].values[0]) else 0)
        offset = (idx - n_entries / 2 + 0.5) * bar_width
        ax1.bar(x + offset, ipcs, bar_width, label=f"{ent}",
                color=COLORS[idx % len(COLORS)], edgecolor="black", linewidth=0.3)

    ax1.set_ylabel("IPC", fontsize=10)
    ax1.set_title(f"ETT Entry Sensitivity — Per Workload (Error Rate = {TARGET_RATE})", fontsize=11, fontweight="bold")
    ax1.set_xticks(x)
    ax1.set_xticklabels(short_names, fontsize=8, rotation=0)
    ax1.legend(title="ETT Entries", fontsize=7, title_fontsize=8, loc="upper right", ncol=4)
    ax1.yaxis.grid(True, linestyle="--", alpha=0.5, linewidth=0.5)
    ax1.set_axisbelow(True)
    ax1.tick_params(axis="y", labelsize=8)

    # ── Bottom: ETT Evictions per workload ──
    for idx, ent in enumerate(entries):
        evicts = []
        for wl in workloads:
            row = df[(df["Workload"] == wl) & (df["Entries"] == ent)]
            val = row["ETT_Evictions"].values[0] if len(row) > 0 and pd.notna(row["ETT_Evictions"].values[0]) else 0
            evicts.append(val)
        offset = (idx - n_entries / 2 + 0.5) * bar_width
        ax2.bar(x + offset, evicts, bar_width, label=f"{ent}",
                color=COLORS[idx % len(COLORS)], edgecolor="black", linewidth=0.3)

    ax2.set_ylabel("ETT Evictions", fontsize=10)
    ax2.set_title(f"ETT Evictions — Per Workload (Error Rate = {TARGET_RATE})", fontsize=11, fontweight="bold")
    ax2.set_xticks(x)
    ax2.set_xticklabels(short_names, fontsize=8, rotation=0)
    ax2.legend(title="ETT Entries", fontsize=7, title_fontsize=8, loc="upper right", ncol=4)
    ax2.yaxis.grid(True, linestyle="--", alpha=0.5, linewidth=0.5)
    ax2.set_axisbelow(True)
    ax2.tick_params(axis="y", labelsize=8)

    plt.tight_layout(pad=1.0)
    plt.savefig(OUTPUT_PNG, dpi=300, bbox_inches="tight", facecolor="white", edgecolor="none")
    plt.close()
    print(f"PNG saved: {OUTPUT_PNG}")


if __name__ == "__main__":
    main()
