#!/usr/bin/env python3
"""
Fig 1: Motivation — Catastrophic IPC loss under naive page retirement.

Normalized IPC (baseline = 1.0) at BER = 1e-8.
Three bars per workload:
  (1) No Error Baseline (= 1.0)
  (2) Our Approach (Pinning ON, threshold=32)
  (3) Conventional (immediate page retirement, no ETT)
"""

import os
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

from common_ett import load_err_sweep, load_llc_baseline, gmean

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_CSV = os.path.join(SCRIPT_DIR, "fig1_motivation.csv")
OUTPUT_PNG = os.path.join(SCRIPT_DIR, "fig1_motivation.png")

TARGET_RATE = "1e-8"


def main():
    # ── Baseline (no error, 2MB LLC) ──
    baseline_ipc = {}
    for r in load_llc_baseline():
        if r["llc_size"] == "2MB" and r["metrics"].ipc is not None:
            baseline_ipc[r["workload"]] = r["metrics"].ipc

    # ── Error rate sweep ──
    pin_on, pin_off = {}, {}
    for r in load_err_sweep():
        if r["error_rate"] != TARGET_RATE or r["metrics"].ipc is None:
            continue
        if r["pinning"]:
            pin_on[r["workload"]] = r["metrics"].ipc
        else:
            pin_off[r["workload"]] = r["metrics"].ipc

    workloads = sorted(w for w in baseline_ipc if w in pin_on)
    if not workloads:
        print("No matching data found")
        return

    # ── Build normalized values ──
    rows = []
    norm_ours, norm_conv = [], []
    for w in workloads:
        base = baseline_ipc[w]
        ours = pin_on.get(w, 0)
        conv = pin_off.get(w)  # may be None (crashed / too slow)
        n_ours = ours / base if base > 0 else 0
        n_conv = conv / base if conv is not None and base > 0 else 0
        norm_ours.append(n_ours)
        norm_conv.append(n_conv)
        rows.append({
            "Workload": w, "Baseline_IPC": base,
            "Ours_IPC": ours, "Conv_IPC": conv,
            "Norm_Ours": n_ours, "Norm_Conv": n_conv,
        })

    # GMEAN
    gm_ours = gmean(norm_ours)
    gm_conv = gmean([v for v in norm_conv if v > 0])
    norm_ours.append(gm_ours)
    norm_conv.append(gm_conv)
    labels = workloads + ["GMEAN"]

    pd.DataFrame(rows).to_csv(OUTPUT_CSV, index=False)

    # ── Plot ──
    x = np.arange(len(labels))
    width = 0.25
    fig, ax = plt.subplots(figsize=(10, 3.2))

    ax.bar(x - width, [1.0] * len(labels), width,
           label="No Error (Baseline)", color="#9E9E9E", edgecolor="black", linewidth=0.3)
    ax.bar(x, norm_ours, width,
           label="Our Approach", color="#4A90E2", edgecolor="black", linewidth=0.3)
    ax.bar(x + width, norm_conv, width,
           label="Conventional (Immediate Retire)", color="#EE5A6F", edgecolor="black", linewidth=0.3)

    # Annotate degradation %
    for i in range(len(labels)):
        for offset, val in [(0, norm_ours[i]), (width, norm_conv[i])]:
            if val <= 0:
                # Mark missing data
                ax.text(x[i] + offset, 0.02, "N/A", ha="center", va="bottom",
                        fontsize=5, color="gray", fontstyle="italic")
                continue
            pct = (val - 1) * 100
            ax.text(x[i] + offset, val + 0.01, f"{pct:+.1f}%",
                    ha="center", va="bottom", fontsize=5)

    ax.set_ylabel("Normalized IPC", fontsize=9)
    ax.set_title(f"IPC Degradation at MTBCE = {TARGET_RATE}", fontsize=10, fontweight="bold")
    ax.set_xticks(x)
    ax.set_xticklabels(labels, rotation=45, ha="right", fontsize=6)
    ax.tick_params(axis="y", labelsize=7)
    ax.set_ylim(0, 1.15)
    ax.yaxis.grid(True, linestyle="--", alpha=0.5, linewidth=0.5)
    ax.set_axisbelow(True)
    ax.margins(x=0.01)
    ax.axvline(x=len(workloads) - 0.5, color="gray", linestyle=":", linewidth=0.8)
    ax.legend(loc="upper right", fontsize=7)

    plt.tight_layout(pad=0.3)
    plt.savefig(OUTPUT_PNG, dpi=300, bbox_inches="tight", facecolor="white", edgecolor="none")
    plt.close()
    print(f"CSV: {OUTPUT_CSV}\nPNG: {OUTPUT_PNG}")


if __name__ == "__main__":
    main()
