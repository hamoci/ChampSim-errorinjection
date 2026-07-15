#!/usr/bin/env python3
"""
ETT Entry Sensitivity — Per-Workload with Error Way metrics.

4-panel figure at 1e-8:
  1. IPC per workload
  2. ETT Evictions per workload
  3. Error Way Evictions per workload
  4. Error Way Hits per workload
"""

import os
import re
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
BASE_DIR = os.path.dirname(SCRIPT_DIR)
RESULTS_DIR = os.path.join(BASE_DIR, "results", "ett_evaluation", "2_ett_sensitivity")
OUTPUT_PNG = os.path.join(SCRIPT_DIR, "3c_ett_entry_with_errway.png")
OUTPUT_CSV = os.path.join(SCRIPT_DIR, "3c_ett_entry_with_errway.csv")

ENTRY_COUNTS = [1, 4, 8, 16, 32, 64, 128, 256]
TARGET_RATES = ["1e-8"]

# Regex patterns
RE_FNAME = re.compile(r"^ett_sens_entries_(\d+)_(1e-\d+)_(.+)\.txt$")
RE_IPC = re.compile(r"CPU 0 cumulative IPC:\s+([\d.]+)")
RE_ETT_EVICTIONS = re.compile(r"ETT Evictions:\s+(\d+)")
RE_ERRWAY_EVICTIONS = re.compile(r"Error Way Evictions.*?:\s+(\d+)")
RE_ERRWAY_HITS = re.compile(r"Error Way Hits:\s+(\d+)")
RE_ERRWAY_FILLS = re.compile(r"Error Way Fills.*?:\s+(\d+)")
RE_WORKLOAD = re.compile(r"^(\d+\.\w+)")


def parse_file(path):
    with open(path) as f:
        txt = f.read()
    result = {}
    for name, regex in [("IPC", RE_IPC), ("ETT_Evictions", RE_ETT_EVICTIONS),
                         ("ErrWay_Evictions", RE_ERRWAY_EVICTIONS),
                         ("ErrWay_Hits", RE_ERRWAY_HITS),
                         ("ErrWay_Fills", RE_ERRWAY_FILLS)]:
        m = regex.search(txt)
        result[name] = float(m.group(1)) if m else None
    return result


def main():
    rows = []
    for fname in sorted(os.listdir(RESULTS_DIR)):
        m = RE_FNAME.match(fname)
        if not m:
            continue
        entries = int(m.group(1))
        rate = m.group(2)
        trace = m.group(3)
        if rate not in TARGET_RATES or entries not in ENTRY_COUNTS:
            continue
        wl_m = RE_WORKLOAD.match(trace)
        workload = wl_m.group(1) if wl_m else trace

        metrics = parse_file(os.path.join(RESULTS_DIR, fname))
        rows.append({"Workload": workload, "Entries": entries, "Error_Rate": rate, **metrics})

    df = pd.DataFrame(rows)
    df.to_csv(OUTPUT_CSV, index=False)

    if df.empty:
        print("No data found")
        return

    existing_entries = sorted(df["Entries"].unique())
    entries = [e for e in ENTRY_COUNTS if e in existing_entries]
    workloads = sorted(df["Workload"].unique())
    short_names = [w.split(".")[1].replace("_s", "") for w in workloads]

    COLORS = ["#E74C3C", "#E67E22", "#F1C40F", "#2ECC71", "#1ABC9C", "#3498DB", "#9B59B6", "#34495E"]

    fig, axes = plt.subplots(4, 1, figsize=(14, 12))
    n_entries = len(entries)
    n_wl = len(workloads)
    x = np.arange(n_wl)
    total_width = 0.85
    bar_width = total_width / n_entries

    panels = [
        ("IPC", "IPC", False),
        ("ETT_Evictions", "ETT Evictions", True),
        ("ErrWay_Evictions", "Error Way Evictions", True),
        ("ErrWay_Hits", "Error Way Hits", True),
    ]

    for ax, (col, ylabel, is_int) in zip(axes, panels):
        for idx, ent in enumerate(entries):
            vals = []
            for wl in workloads:
                row = df[(df["Workload"] == wl) & (df["Entries"] == ent)]
                if len(row) > 0 and pd.notna(row[col].values[0]):
                    vals.append(row[col].values[0])
                else:
                    vals.append(0)
            offset = (idx - n_entries / 2 + 0.5) * bar_width
            ax.bar(x + offset, vals, bar_width, label=f"{ent}",
                   color=COLORS[idx % len(COLORS)], edgecolor="black", linewidth=0.3)

        ax.set_ylabel(ylabel, fontsize=10)
        ax.set_xticks(x)
        ax.set_xticklabels(short_names, fontsize=8)
        ax.legend(title="ETT Entries", fontsize=6, title_fontsize=7, loc="upper right", ncol=4)
        ax.yaxis.grid(True, linestyle="--", alpha=0.5, linewidth=0.5)
        ax.set_axisbelow(True)
        ax.tick_params(axis="y", labelsize=8)

    axes[0].set_title("ETT Entry Sensitivity — Per Workload (Error Rate = 1e-8)", fontsize=12, fontweight="bold")

    plt.tight_layout(pad=0.8)
    plt.savefig(OUTPUT_PNG, dpi=300, bbox_inches="tight", facecolor="white", edgecolor="none")
    plt.close()
    print(f"CSV: {OUTPUT_CSV}")
    print(f"PNG: {OUTPUT_PNG}")


if __name__ == "__main__":
    main()
