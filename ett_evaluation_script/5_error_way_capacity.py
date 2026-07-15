#!/usr/bin/env python3
"""
Fig 5: Error Way Capacity (Max Ways) Sensitivity.
- IPC (GMEAN) per max-ways × error rate
- Error Way Evictions (when ways are saturated, evictions happen)
"""

import os
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

from common_ett import load_errway_capacity, load_llc_baseline, gmean

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_CSV = os.path.join(SCRIPT_DIR, "5_error_way_capacity.csv")
OUTPUT_PNG = os.path.join(SCRIPT_DIR, "5_error_way_capacity.png")

ERROR_RATES = ["1e-8", "1e-7", "1e-6", "1e-5"]
WAYS = [1, 4, 8]


def main():
    # ── Baseline ──
    baseline_recs = load_llc_baseline()
    baseline_ipc = {}
    for r in baseline_recs:
        if r["llc_size"] == "2MB" and r["metrics"].ipc is not None:
            baseline_ipc[r["workload"]] = r["metrics"].ipc
    baseline_gmean_val = gmean(list(baseline_ipc.values())) if baseline_ipc else None

    # ── Load ──
    recs = load_errway_capacity()

    agg = {}
    per_workload = []
    for r in recs:
        m = r["metrics"]
        key = (r["ways"], r["error_rate"])
        if key not in agg:
            agg[key] = {"ipc": [], "evictions": [], "used_pct": []}
        if m.ipc is not None:
            agg[key]["ipc"].append(m.ipc)
        if m.err_way_evictions is not None:
            agg[key]["evictions"].append(m.err_way_evictions)
        if m.err_way_used_pct is not None:
            agg[key]["used_pct"].append(m.err_way_used_pct)
        per_workload.append({
            "Workload": r["workload"],
            "Max_Ways": r["ways"],
            "Error_Rate": r["error_rate"],
            "IPC": m.ipc,
            "Err_Way_Evictions": m.err_way_evictions,
            "Err_Way_Used_Pct": m.err_way_used_pct,
        })

    df = pd.DataFrame(per_workload)
    df.to_csv(OUTPUT_CSV, index=False)

    if not agg:
        print("No error way capacity data found")
        return

    existing_ways = sorted(set(w for (w, _) in agg.keys()))

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(8, 5), sharex=True)
    colors = ["#4A90E2", "#EE5A6F", "#2ECC71", "#F5A623"]
    markers = ["o", "s", "^", "D"]
    x = np.arange(len(existing_ways))

    # ── IPC (GMEAN) ──
    for idx, er in enumerate(ERROR_RATES):
        vals = [gmean(agg.get((w, er), {}).get("ipc", [])) for w in existing_ways]
        ax1.plot(x, vals, marker=markers[idx], color=colors[idx], label=er,
                 linewidth=1.5, markersize=5)

    if baseline_gmean_val:
        ax1.axhline(y=baseline_gmean_val, color="gray", linestyle="--", linewidth=1, label="Baseline")

    ax1.set_ylabel("IPC (GMEAN)", fontsize=8)
    ax1.set_title("Max Error Ways per Set — Sensitivity", fontsize=10, fontweight="bold")
    ax1.legend(title="Error Rate", fontsize=6, title_fontsize=7, loc="best")
    ax1.yaxis.grid(True, linestyle="--", alpha=0.5, linewidth=0.5)
    ax1.set_axisbelow(True)
    ax1.tick_params(axis="y", labelsize=6)

    # ── Error Way Evictions (sum) ──
    for idx, er in enumerate(ERROR_RATES):
        vals = [sum(agg.get((w, er), {}).get("evictions", [0])) for w in existing_ways]
        ax2.bar(x + (idx - len(ERROR_RATES) / 2 + 0.5) * 0.18, vals, 0.18,
                label=er, color=colors[idx], edgecolor="black", linewidth=0.3)

    ax2.set_ylabel("Total Error Way Evictions", fontsize=8)
    ax2.set_xticks(x)
    ax2.set_xticklabels([str(w) for w in existing_ways], fontsize=8)
    ax2.set_xlabel("Max Error Ways per Set", fontsize=9)
    ax2.yaxis.grid(True, linestyle="--", alpha=0.5, linewidth=0.5)
    ax2.set_axisbelow(True)
    ax2.tick_params(axis="y", labelsize=6)

    plt.tight_layout(pad=0.5)
    plt.savefig(OUTPUT_PNG, dpi=300, bbox_inches="tight", facecolor="white", edgecolor="none")
    plt.close()

    print(f"CSV saved: {OUTPUT_CSV}")
    print(f"PNG saved: {OUTPUT_PNG}")


if __name__ == "__main__":
    main()
