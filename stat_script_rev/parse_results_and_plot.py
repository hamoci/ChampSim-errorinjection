#!/usr/bin/env python3
"""Simple IPC comparison plot for baseline vs error (real_final_spec, LLC=2MB)."""

import os
import numpy as np
import matplotlib.pyplot as plt

from common_real_final import load_records, extract_ipc

OUT_MAIN = "/home/hamoci/Study/ChampSim/results/performance_comparison.png"
OUT_DETAIL = "/home/hamoci/Study/ChampSim/results/detailed_comparison.png"


def main():
    recs = [r for r in load_records() if r.llc_mb == 2]

    # use 1e-6 as representative error point for compact comparison
    data = {}
    for r in recs:
        ipc = extract_ipc(r.path)
        if ipc is None:
            continue

        cfg = None
        if r.error_rate is None and r.page == "4kb":
            cfg = "4KB"
        elif r.error_rate is None and r.page == "2mb":
            cfg = "2MB"
        elif r.error_rate == "1e-6" and r.page == "4kb":
            cfg = "4KB Error"
        elif r.error_rate == "1e-6" and r.page == "2mb":
            cfg = "2MB Error"

        if cfg is None:
            continue
        data.setdefault(r.workload, {})[cfg] = ipc

    workloads = sorted(data.keys())
    if not workloads:
        print("No data to plot")
        return

    cfgs = ["4KB", "4KB Error", "2MB", "2MB Error"]
    colors = ['#648FFF', '#785EF0', '#DC267F', '#FE6100']

    plt.figure(figsize=(10, 7))
    plt.subplot(2, 1, 1)
    x = np.arange(len(workloads))
    width = 0.18
    for i, cfg in enumerate(cfgs):
        y = [data[w].get(cfg, 0) for w in workloads]
        plt.bar(x + i * width, y, width, label=cfg, color=colors[i], alpha=0.8)
    plt.ylabel('IPC', fontweight='bold', fontsize=14)
    plt.xticks(x + width * 1.5, workloads, rotation=45, ha='right', fontsize=8)
    plt.legend(ncol=2, loc='upper right', fontsize=8)
    plt.grid(True, alpha=0.3)

    plt.subplot(2, 1, 2)
    imp4 = []
    imp2 = []
    for w in workloads:
        b4, e4 = data[w].get("4KB", 0), data[w].get("4KB Error", 0)
        b2, e2 = data[w].get("2MB", 0), data[w].get("2MB Error", 0)
        imp4.append(abs((e4 - b4) / b4 * 100) if b4 > 0 else 0)
        imp2.append(abs((e2 - b2) / b2 * 100) if b2 > 0 else 0)

    plt.bar(x - 0.15, imp4, 0.3, label='4KB Error Impact', color='#FE6100', alpha=0.8)
    plt.bar(x + 0.15, imp2, 0.3, label='2MB Error Impact', color='#FFB000', alpha=0.8)
    plt.ylabel('Performance Impact (%)', fontweight='bold', fontsize=14)
    plt.xticks(x, workloads, rotation=45, ha='right', fontsize=8)
    plt.legend(loc='upper right', fontsize=8)
    plt.grid(True, alpha=0.3)

    plt.tight_layout(pad=1.2)
    os.makedirs(os.path.dirname(OUT_MAIN), exist_ok=True)
    plt.savefig(OUT_MAIN, dpi=300, bbox_inches='tight', facecolor='white', edgecolor='none')
    plt.close()

    # detail: first 10 workloads
    fig, axes = plt.subplots(2, 5, figsize=(14, 7))
    axes = axes.flatten()
    for idx, w in enumerate(workloads[:10]):
        ax = axes[idx]
        keys = [k for k in cfgs if k in data[w]]
        vals = [data[w][k] for k in keys]
        ax.bar(keys, vals, color=[colors[cfgs.index(k)] for k in keys], alpha=0.8)
        ax.set_title(w, fontsize=10)
        ax.tick_params(axis='x', rotation=45, labelsize=7)
        ax.tick_params(axis='y', labelsize=7)
        ax.grid(True, alpha=0.3)
    for idx in range(len(workloads[:10]), len(axes)):
        axes[idx].set_visible(False)
    plt.tight_layout(pad=1.2)
    plt.savefig(OUT_DETAIL, dpi=300, bbox_inches='tight', facecolor='white', edgecolor='none')
    plt.close()

    print(f"PNG saved: {OUT_MAIN}")
    print(f"PNG saved: {OUT_DETAIL}")


if __name__ == "__main__":
    main()
