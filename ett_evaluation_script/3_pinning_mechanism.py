#!/usr/bin/env python3
"""
Fig 3: Why Pinning Works — Error Way Hit Rate & Occupancy.

2-panel figure (pinning ON data only):
  Top:    Per-workload Error Way Hit Rate (%) at each BER
  Bottom: Per-workload Error Way Occupancy (%) at each BER

Key message: 50-90% of error-data accesses are served from LLC (not DRAM),
while consuming only 1-15% of LLC capacity.
"""

import os
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

from common_ett import load_err_sweep

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_CSV = os.path.join(SCRIPT_DIR, "fig3_mechanism.csv")
OUTPUT_PNG = os.path.join(SCRIPT_DIR, "fig3_mechanism.png")

ERROR_RATES = ["1e-5", "1e-6", "1e-7", "1e-8"]
COLORS = ["#2ECC71", "#F5A623", "#EE5A6F", "#4A90E2"]


def main():
    recs = [r for r in load_err_sweep() if r["pinning"]]

    rows = []
    for r in recs:
        m = r["metrics"]
        rows.append({
            "Workload": r["workload"], "Error_Rate": r["error_rate"],
            "Hit_Rate": m.err_way_hit_rate, "Occupancy": m.err_way_used_pct,
            "Hits": m.err_way_hits, "Fills": m.err_way_fills,
        })

    if not rows:
        print("No pinning-on data")
        return

    df = pd.DataFrame(rows)
    df.to_csv(OUTPUT_CSV, index=False)

    workloads = sorted(df["Workload"].unique())

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 4.5), sharex=True)

    x = np.arange(len(workloads) + 1)  # +1 for AVG
    n_rates = len(ERROR_RATES)
    width = 0.8 / n_rates

    for idx, er in enumerate(ERROR_RATES):
        sub = df[df["Error_Rate"] == er].set_index("Workload")

        # Hit Rate
        vals_hr = [sub.loc[w, "Hit_Rate"] if w in sub.index and pd.notna(sub.loc[w, "Hit_Rate"]) else 0
                    for w in workloads]
        valid_hr = [v for v in vals_hr if v > 0]
        vals_hr.append(np.mean(valid_hr) if valid_hr else 0)

        # Occupancy
        vals_oc = [sub.loc[w, "Occupancy"] if w in sub.index and pd.notna(sub.loc[w, "Occupancy"]) else 0
                    for w in workloads]
        valid_oc = [v for v in vals_oc if v > 0]
        vals_oc.append(np.mean(valid_oc) if valid_oc else 0)

        offset = (idx - n_rates / 2 + 0.5) * width
        ax1.bar(x + offset, vals_hr, width, label=er, color=COLORS[idx],
                edgecolor="black", linewidth=0.3)
        ax2.bar(x + offset, vals_oc, width, label=er, color=COLORS[idx],
                edgecolor="black", linewidth=0.3)

    labels = workloads + ["AVG"]

    ax1.set_ylabel("Error Way Hit Rate (%)", fontsize=8)
    ax1.set_title("(a) Error Way Hit Rate — DRAM re-access avoided", fontsize=9, fontweight="bold")
    ax1.set_ylim(0, 105)
    ax1.yaxis.grid(True, linestyle="--", alpha=0.5, linewidth=0.5)
    ax1.set_axisbelow(True)
    ax1.tick_params(axis="y", labelsize=6)
    ax1.axvline(x=len(workloads) - 0.5, color="gray", linestyle=":", linewidth=0.8)
    ax1.legend(title="MTBCE", fontsize=6, title_fontsize=7, loc="lower right", ncol=4)

    ax2.set_ylabel("Error Way Occupancy (%)", fontsize=8)
    ax2.set_title("(b) LLC Capacity Cost — fraction occupied by pinned error data", fontsize=9, fontweight="bold")
    ax2.set_xticks(x)
    ax2.set_xticklabels(labels, rotation=45, ha="right", fontsize=6)
    ax2.yaxis.grid(True, linestyle="--", alpha=0.5, linewidth=0.5)
    ax2.set_axisbelow(True)
    ax2.tick_params(axis="y", labelsize=6)
    ax2.axvline(x=len(workloads) - 0.5, color="gray", linestyle=":", linewidth=0.8)

    plt.tight_layout(pad=0.5)
    plt.savefig(OUTPUT_PNG, dpi=300, bbox_inches="tight", facecolor="white", edgecolor="none")
    plt.close()
    print(f"CSV: {OUTPUT_CSV}\nPNG: {OUTPUT_PNG}")


if __name__ == "__main__":
    main()
