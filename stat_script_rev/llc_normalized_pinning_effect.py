#!/usr/bin/env python3
"""Baseline-normalized IPC and pinning gain summary (real_final_spec, LLC=2MB)."""

import os
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

from common_real_final import load_records, extract_ipc

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_CSV = os.path.join(SCRIPT_DIR, "llc_normalized_pinning_effect.csv")
OUTPUT_PNG = os.path.join(SCRIPT_DIR, "llc_normalized_pinning_effect.png")

ERROR_RATES = ["1e-6", "1e-7", "1e-8", "1e-9"]
PAGES = ["4kb", "2mb"]
LLC_MB = 2


def gmean(values):
    vals = [v for v in values if v is not None and v > 0]
    if not vals:
        return None
    return float(np.exp(np.mean(np.log(vals))))


def main():
    recs = [r for r in load_records() if r.llc_mb == LLC_MB]

    baseline = {}
    errors = {}

    for r in recs:
        ipc = extract_ipc(r.path)
        if ipc is None:
            continue

        if r.error_rate is None:
            baseline[(r.workload, r.page)] = ipc
            continue

        if r.error_rate not in ERROR_RATES or r.page not in PAGES:
            continue

        errors[(r.workload, r.page, r.error_rate, r.pinning)] = ipc

    rows = []
    for page in PAGES:
        for er in ERROR_RATES:
            ratios = {False: [], True: []}
            pin_gain = []

            for workload in sorted({k[0] for k in errors.keys()}):
                b = baseline.get((workload, page))
                if b is None or b <= 0:
                    continue

                n = errors.get((workload, page, er, False))
                p = errors.get((workload, page, er, True))

                if n is not None and n > 0:
                    ratios[False].append(n / b)
                if p is not None and p > 0:
                    ratios[True].append(p / b)
                if n is not None and p is not None and n > 0 and p > 0:
                    pin_gain.append(p / n)

            g_n = gmean(ratios[False])
            g_p = gmean(ratios[True])
            g_gain = gmean(pin_gain)

            rows.append({
                "Page": page,
                "MTBCE": er,
                "NoPin_vs_Baseline_GMEAN": g_n,
                "Pin_vs_Baseline_GMEAN": g_p,
                "Pin_over_NoPin_GMEAN": g_gain,
                "NoPin_vs_Baseline_%": None if g_n is None else (g_n - 1.0) * 100.0,
                "Pin_vs_Baseline_%": None if g_p is None else (g_p - 1.0) * 100.0,
                "Pin_Gain_%": None if g_gain is None else (g_gain - 1.0) * 100.0,
                "NoPin_Samples": len(ratios[False]),
                "Pin_Samples": len(ratios[True]),
                "Gain_Samples": len(pin_gain),
            })

    df = pd.DataFrame(rows)
    df.to_csv(OUTPUT_CSV, index=False)

    if df.empty:
        print("No normalized records found")
        return

    fig, axes = plt.subplots(2, 1, figsize=(9, 5.4), sharex=True)
    x = np.arange(len(ERROR_RATES))
    bw = 0.32

    for i, page in enumerate(PAGES):
        ax = axes[i]
        ax2 = ax.twinx()

        sub = df[df["Page"] == page].set_index("MTBCE").reindex(ERROR_RATES)
        y_n = sub["NoPin_vs_Baseline_%"].to_numpy(dtype=float)
        y_p = sub["Pin_vs_Baseline_%"].to_numpy(dtype=float)
        y_g = sub["Pin_Gain_%"].to_numpy(dtype=float)

        ax.bar(x - bw / 2, y_n, bw, color="#C0392B", edgecolor="black", linewidth=0.3, label="NoPin vs Baseline")
        ax.bar(x + bw / 2, y_p, bw, color="#2471A3", edgecolor="black", linewidth=0.3, label="Pin vs Baseline")

        ax2.plot(x, y_g, marker="o", markersize=4, linewidth=1.5, color="#117A65", label="Pin Gain (Pin/NoPin)")

        ax.axhline(0.0, color="black", linewidth=0.8, alpha=0.8)
        ax.set_ylabel(f"{page.upper()}\nDelta IPC (%)", fontsize=8)
        ax2.set_ylabel("Pin Gain (%)", fontsize=8)
        ax.tick_params(axis="y", labelsize=7)
        ax2.tick_params(axis="y", labelsize=7)
        ax.grid(True, axis="y", linestyle="--", alpha=0.45, linewidth=0.5)
        ax.set_axisbelow(True)

    axes[-1].set_xticks(x)
    axes[-1].set_xticklabels(ERROR_RATES, fontsize=8)
    axes[-1].set_xlabel("MTBCE", fontsize=9)

    handles = [
        plt.Rectangle((0, 0), 1, 1, facecolor="#C0392B", edgecolor="black", linewidth=0.3, label="NoPin vs Baseline"),
        plt.Rectangle((0, 0), 1, 1, facecolor="#2471A3", edgecolor="black", linewidth=0.3, label="Pin vs Baseline"),
        plt.Line2D([0], [0], color="#117A65", marker="o", linewidth=1.5, markersize=4, label="Pin Gain (Pin/NoPin)"),
    ]
    fig.legend(handles=handles, loc="upper center", ncol=3, fontsize=8, framealpha=0.9)
    fig.suptitle("LLC 2MB: Baseline-normalized IPC and Cache Pinning Gain", fontsize=11, fontweight="bold", y=0.98)
    plt.tight_layout(rect=[0, 0, 1, 0.94])
    plt.savefig(OUTPUT_PNG, dpi=300, bbox_inches="tight", facecolor="white", edgecolor="none")
    plt.close()

    print(f"CSV saved: {OUTPUT_CSV}")
    print(f"PNG saved: {OUTPUT_PNG}")


if __name__ == "__main__":
    main()
