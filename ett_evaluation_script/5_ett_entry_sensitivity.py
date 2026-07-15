#!/usr/bin/env python3
"""
Fig 5: ETT Entry Count Sensitivity.

2-panel figure:
  Top:    GMEAN Normalized IPC vs Entry Count (line plot, one line per BER)
  Bottom: Total ETT Evictions vs Entry Count (bar chart)

Key message: 64 entries is sufficient; even 32 works at moderate BER.
Hardware overhead is small.
"""

import os
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

from common_ett import load_ett_entries, load_llc_baseline, gmean

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_CSV = os.path.join(SCRIPT_DIR, "fig5_ett_entries.csv")
OUTPUT_PNG = os.path.join(SCRIPT_DIR, "fig5_ett_entries.png")

ERROR_RATES = ["1e-5", "1e-6", "1e-7", "1e-8"]
COLORS = ["#2ECC71", "#F5A623", "#EE5A6F", "#4A90E2"]
MARKERS = ["^", "D", "s", "o"]


def main():
    # ── Baseline ──
    baseline_ipc = {}
    for r in load_llc_baseline():
        if r["llc_size"] == "2MB" and r["metrics"].ipc is not None:
            baseline_ipc[r["workload"]] = r["metrics"].ipc

    # ── ETT entry sweep ──
    recs = load_ett_entries()

    agg = {}  # (entries, rate) -> {ipc: [], evictions: [], workloads: []}
    detail_rows = []
    for r in recs:
        m = r["metrics"]
        key = (r["entries"], r["error_rate"])
        if key not in agg:
            agg[key] = {"ipc": [], "evictions": [], "workloads": []}
        if m.ipc is not None:
            agg[key]["ipc"].append(m.ipc)
            agg[key]["workloads"].append(r["workload"])
        if m.ett_evictions is not None:
            agg[key]["evictions"].append(m.ett_evictions)
        detail_rows.append({
            "Workload": r["workload"], "Entries": r["entries"],
            "Error_Rate": r["error_rate"], "IPC": m.ipc,
            "ETT_Evictions": m.ett_evictions,
        })

    pd.DataFrame(detail_rows).to_csv(OUTPUT_CSV, index=False)

    entry_counts = sorted(set(e for (e, _) in agg.keys()))
    if not entry_counts:
        print("No data")
        return

    # ── Plot ──
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(7, 5), sharex=True)
    x = np.arange(len(entry_counts))

    # Top: Normalized IPC (GMEAN)
    for idx, er in enumerate(ERROR_RATES):
        vals = []
        for e in entry_counts:
            data = agg.get((e, er), {})
            ipcs = data.get("ipc", [])
            wls = data.get("workloads", [])
            norm = [v / baseline_ipc[w] for v, w in zip(ipcs, wls)
                    if w in baseline_ipc and baseline_ipc[w] > 0]
            vals.append(gmean(norm) if norm else 0)
        ax1.plot(x, vals, marker=MARKERS[idx], color=COLORS[idx], label=er,
                 linewidth=1.8, markersize=6)

    ax1.axhline(y=1.0, color="#9E9E9E", linestyle="--", linewidth=1, label="Baseline")
    ax1.set_ylabel("Normalized IPC (GMEAN)", fontsize=9)
    ax1.set_title("(a) IPC vs ETT Entries", fontsize=10, fontweight="bold")
    ax1.tick_params(axis="y", labelsize=7)
    ax1.set_ylim(0, 1.15)
    ax1.yaxis.grid(True, linestyle="--", alpha=0.5, linewidth=0.5)
    ax1.set_axisbelow(True)
    ax1.legend(fontsize=6, loc="lower right")

    # Bottom: Total ETT Evictions
    n_rates = len(ERROR_RATES)
    width = 0.8 / n_rates
    for idx, er in enumerate(ERROR_RATES):
        vals = [sum(agg.get((e, er), {}).get("evictions", [0])) for e in entry_counts]
        offset = (idx - n_rates / 2 + 0.5) * width
        ax2.bar(x + offset, vals, width, label=er, color=COLORS[idx],
                edgecolor="black", linewidth=0.3)

    ax2.set_ylabel("Total ETT Evictions (all workloads)", fontsize=8)
    ax2.set_xlabel("ETT Entry Count", fontsize=9)
    ax2.set_title("(b) ETT Evictions vs Entry Count", fontsize=10, fontweight="bold")
    ax2.set_xticks(x)
    ax2.set_xticklabels([str(e) for e in entry_counts], fontsize=8)
    ax2.tick_params(axis="y", labelsize=7)
    ax2.yaxis.grid(True, linestyle="--", alpha=0.5, linewidth=0.5)
    ax2.set_axisbelow(True)
    ax2.legend(fontsize=6, loc="upper right")

    plt.tight_layout(pad=0.5)
    plt.savefig(OUTPUT_PNG, dpi=300, bbox_inches="tight", facecolor="white", edgecolor="none")
    plt.close()
    print(f"CSV: {OUTPUT_CSV}\nPNG: {OUTPUT_PNG}")


if __name__ == "__main__":
    main()
