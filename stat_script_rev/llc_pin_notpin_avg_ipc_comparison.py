#!/usr/bin/env python3
"""Pin vs Not-Pin GMEAN IPC comparison (real_final_spec)."""

import os
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt

from common_real_final import load_records, extract_ipc

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_CSV = os.path.join(SCRIPT_DIR, "llc_pin_notpin_avg_ipc_comparison.csv")
OUTPUT_PNG = os.path.join(SCRIPT_DIR, "llc_pin_notpin_avg_ipc_comparison.png")
ERROR_RATES = ["1e-6", "1e-7", "1e-8", "1e-9"]
PAGES = ["4kb", "2mb"]
LLC_MB = 2


def gmean(values):
    vals = [v for v in values if v and v > 0]
    if not vals:
        return 0.0
    return float(np.exp(np.mean(np.log(vals))))


def collect(ipc_by, pinning: bool):
    out = {p: {e: [] for e in ERROR_RATES} for p in PAGES}
    for (_, p, e, pin), v in ipc_by.items():
        if pin == pinning and e in ERROR_RATES and p in PAGES and v is not None:
            out[p][e].append(v)
    return out


def main():
    recs = [r for r in load_records() if r.llc_mb == LLC_MB and (r.error_rate in ERROR_RATES or r.error_rate is None)]

    ipc_by = {}
    baseline = {p: [] for p in PAGES}
    for r in recs:
        ipc = extract_ipc(r.path)
        if ipc is None:
            continue
        if r.error_rate is None and r.page in PAGES:
            baseline[r.page].append(ipc)
            continue
        ipc_by[(r.workload, r.page, r.error_rate, r.pinning)] = ipc

    pin = collect(ipc_by, True)
    notpin = collect(ipc_by, False)

    rows = []
    for e in ERROR_RATES:
        rows.append({
            "MTBCE": e,
            "Baseline_4KB": gmean(baseline["4kb"]) if baseline["4kb"] else None,
            "Baseline_2MB": gmean(baseline["2mb"]) if baseline["2mb"] else None,
            "Pin_4KB": gmean(pin["4kb"][e]) if pin["4kb"][e] else None,
            "Pin_2MB": gmean(pin["2mb"][e]) if pin["2mb"][e] else None,
            "NotPin_4KB": gmean(notpin["4kb"][e]) if notpin["4kb"][e] else None,
            "NotPin_2MB": gmean(notpin["2mb"][e]) if notpin["2mb"][e] else None,
        })

    df = pd.DataFrame(rows)
    df.to_csv(OUTPUT_CSV, index=False)

    x = np.arange(len(ERROR_RATES))
    bw = 0.14
    fig, ax = plt.subplots(figsize=(10, 2.8))

    ax.bar(x - 2.5*bw, df["Baseline_4KB"], bw, label="Baseline 4KB", color="#9E9E9E", edgecolor="black", linewidth=0.3, alpha=0.9)
    ax.bar(x - 1.5*bw, df["NotPin_4KB"], bw, label="NotPin 4KB", color="#922B21", edgecolor="black", linewidth=0.3)
    ax.bar(x - 0.5*bw, df["Pin_4KB"], bw, label="Pin 4KB", color="#F1948A", edgecolor="black", linewidth=0.3)
    ax.bar(x + 0.5*bw, df["Baseline_2MB"], bw, label="Baseline 2MB", color="#BDBDBD", edgecolor="black", linewidth=0.3, alpha=0.9)
    ax.bar(x + 1.5*bw, df["NotPin_2MB"], bw, label="NotPin 2MB", color="#1A5276", edgecolor="black", linewidth=0.3)
    ax.bar(x + 2.5*bw, df["Pin_2MB"], bw, label="Pin 2MB", color="#7FB3D5", edgecolor="black", linewidth=0.3)

    ax.set_ylabel("IPC (GMEAN)", fontsize=8)
    ax.set_xticks(x)
    ax.set_xticklabels(ERROR_RATES, fontsize=7)
    ax.tick_params(axis='y', labelsize=6)
    ax.yaxis.grid(True, linestyle='--', alpha=0.5, linewidth=0.5)
    ax.set_axisbelow(True)
    ax.legend(loc='upper right', fontsize=6, ncol=3, framealpha=0.9)
    plt.tight_layout(pad=0.3)
    plt.savefig(OUTPUT_PNG, dpi=300, bbox_inches='tight', facecolor='white', edgecolor='none')
    plt.close()

    print(f"CSV saved: {OUTPUT_CSV}")
    print(f"PNG saved: {OUTPUT_PNG}")


if __name__ == "__main__":
    main()
