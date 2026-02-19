#!/usr/bin/env python3
"""Pin vs Not-Pin IPC per workload (real_final_spec)."""

import os
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt

from common_real_final import load_records, extract_ipc

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_CSV = os.path.join(SCRIPT_DIR, "llc_pin_notpin_individual_ipc.csv")
OUTPUT_SPEC = os.path.join(SCRIPT_DIR, "llc_pin_notpin_individual_ipc_spec.png")
OUTPUT_GAP = os.path.join(SCRIPT_DIR, "llc_pin_notpin_individual_ipc_gap.png")
ERROR_RATES = ["1e-6", "1e-7", "1e-8", "1e-9"]
PAGES = ["4kb", "2mb"]
LLC_MB = 2


def main():
    recs = [r for r in load_records() if r.llc_mb == LLC_MB and r.error_rate in ERROR_RATES]

    data = {}
    rows = []
    for r in recs:
        ipc = extract_ipc(r.path)
        if ipc is None:
            continue
        data.setdefault(r.workload, {p: {e: {True: None, False: None} for e in ERROR_RATES} for p in PAGES})
        data[r.workload][r.page][r.error_rate][r.pinning] = ipc

    workloads = sorted(data.keys())
    for w in workloads:
        for e in ERROR_RATES:
            rows.append({
                "Workload": w,
                "MTBCE": e,
                "Pin_4KB": data[w]["4kb"][e][True],
                "NotPin_4KB": data[w]["4kb"][e][False],
                "Pin_2MB": data[w]["2mb"][e][True],
                "NotPin_2MB": data[w]["2mb"][e][False],
            })

    pd.DataFrame(rows).to_csv(OUTPUT_CSV, index=False)

    if not workloads:
        print("No workload data")
        return

    ncols = 4
    nrows = (len(workloads) + ncols - 1) // ncols
    fig, axes = plt.subplots(nrows, ncols, figsize=(12, 1.9 * nrows))
    axes = np.array(axes).reshape(-1)

    x = np.arange(len(ERROR_RATES))
    bw = 0.18
    for i, w in enumerate(workloads):
        ax = axes[i]
        n4 = [data[w]["4kb"][e][False] or 0 for e in ERROR_RATES]
        p4 = [data[w]["4kb"][e][True] or 0 for e in ERROR_RATES]
        n2 = [data[w]["2mb"][e][False] or 0 for e in ERROR_RATES]
        p2 = [data[w]["2mb"][e][True] or 0 for e in ERROR_RATES]

        ax.bar(x - 1.5*bw, n4, bw, color="#922B21", edgecolor="black", linewidth=0.3)
        ax.bar(x - 0.5*bw, p4, bw, color="#F1948A", edgecolor="black", linewidth=0.3)
        ax.bar(x + 0.5*bw, n2, bw, color="#1A5276", edgecolor="black", linewidth=0.3)
        ax.bar(x + 1.5*bw, p2, bw, color="#7FB3D5", edgecolor="black", linewidth=0.3)
        ax.set_title(w, fontsize=7, fontweight="bold")
        ax.set_xticks(x)
        ax.set_xticklabels(ERROR_RATES, fontsize=5)
        ax.tick_params(axis='y', labelsize=5)
        ax.yaxis.grid(True, linestyle='--', alpha=0.5, linewidth=0.5)
        ax.set_axisbelow(True)

    for i in range(len(workloads), len(axes)):
        axes[i].set_visible(False)

    handles = [
        plt.Rectangle((0, 0), 1, 1, facecolor="#922B21", edgecolor='black', linewidth=0.3, label="NotPin 4KB"),
        plt.Rectangle((0, 0), 1, 1, facecolor="#F1948A", edgecolor='black', linewidth=0.3, label="Pin 4KB"),
        plt.Rectangle((0, 0), 1, 1, facecolor="#1A5276", edgecolor='black', linewidth=0.3, label="NotPin 2MB"),
        plt.Rectangle((0, 0), 1, 1, facecolor="#7FB3D5", edgecolor='black', linewidth=0.3, label="Pin 2MB"),
    ]
    fig.legend(handles=handles, loc='upper center', ncol=4, fontsize=7, bbox_to_anchor=(0.5, 1.01))
    fig.text(0.5, 0.01, "MTBCE", ha="center", fontsize=9)
    fig.text(0.01, 0.5, "IPC", va="center", rotation="vertical", fontsize=9)
    plt.tight_layout(rect=[0.02, 0.02, 1, 0.97])
    plt.savefig(OUTPUT_SPEC, dpi=300, bbox_inches='tight', facecolor='white', edgecolor='none')
    plt.savefig(OUTPUT_GAP, dpi=300, bbox_inches='tight', facecolor='white', edgecolor='none')
    plt.close()

    print(f"CSV saved: {OUTPUT_CSV}")
    print(f"PNG saved: {OUTPUT_SPEC}")


if __name__ == "__main__":
    main()
