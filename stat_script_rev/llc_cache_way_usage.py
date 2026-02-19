#!/usr/bin/env python3
"""LLC error-way usage analysis for cache-pinning runs (real_final_spec)."""

import os
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt

from common_real_final import load_records, extract_cache_way_stats

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_CSV = os.path.join(SCRIPT_DIR, "llc_cache_way_usage.csv")
OUTPUT_PNG = os.path.join(SCRIPT_DIR, "llc_cache_way_usage.png")
OUTPUT_AVG_CSV = os.path.join(SCRIPT_DIR, "llc_cache_way_usage_avg.csv")
OUTPUT_AVG_PNG = os.path.join(SCRIPT_DIR, "llc_cache_way_usage_avg.png")
ERROR_RATES = ["1e-6", "1e-7", "1e-8", "1e-9"]
PAGES = ["4kb", "2mb"]


def main():
    recs = [r for r in load_records() if r.pinning and r.error_rate in ERROR_RATES]

    rows = []
    for r in recs:
        stat = extract_cache_way_stats(r.path)
        if stat is None:
            continue
        alloc, used = stat
        rows.append({
            "Workload": r.workload,
            "LLC_MB": r.llc_mb,
            "Page": r.page,
            "MTBCE": r.error_rate,
            "AllocatedWays": alloc,
            "UsedPct": used,
        })

    df = pd.DataFrame(rows)
    if df.empty:
        print("No cache-way stats found")
        return

    df.to_csv(OUTPUT_CSV, index=False)

    # Detailed scatter+bar by workload
    workloads = sorted(df["Workload"].unique())
    fig, ax = plt.subplots(figsize=(14, 3.5))
    ax2 = ax.twinx()

    bar_w = 0.1
    group_w = bar_w * 8 + 0.2
    x_base = np.arange(len(workloads)) * group_w

    c4 = ['#FADBD8', '#F1948A', '#E74C3C', '#922B21']
    c2 = ['#D4E6F1', '#7FB3D5', '#2980B9', '#1A5276']

    for i, w in enumerate(workloads):
        idx = 0
        x4, y4, x2, y2 = [], [], [], []
        for j, e in enumerate(ERROR_RATES):
            row = df[(df.Workload == w) & (df.Page == "4kb") & (df.MTBCE == e) & (df.LLC_MB == 2)]
            if not row.empty:
                used = float(row.iloc[0].UsedPct)
                alloc = float(row.iloc[0].AllocatedWays)
                x = x_base[i] + idx * bar_w
                ax.bar(x, used, bar_w, color=c4[j], edgecolor='black', linewidth=0.3)
                x4.append(x); y4.append(alloc)
            idx += 1
        for j, e in enumerate(ERROR_RATES):
            row = df[(df.Workload == w) & (df.Page == "2mb") & (df.MTBCE == e) & (df.LLC_MB == 2)]
            if not row.empty:
                used = float(row.iloc[0].UsedPct)
                alloc = float(row.iloc[0].AllocatedWays)
                x = x_base[i] + idx * bar_w
                ax.bar(x, used, bar_w, color=c2[j], edgecolor='black', linewidth=0.3)
                x2.append(x); y2.append(alloc)
            idx += 1
        if x4:
            ax2.plot(x4, y4, color='#E74C3C', linewidth=1.2)
            ax2.scatter(x4, y4, s=15, color='#E74C3C', edgecolors='black', linewidths=0.3)
        if x2:
            ax2.plot(x2, y2, color='#2980B9', linewidth=1.2)
            ax2.scatter(x2, y2, s=15, color='#2980B9', edgecolors='black', linewidths=0.3)

    ax.set_ylabel('Used Error Way Slots (%)', fontsize=8)
    ax2.set_ylabel('Allocated Error Ways per Set', fontsize=8)
    ax.set_ylim(0, 115)
    ax2.set_ylim(0, max(10, int(df["AllocatedWays"].max()) + 1))
    ax.set_xticks(x_base + 3.5 * bar_w)
    ax.set_xticklabels(workloads, rotation=45, ha='right', fontsize=5)
    ax.tick_params(axis='y', labelsize=6)
    ax2.tick_params(axis='y', labelsize=6)
    ax.yaxis.grid(True, linestyle='--', alpha=0.5, linewidth=0.5)
    ax.set_axisbelow(True)
    plt.tight_layout(pad=0.3)
    plt.savefig(OUTPUT_PNG, dpi=300, bbox_inches='tight', facecolor='white', edgecolor='none')
    plt.close()

    # Average chart by LLC/page/MTBCE
    avg = df.groupby(["LLC_MB", "Page", "MTBCE"], as_index=False).agg({"AllocatedWays": "mean", "UsedPct": "mean"})
    avg.to_csv(OUTPUT_AVG_CSV, index=False)

    fig, ax = plt.subplots(figsize=(9, 3))
    labels = []
    used_vals = []
    alloc_vals = []
    for llc in sorted(avg["LLC_MB"].unique()):
        for p in ["4kb", "2mb"]:
            for e in ERROR_RATES:
                row = avg[(avg.LLC_MB == llc) & (avg.Page == p) & (avg.MTBCE == e)]
                if row.empty:
                    continue
                labels.append(f"{llc}MB\n{p}\n{e}")
                used_vals.append(float(row.iloc[0].UsedPct))
                alloc_vals.append(float(row.iloc[0].AllocatedWays))

    x = np.arange(len(labels))
    ax.bar(x, used_vals, color="#7FB3D5", edgecolor='black', linewidth=0.3)
    ax2 = ax.twinx()
    ax2.plot(x, alloc_vals, color="#E74C3C", marker='o', linewidth=1.2, markersize=3)
    ax.set_ylabel("Used %", fontsize=8)
    ax2.set_ylabel("Alloc ways", fontsize=8)
    ax.set_xticks(x)
    ax.set_xticklabels(labels, fontsize=5)
    ax.tick_params(axis='y', labelsize=6)
    ax2.tick_params(axis='y', labelsize=6)
    ax.yaxis.grid(True, linestyle='--', alpha=0.5, linewidth=0.5)
    ax.set_axisbelow(True)
    plt.tight_layout(pad=0.3)
    plt.savefig(OUTPUT_AVG_PNG, dpi=300, bbox_inches='tight', facecolor='white', edgecolor='none')
    plt.close()

    print(f"CSV saved: {OUTPUT_CSV}")
    print(f"PNG saved: {OUTPUT_PNG}")
    print(f"AVG CSV saved: {OUTPUT_AVG_CSV}")
    print(f"AVG PNG saved: {OUTPUT_AVG_PNG}")


if __name__ == "__main__":
    main()
