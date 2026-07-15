#!/usr/bin/env python3
"""
Retirement Threshold Sensitivity — Per-Workload, Pinning ON vs OFF.

For each error rate (1e-8, 1e-7), show per-workload:
  Top:    IPC grouped by workload, bars for each (pinning, threshold) combo
  Bottom: Pages Retired
"""

import os
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
INPUT_CSV = os.path.join(SCRIPT_DIR, "4_retirement_threshold_sensitivity.csv")
OUTPUT_PNG = os.path.join(SCRIPT_DIR, "4b_retire_threshold_per_workload.png")

TARGET_RATES = [1e-8, 1e-7]
THRESHOLDS_ON = [4, 8, 16, 32]
THRESHOLDS_OFF = [4, 8, 16, 32]


def make_panels(df, rate, axes_row, rate_label):
    ax_ipc, ax_ret = axes_row

    df_rate = df[np.isclose(df["Error_Rate"], rate)].copy()
    if df_rate.empty:
        return

    workloads = sorted(df_rate["Workload"].unique())
    short_names = [w.split(".")[1].replace("_s", "") for w in workloads]
    n_wl = len(workloads)
    x = np.arange(n_wl)

    # Build bar configs: (label, pinning, threshold, color)
    bar_configs = []
    off_colors = ["#FFCDD2", "#EF9A9A", "#E57373", "#EF5350"]  # light to dark red
    on_colors = ["#BBDEFB", "#64B5F6", "#42A5F5", "#1E88E5"]    # light to dark blue

    for i, t in enumerate(THRESHOLDS_OFF):
        bar_configs.append((f"OFF t={t}", "OFF", t, off_colors[i]))
    for i, t in enumerate(THRESHOLDS_ON):
        bar_configs.append((f"ON t={t}", "ON", t, on_colors[i]))

    n_bars = len(bar_configs)
    total_width = 0.88
    bar_width = total_width / n_bars

    for panel_ax, col, ylabel in [(ax_ipc, "IPC", "IPC"), (ax_ret, "Pages_Retired", "Pages Retired")]:
        for idx, (label, pin, thresh, color) in enumerate(bar_configs):
            vals = []
            for wl in workloads:
                row = df_rate[(df_rate["Workload"] == wl) &
                              (df_rate["Pinning"] == pin) &
                              (df_rate["Threshold"] == thresh)]
                if len(row) > 0 and pd.notna(row[col].values[0]):
                    vals.append(row[col].values[0])
                else:
                    vals.append(0)
            offset = (idx - n_bars / 2 + 0.5) * bar_width
            panel_ax.bar(x + offset, vals, bar_width, label=label,
                         color=color, edgecolor="black", linewidth=0.3)

        panel_ax.set_ylabel(ylabel, fontsize=9)
        panel_ax.set_xticks(x)
        panel_ax.set_xticklabels(short_names, fontsize=7, rotation=0)
        panel_ax.yaxis.grid(True, linestyle="--", alpha=0.5, linewidth=0.5)
        panel_ax.set_axisbelow(True)
        panel_ax.tick_params(axis="y", labelsize=7)

    ax_ipc.set_title(f"Retirement Threshold Sensitivity — {rate_label}", fontsize=11, fontweight="bold")
    ax_ipc.legend(fontsize=5.5, loc="upper right", ncol=4)


def main():
    df = pd.read_csv(INPUT_CSV)

    fig, axes = plt.subplots(len(TARGET_RATES) * 2, 1, figsize=(14, 10))

    for i, rate in enumerate(TARGET_RATES):
        exp = int(-np.log10(rate))
        rate_label = f"MTBCE = $10^{{{exp}}}$"
        make_panels(df, rate, axes[i*2 : i*2+2], rate_label)

    plt.tight_layout(pad=0.8)
    plt.savefig(OUTPUT_PNG, dpi=300, bbox_inches="tight", facecolor="white", edgecolor="none")
    plt.close()
    print(f"PNG saved: {OUTPUT_PNG}")


if __name__ == "__main__":
    main()
