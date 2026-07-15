#!/usr/bin/env python3
"""
Fig 1: Pinning ON vs OFF vs Baseline IPC comparison.
- Per-workload grouped bar chart at each error rate
- Includes GMEAN
- Annotated with baseline-relative % change
"""

import os
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

from common_ett import load_err_sweep, load_llc_baseline, gmean

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_CSV = os.path.join(SCRIPT_DIR, "1_pinning_ipc_comparison.csv")
OUTPUT_PNG = os.path.join(SCRIPT_DIR, "1_pinning_ipc_comparison.png")

ERROR_RATES = ["1e-8", "1e-7", "1e-6", "1e-5"]


def main():
    # ── Load data ──
    baseline_recs = load_llc_baseline()
    baseline_ipc = {}
    for r in baseline_recs:
        if r["llc_size"] == "2MB" and r["metrics"].ipc is not None:
            baseline_ipc[r["workload"]] = r["metrics"].ipc

    sweep_recs = load_err_sweep()
    # {(workload, error_rate, pinning): ipc}
    sweep_ipc = {}
    for r in sweep_recs:
        if r["metrics"].ipc is not None:
            sweep_ipc[(r["workload"], r["error_rate"], r["pinning"])] = r["metrics"].ipc

    workloads = sorted(baseline_ipc.keys())
    if not workloads:
        print("No baseline data found")
        return

    # ── Build CSV ──
    rows = []
    for w in workloads:
        for er in ERROR_RATES:
            rows.append({
                "Workload": w,
                "Error_Rate": er,
                "Baseline_IPC": baseline_ipc.get(w),
                "Pinning_ON_IPC": sweep_ipc.get((w, er, True)),
                "Pinning_OFF_IPC": sweep_ipc.get((w, er, False)),
            })
    df = pd.DataFrame(rows)
    df.to_csv(OUTPUT_CSV, index=False)

    # ── Plot: one subplot per error rate ──
    fig, axes = plt.subplots(len(ERROR_RATES), 1, figsize=(10, 2.8 * len(ERROR_RATES)), sharex=False)
    if len(ERROR_RATES) == 1:
        axes = [axes]

    for idx, er in enumerate(ERROR_RATES):
        ax = axes[idx]
        b_vals, on_vals, off_vals = [], [], []
        for w in workloads:
            b_vals.append(baseline_ipc.get(w, 0))
            on_vals.append(sweep_ipc.get((w, er, True), 0))
            off_vals.append(sweep_ipc.get((w, er, False), 0))

        # Add GMEAN
        labels = workloads + ["GMEAN"]
        b_vals.append(gmean(b_vals))
        on_vals.append(gmean(on_vals))
        off_vals.append(gmean(off_vals))

        x = np.arange(len(labels))
        width = 0.27

        ax.bar(x - width, b_vals, width, label="No Error (Baseline)", color="#9E9E9E", edgecolor="black", linewidth=0.3)
        ax.bar(x, on_vals, width, label="Pinning ON", color="#4A90E2", edgecolor="black", linewidth=0.3)
        ax.bar(x + width, off_vals, width, label="Pinning OFF", color="#EE5A6F", edgecolor="black", linewidth=0.3)

        # Annotate % change relative to baseline
        for i in range(len(labels)):
            base = b_vals[i]
            if base <= 0:
                continue
            for offset, val in [(0, on_vals[i]), (width, off_vals[i])]:
                if val <= 0:
                    continue
                pct = (val / base - 1) * 100
                ax.text(x[i] + offset, val + max(0.003, abs(val) * 0.01),
                        f"{pct:+.1f}%", ha="center", va="bottom", fontsize=4.5)

        ax.set_ylabel("IPC", fontsize=8)
        ax.set_title(f"Error Rate: {er}", fontsize=9, fontweight="bold")
        ax.set_xticks(x)
        ax.set_xticklabels(labels, rotation=45, ha="right", fontsize=6)
        ax.tick_params(axis="y", labelsize=6)
        ax.yaxis.grid(True, linestyle="--", alpha=0.5, linewidth=0.5)
        ax.set_axisbelow(True)
        ax.margins(x=0.01)

        # GMEAN separator
        ax.axvline(x=len(workloads) - 0.5, color="gray", linestyle=":", linewidth=0.8)

    handles, labels_leg = axes[0].get_legend_handles_labels()
    fig.legend(handles, labels_leg, loc="upper center", ncol=3, fontsize=7,
               framealpha=0.9, bbox_to_anchor=(0.5, 1.01))
    plt.tight_layout(rect=[0, 0, 1, 0.97], pad=0.5)
    plt.savefig(OUTPUT_PNG, dpi=300, bbox_inches="tight", facecolor="white", edgecolor="none")
    plt.close()

    print(f"CSV saved: {OUTPUT_CSV}")
    print(f"PNG saved: {OUTPUT_PNG}")


if __name__ == "__main__":
    main()
