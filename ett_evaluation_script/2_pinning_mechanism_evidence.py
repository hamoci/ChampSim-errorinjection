#!/usr/bin/env python3
"""
Fig 2: Pinning mechanism evidence — Error Way Hit Rate & Occupancy.
Shows *why* pinning helps: high hit rate = DRAM re-access avoided,
low occupancy = negligible capacity cost.
"""

import os
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

from common_ett import load_err_sweep, gmean

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_CSV = os.path.join(SCRIPT_DIR, "2_pinning_mechanism_evidence.csv")
OUTPUT_PNG = os.path.join(SCRIPT_DIR, "2_pinning_mechanism_evidence.png")

ERROR_RATES = ["1e-8", "1e-7", "1e-6", "1e-5"]


def main():
    recs = [r for r in load_err_sweep() if r["pinning"]]

    rows = []
    for r in recs:
        m = r["metrics"]
        rows.append({
            "Workload": r["workload"],
            "Error_Rate": r["error_rate"],
            "Err_Way_Hit_Rate": m.err_way_hit_rate,
            "Err_Way_Used_Pct": m.err_way_used_pct,
            "Err_Way_Hits": m.err_way_hits,
            "Err_Way_Fills": m.err_way_fills,
            "Err_Way_Evictions": m.err_way_evictions,
            "Total_Errors": m.total_errors,
        })

    if not rows:
        print("No pinning-on data found")
        return

    df = pd.DataFrame(rows)
    df.to_csv(OUTPUT_CSV, index=False)

    workloads = sorted(df["Workload"].unique())

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 5), sharex=True)

    # ── Top: Error Way Hit Rate ──
    for idx, er in enumerate(ERROR_RATES):
        sub = df[df["Error_Rate"] == er].set_index("Workload")
        vals = [sub.loc[w, "Err_Way_Hit_Rate"] if w in sub.index else 0 for w in workloads]
        vals.append(np.mean([v for v in vals if v > 0]) if any(v > 0 for v in vals) else 0)
        x = np.arange(len(workloads) + 1)
        width = 0.18
        offset = (idx - len(ERROR_RATES) / 2 + 0.5) * width
        ax1.bar(x + offset, vals, width, label=er, edgecolor="black", linewidth=0.3)

    ax1.set_ylabel("Error Way Hit Rate (%)", fontsize=8)
    ax1.set_title("Error Way Hit Rate (pinning ON)", fontsize=9, fontweight="bold")
    ax1.set_ylim(0, 105)
    ax1.yaxis.grid(True, linestyle="--", alpha=0.5, linewidth=0.5)
    ax1.set_axisbelow(True)
    ax1.legend(title="Error Rate", fontsize=6, title_fontsize=7, loc="lower right")
    ax1.axvline(x=len(workloads) - 0.5, color="gray", linestyle=":", linewidth=0.8)

    # ── Bottom: Error Way Occupancy ──
    for idx, er in enumerate(ERROR_RATES):
        sub = df[df["Error_Rate"] == er].set_index("Workload")
        vals = [sub.loc[w, "Err_Way_Used_Pct"] if w in sub.index else 0 for w in workloads]
        vals.append(np.mean([v for v in vals if v > 0]) if any(v > 0 for v in vals) else 0)
        x = np.arange(len(workloads) + 1)
        width = 0.18
        offset = (idx - len(ERROR_RATES) / 2 + 0.5) * width
        ax2.bar(x + offset, vals, width, label=er, edgecolor="black", linewidth=0.3)

    labels = workloads + ["AVG"]
    ax2.set_ylabel("Error Way Occupancy (%)", fontsize=8)
    ax2.set_title("Error Way Occupancy (pinning ON)", fontsize=9, fontweight="bold")
    ax2.set_xticks(np.arange(len(labels)))
    ax2.set_xticklabels(labels, rotation=45, ha="right", fontsize=6)
    ax2.yaxis.grid(True, linestyle="--", alpha=0.5, linewidth=0.5)
    ax2.set_axisbelow(True)
    ax2.axvline(x=len(workloads) - 0.5, color="gray", linestyle=":", linewidth=0.8)

    plt.tight_layout(pad=0.5)
    plt.savefig(OUTPUT_PNG, dpi=300, bbox_inches="tight", facecolor="white", edgecolor="none")
    plt.close()

    print(f"CSV saved: {OUTPUT_CSV}")
    print(f"PNG saved: {OUTPUT_PNG}")


if __name__ == "__main__":
    main()
