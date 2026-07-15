#!/usr/bin/env python3
"""
Fig 2: Error Rate Scalability — Graceful degradation across MTBCE.

Line plot: X = MTBCE (1e-5 → 1e-8), Y = Normalized IPC (GMEAN).
Three lines: Baseline (= 1.0), Our Approach, Conventional.
"""

import os
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

from common_ett import load_err_sweep, load_llc_baseline, gmean

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_CSV = os.path.join(SCRIPT_DIR, "fig2_ber_sweep.csv")
OUTPUT_PNG = os.path.join(SCRIPT_DIR, "fig2_ber_sweep.png")

ERROR_RATES = ["1e-5", "1e-6", "1e-7", "1e-8"]


def main():
    # ── Baseline ──
    baseline_ipc = {}
    for r in load_llc_baseline():
        if r["llc_size"] == "2MB" and r["metrics"].ipc is not None:
            baseline_ipc[r["workload"]] = r["metrics"].ipc

    # ── Sweep ──
    sweep = {}  # (workload, rate, pinning) -> ipc
    for r in load_err_sweep():
        if r["metrics"].ipc is not None:
            sweep[(r["workload"], r["error_rate"], r["pinning"])] = r["metrics"].ipc

    workloads = sorted(baseline_ipc.keys())
    if not workloads:
        print("No data")
        return

    rows = []
    gm_ours, gm_conv = [], []

    for er in ERROR_RATES:
        norm_ours_list, norm_conv_list = [], []
        for w in workloads:
            base = baseline_ipc.get(w, 0)
            if base <= 0:
                continue
            ours = sweep.get((w, er, True))
            conv = sweep.get((w, er, False))
            if ours is not None:
                norm_ours_list.append(ours / base)
            if conv is not None and conv > 0:
                norm_conv_list.append(conv / base)

        gm_o = gmean(norm_ours_list) if norm_ours_list else None
        gm_c = gmean(norm_conv_list) if norm_conv_list else None
        gm_ours.append(gm_o)
        gm_conv.append(gm_c)
        rows.append({"BER": er, "Norm_GMEAN_Ours": gm_o, "Norm_GMEAN_Conv": gm_c})

    pd.DataFrame(rows).to_csv(OUTPUT_CSV, index=False)

    # ── Plot ──
    x = np.arange(len(ERROR_RATES))
    fig, ax = plt.subplots(figsize=(6, 3.5))

    ax.axhline(y=1.0, color="#9E9E9E", linestyle="--", linewidth=1.5, label="No Error (Baseline)")
    ax.plot(x, gm_ours, marker="o", color="#4A90E2", linewidth=2, markersize=7, label="Our Approach")
    ax.plot(x, [v if v else 0 for v in gm_conv], marker="s", color="#EE5A6F",
            linewidth=2, markersize=7, label="Conventional")

    # Annotate values
    for i in range(len(ERROR_RATES)):
        if gm_ours[i] is not None:
            pct = (gm_ours[i] - 1) * 100
            ax.annotate(f"{pct:+.1f}%", (x[i], gm_ours[i]),
                        textcoords="offset points", xytext=(0, 10), ha="center", fontsize=7, color="#4A90E2")
        if gm_conv[i] is not None and gm_conv[i] > 0:
            pct = (gm_conv[i] - 1) * 100
            ax.annotate(f"{pct:+.1f}%", (x[i], gm_conv[i]),
                        textcoords="offset points", xytext=(0, -14), ha="center", fontsize=7, color="#EE5A6F")

    ax.set_ylabel("Normalized IPC (GMEAN)", fontsize=9)
    ax.set_xlabel("MTBCE", fontsize=9)
    ax.set_title("IPC Scalability across MTBCE", fontsize=10, fontweight="bold")
    ax.set_xticks(x)
    ax.set_xticklabels(ERROR_RATES, fontsize=8)
    ax.tick_params(axis="y", labelsize=7)
    ax.set_ylim(0, 1.15)
    ax.yaxis.grid(True, linestyle="--", alpha=0.5, linewidth=0.5)
    ax.set_axisbelow(True)
    ax.legend(fontsize=7, loc="lower left")

    plt.tight_layout(pad=0.3)
    plt.savefig(OUTPUT_PNG, dpi=300, bbox_inches="tight", facecolor="white", edgecolor="none")
    plt.close()
    print(f"CSV: {OUTPUT_CSV}\nPNG: {OUTPUT_PNG}")


if __name__ == "__main__":
    main()
