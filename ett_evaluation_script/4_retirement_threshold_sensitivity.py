#!/usr/bin/env python3
"""
Fig 4: Retirement Threshold Sensitivity — Pinning OFF vs ON (IPC comparison).
Bar chart showing that proposed cache pinning recovers IPC across thresholds/error rates.
"""

import os
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

from common_ett import load_retire_threshold, load_llc_baseline, gmean

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_CSV = os.path.join(SCRIPT_DIR, "4_retirement_threshold_sensitivity.csv")
OUTPUT_PNG = os.path.join(SCRIPT_DIR, "4_retirement_threshold_sensitivity.png")

ERROR_RATES = ["1e-8", "1e-7", "1e-6", "1e-5"]
THRESHOLDS = [4, 8, 16, 32]


def main():
    # ── Load baseline ──
    baseline_recs = load_llc_baseline()
    baseline_ipc = {}
    for r in baseline_recs:
        if r["llc_size"] == "2MB" and r["metrics"].ipc is not None:
            baseline_ipc[r["workload"]] = r["metrics"].ipc
    baseline_gmean_val = gmean(list(baseline_ipc.values())) if baseline_ipc else None

    # ── Load retire threshold sweep ──
    recs = load_retire_threshold()

    # Aggregate: (pinning, threshold, error_rate) -> lists
    agg = {}
    per_workload = []
    for r in recs:
        m = r["metrics"]
        key = (r["pinning"], r["threshold"], r["error_rate"])
        if key not in agg:
            agg[key] = {"ipc": [], "retired": [], "evictions": []}
        if m.ipc is not None:
            agg[key]["ipc"].append(m.ipc)
        if m.pages_retired is not None:
            agg[key]["retired"].append(m.pages_retired)
        if m.ett_evictions is not None:
            agg[key]["evictions"].append(m.ett_evictions)
        per_workload.append({
            "Workload": r["workload"],
            "Pinning": "ON" if r["pinning"] else "OFF",
            "Threshold": r["threshold"],
            "Error_Rate": r["error_rate"],
            "IPC": m.ipc,
            "Pages_Retired": m.pages_retired,
            "ETT_Evictions": m.ett_evictions,
        })

    df_detail = pd.DataFrame(per_workload)
    df_detail.to_csv(OUTPUT_CSV, index=False)

    if not agg:
        print("No retirement threshold data found")
        return

    # ── Plot: single chart ──
    # X-axis: each error rate × threshold combo for Pinning OFF (4,8,16,32)
    # Plus dashed lines for Pinning ON at each threshold per error rate
    PINNING_ON_THRESHOLDS = [4, 8, 16, 32]

    fig, ax = plt.subplots(figsize=(5.5, 2.8))

    color_off = "#EE5A6F"
    on_colors = {4: "#90CAF9", 8: "#42A5F5", 16: "#1E88E5", 32: "#0D47A1"}
    on_linewidths = {4: 1.0, 8: 1.2, 16: 1.5, 32: 2.0}

    # Bars tightly packed within group, gap only between error rate groups
    group_labels = []
    off_vals = []
    group_positions = []
    group_ranges = []  # (start_pos, end_pos, {threshold: norm_on}) per error rate
    bar_width = 1.0   # no gap between bars
    pos = 0
    group_gap = 1.0   # gap between BER groups

    for er_idx, er in enumerate(ERROR_RATES):
        on_norms = {}
        for t in PINNING_ON_THRESHOLDS:
            ipc_on = gmean(agg.get((True, t, er), {}).get("ipc", []))
            on_norms[t] = ipc_on / baseline_gmean_val if baseline_gmean_val and ipc_on else 0
        g_start = pos
        for t in THRESHOLDS:
            ipc_off = gmean(agg.get((False, t, er), {}).get("ipc", []))
            norm_off = ipc_off / baseline_gmean_val if baseline_gmean_val else 0
            off_vals.append(norm_off)
            group_positions.append(pos)
            group_labels.append(str(t))
            pos += 1  # step = 1 = bar_width + no gap → tightly packed
        g_end = pos - 1
        group_ranges.append((g_start, g_end, on_norms, er))
        pos += group_gap

    x = np.array(group_positions, dtype=float)

    # Red bars (W/O Pinning)
    ax.bar(x, off_vals, bar_width,
           label="W/O Pinning", color=color_off,
           edgecolor="black", linewidth=0.3)

    # Dashed lines for each Pinning ON threshold
    for i, (g_start, g_end, on_norms, er) in enumerate(group_ranges):
        margin = bar_width / 2 + 0.1
        for t in PINNING_ON_THRESHOLDS:
            if on_norms.get(t, 0) == 0:
                continue
            label = f"W/ Pinning (t={t})" if i == 0 else None
            ax.hlines(y=on_norms[t], xmin=g_start - margin, xmax=g_end + margin,
                      colors=on_colors[t], linestyles="--",
                      linewidth=on_linewidths[t], label=label)

    # X-axis: threshold numbers on tick, MTBCE group label below
    ax.set_xticks(x)
    ax.set_xticklabels(group_labels, fontsize=6)
    ax.tick_params(axis="x", pad=2)

    # MTBCE group labels below threshold numbers
    for g_start, g_end, _, er in group_ranges:
        mid = (g_start + g_end) / 2
        # Convert BER notation to MTBCE notation (1e-X → 10^X)
        exp = er.replace("1e-", "")
        ax.text(mid, -0.15, f"MTBCE=$10^{exp}$",
                ha="center", va="top", fontsize=6, fontweight="bold",
                transform=ax.get_xaxis_transform())

    ax.set_ylabel("Normalized IPC", fontsize=7)
    ax.set_ylim(bottom=0.4)
    ax.yaxis.grid(True, linestyle="--", alpha=0.4, linewidth=0.4)
    ax.set_axisbelow(True)
    ax.tick_params(axis="y", labelsize=6)
    ax.legend(fontsize=6, loc="lower right")

    plt.tight_layout(pad=0.3)
    plt.savefig(OUTPUT_PNG, dpi=300, bbox_inches="tight", facecolor="white", edgecolor="none")
    plt.close()

    print(f"CSV saved: {OUTPUT_CSV}")
    print(f"PNG saved: {OUTPUT_PNG}")


if __name__ == "__main__":
    main()
