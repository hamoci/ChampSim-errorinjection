#!/usr/bin/env python3
"""
Fig 4: Retirement Threshold Sensitivity (Pinning ON only).

2-panel figure:
  Left:  GMEAN IPC vs Threshold (line plot, one line per BER)
  Right: Total Pages Retired vs Threshold (bar chart)

Key message: threshold=32 is the sweet spot — retirement drops by orders
of magnitude while IPC loss remains <10%.
"""

import os
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

from common_ett import load_retire_threshold, load_llc_baseline, gmean

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_CSV = os.path.join(SCRIPT_DIR, "fig4_threshold.csv")
OUTPUT_PNG = os.path.join(SCRIPT_DIR, "fig4_threshold.png")

ERROR_RATES = ["1e-5", "1e-6", "1e-7", "1e-8"]
COLORS = ["#2ECC71", "#F5A623", "#EE5A6F", "#4A90E2"]
MARKERS = ["^", "D", "s", "o"]


def main():
    # ── Baseline ──
    baseline_ipc = {}
    for r in load_llc_baseline():
        if r["llc_size"] == "2MB" and r["metrics"].ipc is not None:
            baseline_ipc[r["workload"]] = r["metrics"].ipc
    baseline_gm = gmean(list(baseline_ipc.values())) if baseline_ipc else None

    # ── Threshold sweep (Pinning ON only) ──
    recs = [r for r in load_retire_threshold() if r["pinning"]]

    agg = {}  # (threshold, rate) -> {ipc: [], retired: []}
    detail_rows = []
    for r in recs:
        m = r["metrics"]
        key = (r["threshold"], r["error_rate"])
        if key not in agg:
            agg[key] = {"ipc": [], "retired": []}
        if m.ipc is not None:
            agg[key]["ipc"].append(m.ipc)
        if m.pages_retired is not None:
            agg[key]["retired"].append(m.pages_retired)
        detail_rows.append({
            "Workload": r["workload"], "Threshold": r["threshold"],
            "Error_Rate": r["error_rate"], "IPC": m.ipc,
            "Pages_Retired": m.pages_retired,
        })

    pd.DataFrame(detail_rows).to_csv(OUTPUT_CSV, index=False)

    thresholds = sorted(set(t for (t, _) in agg.keys()))
    if not thresholds:
        print("No data")
        return

    # ── Plot ──
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(10, 3.5))
    x = np.arange(len(thresholds))

    # Left: GMEAN IPC
    for idx, er in enumerate(ERROR_RATES):
        vals = []
        for t in thresholds:
            ipcs = agg.get((t, er), {}).get("ipc", [])
            # Normalize then gmean
            norm = [v / baseline_ipc.get(w, v) for v, w in
                    zip(ipcs, sorted(baseline_ipc.keys())[:len(ipcs)])]
            vals.append(gmean(norm) if norm else 0)
        ax1.plot(x, vals, marker=MARKERS[idx], color=COLORS[idx], label=er,
                 linewidth=1.8, markersize=6)

    ax1.axhline(y=1.0, color="#9E9E9E", linestyle="--", linewidth=1, label="Baseline")
    ax1.set_ylabel("Normalized IPC (GMEAN)", fontsize=9)
    ax1.set_xlabel("Retirement Threshold", fontsize=9)
    ax1.set_title("(a) IPC vs Threshold", fontsize=10, fontweight="bold")
    ax1.set_xticks(x)
    ax1.set_xticklabels([str(t) for t in thresholds], fontsize=8)
    ax1.tick_params(axis="y", labelsize=7)
    ax1.set_ylim(0, 1.15)
    ax1.yaxis.grid(True, linestyle="--", alpha=0.5, linewidth=0.5)
    ax1.set_axisbelow(True)
    ax1.legend(fontsize=6, loc="lower right")

    # Right: Total Pages Retired
    n_rates = len(ERROR_RATES)
    width = 0.8 / n_rates
    for idx, er in enumerate(ERROR_RATES):
        vals = [sum(agg.get((t, er), {}).get("retired", [0])) for t in thresholds]
        offset = (idx - n_rates / 2 + 0.5) * width
        bars = ax2.bar(x + offset, vals, width, label=er, color=COLORS[idx],
                       edgecolor="black", linewidth=0.3)
        # Annotate non-zero values
        for bar, val in zip(bars, vals):
            if val > 0:
                ax2.text(bar.get_x() + bar.get_width() / 2, bar.get_height(),
                         f"{int(val)}", ha="center", va="bottom", fontsize=4.5)

    ax2.set_ylabel("Total Pages Retired (all workloads)", fontsize=8)
    ax2.set_xlabel("Retirement Threshold", fontsize=9)
    ax2.set_title("(b) Page Retirements vs Threshold", fontsize=10, fontweight="bold")
    ax2.set_xticks(x)
    ax2.set_xticklabels([str(t) for t in thresholds], fontsize=8)
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
