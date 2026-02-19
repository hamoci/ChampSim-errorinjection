#!/usr/bin/env python3
"""IPC comparison across MTBCE for no-cache-pinning runs (real_final_spec)."""

import os
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt

from common_real_final import load_records, extract_ipc

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_CSV = os.path.join(SCRIPT_DIR, "llc_notpin_ipc_comparison.csv")
OUTPUT_PNG = os.path.join(SCRIPT_DIR, "llc_notpin_ipc_comparison.png")
ERROR_RATES = ["1e-6", "1e-7", "1e-8", "1e-9"]
PAGES = ["4kb", "2mb"]
LLC_MB = 2


def gmean(values):
    vals = [v for v in values if v and v > 0]
    if not vals:
        return 0.0
    return float(np.exp(np.mean(np.log(vals))))


def main():
    recs = [r for r in load_records() if r.llc_mb == LLC_MB and (r.error_rate in ERROR_RATES or r.error_rate is None)]

    data = {}
    baseline = {}
    for r in recs:
        ipc = extract_ipc(r.path)
        if ipc is None:
            continue
        if r.error_rate is None:
            baseline.setdefault(r.workload, {})[r.page] = ipc
            continue
        if r.pinning:
            continue
        data.setdefault(r.workload, {p: {e: None for e in ERROR_RATES} for p in PAGES})
        data[r.workload][r.page][r.error_rate] = ipc

    workloads = sorted(data.keys())

    rows = []
    for w in workloads:
        row = {"Workload": w}
        row["4kb_baseline"] = baseline.get(w, {}).get("4kb")
        row["2mb_baseline"] = baseline.get(w, {}).get("2mb")
        for p in PAGES:
            for e in ERROR_RATES:
                row[f"{p}_{e}"] = data[w][p][e]
        rows.append(row)
    pd.DataFrame(rows).to_csv(OUTPUT_CSV, index=False)

    if not workloads:
        print("No non-pinning records found")
        return

    x_base = np.arange(len(workloads))
    bar_width = 0.09
    group_width = bar_width * (len(ERROR_RATES) * 2 + 2) + 0.15
    x_positions = x_base * group_width

    fig, ax = plt.subplots(figsize=(14, 3))
    c4 = ['#FADBD8', '#F1948A', '#E74C3C', '#922B21']
    c2 = ['#D4E6F1', '#7FB3D5', '#2980B9', '#1A5276']

    for i, w in enumerate(workloads):
        idx = 0
        b4 = baseline.get(w, {}).get("4kb")
        if b4 is not None:
            ax.bar(x_positions[i] + idx * bar_width, b4, bar_width, color='#9E9E9E', edgecolor='black', linewidth=0.3)
        idx += 1
        for j, e in enumerate(ERROR_RATES):
            v = data[w]["4kb"][e]
            if v is not None:
                ax.bar(x_positions[i] + idx * bar_width, v, bar_width, color=c4[j], edgecolor='black', linewidth=0.3)
            idx += 1
        b2 = baseline.get(w, {}).get("2mb")
        if b2 is not None:
            ax.bar(x_positions[i] + idx * bar_width, b2, bar_width, color='#BDBDBD', edgecolor='black', linewidth=0.3)
        idx += 1
        for j, e in enumerate(ERROR_RATES):
            v = data[w]["2mb"][e]
            if v is not None:
                ax.bar(x_positions[i] + idx * bar_width, v, bar_width, color=c2[j], edgecolor='black', linewidth=0.3)
            idx += 1

    legend = []
    legend.append(plt.Rectangle((0, 0), 1, 1, facecolor='#9E9E9E', edgecolor='black', linewidth=0.3, label='4KB baseline'))
    for j, e in enumerate(ERROR_RATES):
        legend.append(plt.Rectangle((0, 0), 1, 1, facecolor=c4[j], edgecolor='black', linewidth=0.3, label=f'4KB {e}'))
    legend.append(plt.Rectangle((0, 0), 1, 1, facecolor='#BDBDBD', edgecolor='black', linewidth=0.3, label='2MB baseline'))
    for j, e in enumerate(ERROR_RATES):
        legend.append(plt.Rectangle((0, 0), 1, 1, facecolor=c2[j], edgecolor='black', linewidth=0.3, label=f'2MB {e}'))
    ax.legend(handles=legend, loc='upper right', fontsize=5, ncol=5, framealpha=0.9)

    ax.set_ylabel('IPC', fontsize=8)
    ax.set_xticks(x_positions + ((len(ERROR_RATES) * 2 + 2) / 2 - 0.5) * bar_width)
    ax.set_xticklabels(workloads, rotation=45, ha='right', fontsize=5)
    ax.tick_params(axis='y', labelsize=6)
    ax.yaxis.grid(True, linestyle='--', alpha=0.5, linewidth=0.5)
    ax.set_axisbelow(True)
    ax.set_xlim(-0.1, x_positions[-1] + (len(ERROR_RATES) * 2 + 2) * bar_width + 0.1)
    plt.tight_layout(pad=0.3)
    plt.savefig(OUTPUT_PNG, dpi=300, bbox_inches='tight', facecolor='white', edgecolor='none')
    plt.close()

    print(f"CSV saved: {OUTPUT_CSV}")
    print(f"PNG saved: {OUTPUT_PNG}")

    for e in ERROR_RATES:
        vals4 = [data[w]["4kb"][e] for w in workloads if data[w]["4kb"][e] is not None]
        vals2 = [data[w]["2mb"][e] for w in workloads if data[w]["2mb"][e] is not None]
        if vals4 and vals2:
            print(f"{e}: 4KB gmean={gmean(vals4):.4f}, 2MB gmean={gmean(vals2):.4f}")


if __name__ == "__main__":
    main()
