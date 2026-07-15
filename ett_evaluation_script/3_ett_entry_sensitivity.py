#!/usr/bin/env python3
"""
Fig 3: ETT Entry Count Sensitivity.
- IPC (GMEAN across workloads) per entry count × error rate
- ETT Eviction count (shows whether entries are sufficient)
- Pages retired (consequence of eviction)
"""

import os
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

from common_ett import load_ett_entries, load_llc_baseline, gmean

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_CSV = os.path.join(SCRIPT_DIR, "3_ett_entry_sensitivity.csv")
OUTPUT_PNG = os.path.join(SCRIPT_DIR, "3_ett_entry_sensitivity.png")

ERROR_RATES = ["1e-8", "1e-7", "1e-6", "1e-5"]
ENTRY_COUNTS = [1, 4, 8, 16, 32, 64, 128, 256]


def main():
    # ── Load baseline ──
    baseline_recs = load_llc_baseline()
    baseline_ipc = {}
    for r in baseline_recs:
        if r["llc_size"] == "2MB" and r["metrics"].ipc is not None:
            baseline_ipc[r["workload"]] = r["metrics"].ipc

    # ── Load ETT entry sweep ──
    recs = load_ett_entries()

    # Aggregate per (entries, error_rate)
    agg = {}  # (entries, rate) -> {ipc: [], evictions: [], retired: []}
    per_workload = []
    for r in recs:
        m = r["metrics"]
        key = (r["entries"], r["error_rate"])
        if key not in agg:
            agg[key] = {"ipc": [], "evictions": [], "retired": [], "ett_used": []}
        if m.ipc is not None:
            agg[key]["ipc"].append(m.ipc)
        if m.ett_evictions is not None:
            agg[key]["evictions"].append(m.ett_evictions)
        if m.pages_retired is not None:
            agg[key]["retired"].append(m.pages_retired)
        if m.ett_used is not None:
            agg[key]["ett_used"].append(m.ett_used)
        per_workload.append({
            "Workload": r["workload"],
            "Entries": r["entries"],
            "Error_Rate": r["error_rate"],
            "IPC": m.ipc,
            "ETT_Evictions": m.ett_evictions,
            "Pages_Retired": m.pages_retired,
            "ETT_Used": m.ett_used,
        })

    df_detail = pd.DataFrame(per_workload)
    df_detail.to_csv(OUTPUT_CSV, index=False)

    if not agg:
        print("No ETT entry data found")
        return

    baseline_gmean = gmean(list(baseline_ipc.values())) if baseline_ipc else None

    # ── Plot: 3 subplots ──
    fig, (ax1, ax2, ax3) = plt.subplots(3, 1, figsize=(8, 7), sharex=True)
    colors = ["#4A90E2", "#EE5A6F", "#2ECC71", "#F5A623"]
    markers = ["o", "s", "^", "D"]
    x = np.arange(len(ENTRY_COUNTS))

    # ── Subplot 1: IPC (GMEAN) ──
    for idx, er in enumerate(ERROR_RATES):
        vals = [gmean(agg.get((e, er), {}).get("ipc", [])) for e in ENTRY_COUNTS]
        ax1.plot(x, vals, marker=markers[idx], color=colors[idx], label=er,
                 linewidth=1.5, markersize=5)

    if baseline_gmean:
        ax1.axhline(y=baseline_gmean, color="gray", linestyle="--", linewidth=1, label="No Error Baseline")

    ax1.set_ylabel("IPC (GMEAN)", fontsize=8)
    ax1.set_title("ETT Entry Count Sensitivity", fontsize=10, fontweight="bold")
    ax1.legend(title="Error Rate", fontsize=6, title_fontsize=7, loc="best")
    ax1.yaxis.grid(True, linestyle="--", alpha=0.5, linewidth=0.5)
    ax1.set_axisbelow(True)
    ax1.tick_params(axis="y", labelsize=6)

    # ── Subplot 2: Total ETT Evictions (sum across workloads) ──
    for idx, er in enumerate(ERROR_RATES):
        vals = [sum(agg.get((e, er), {}).get("evictions", [0])) for e in ENTRY_COUNTS]
        ax2.bar(x + (idx - len(ERROR_RATES) / 2 + 0.5) * 0.18, vals, 0.18,
                label=er, color=colors[idx], edgecolor="black", linewidth=0.3)

    ax2.set_ylabel("Total ETT Evictions", fontsize=8)
    ax2.yaxis.grid(True, linestyle="--", alpha=0.5, linewidth=0.5)
    ax2.set_axisbelow(True)
    ax2.tick_params(axis="y", labelsize=6)
    ax2.legend(title="Error Rate", fontsize=6, title_fontsize=7, loc="best")

    # ── Subplot 3: Pages Retired (sum across workloads) ──
    for idx, er in enumerate(ERROR_RATES):
        vals = [sum(agg.get((e, er), {}).get("retired", [0])) for e in ENTRY_COUNTS]
        ax3.bar(x + (idx - len(ERROR_RATES) / 2 + 0.5) * 0.18, vals, 0.18,
                label=er, color=colors[idx], edgecolor="black", linewidth=0.3)

    ax3.set_ylabel("Total Pages Retired", fontsize=8)
    ax3.set_xticks(x)
    ax3.set_xticklabels([str(e) for e in ENTRY_COUNTS], fontsize=8)
    ax3.set_xlabel("ETT Entries", fontsize=9)
    ax3.yaxis.grid(True, linestyle="--", alpha=0.5, linewidth=0.5)
    ax3.set_axisbelow(True)
    ax3.tick_params(axis="y", labelsize=6)

    plt.tight_layout(pad=0.5)
    plt.savefig(OUTPUT_PNG, dpi=300, bbox_inches="tight", facecolor="white", edgecolor="none")
    plt.close()

    print(f"CSV saved: {OUTPUT_CSV}")
    print(f"PNG saved: {OUTPUT_PNG}")


if __name__ == "__main__":
    main()
