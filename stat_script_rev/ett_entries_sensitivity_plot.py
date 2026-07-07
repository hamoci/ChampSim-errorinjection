#!/usr/bin/env python3
"""Plot ETT entries sensitivity: IPC, error way hits, ETT evictions, invalidated lines."""

import os
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.ticker as ticker

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CSV_PATH = os.path.join(SCRIPT_DIR, "ett_entries_summary.csv")

# MTBCE ordering (high error → low error)
BER_ORDER = ["1e-8", "1e-7", "1e-6", "1e-5"]
BER_LABELS = {"1e-8": "MTBCE=1e-8", "1e-7": "MTBCE=1e-7", "1e-6": "MTBCE=1e-6", "1e-5": "MTBCE=1e-5"}
BER_COLORS = {"1e-8": "#C0392B", "1e-7": "#E67E22", "1e-6": "#2980B9", "1e-5": "#27AE60"}
BER_MARKERS = {"1e-8": "o", "1e-7": "s", "1e-6": "^", "1e-5": "D"}


def main():
    df = pd.read_csv(CSV_PATH, dtype={"ber": str})

    entries_vals = sorted(df["entries"].unique())
    x_ticks = list(range(len(entries_vals)))
    x_labels = [str(e) for e in entries_vals]

    fig, axes = plt.subplots(2, 2, figsize=(12, 8))

    # ---- (a) IPC Gmean ----
    ax = axes[0, 0]
    for ber in BER_ORDER:
        sub = df[df["ber"] == ber].sort_values("entries")
        ax.plot(x_ticks, sub["ipc_gmean"].values,
                marker=BER_MARKERS[ber], color=BER_COLORS[ber],
                label=BER_LABELS[ber], linewidth=1.5, markersize=5)
    ax.set_ylabel("IPC (Gmean)", fontsize=10)
    ax.set_title("(a) IPC vs ETT Entries", fontsize=11)
    ax.set_xticks(x_ticks)
    ax.set_xticklabels(x_labels, fontsize=8)
    ax.set_xlabel("ETT Entries", fontsize=9)
    ax.legend(fontsize=7, loc="best")
    ax.yaxis.grid(True, linestyle="--", alpha=0.4)
    ax.set_axisbelow(True)

    # ---- (b) Error Way Hits ----
    ax = axes[0, 1]
    for ber in BER_ORDER:
        sub = df[df["ber"] == ber].sort_values("entries")
        ax.plot(x_ticks, sub["avg_error_way_hits"].values,
                marker=BER_MARKERS[ber], color=BER_COLORS[ber],
                label=BER_LABELS[ber], linewidth=1.5, markersize=5)
    ax.set_ylabel("Avg Error Way Hits", fontsize=10)
    ax.set_title("(b) Error Way Hits (DRAM access avoided)", fontsize=11)
    ax.set_xticks(x_ticks)
    ax.set_xticklabels(x_labels, fontsize=8)
    ax.set_xlabel("ETT Entries", fontsize=9)
    ax.legend(fontsize=7, loc="best")
    ax.yaxis.grid(True, linestyle="--", alpha=0.4)
    ax.set_axisbelow(True)

    # ---- (c) ETT Evictions ----
    ax = axes[1, 0]
    for ber in BER_ORDER:
        sub = df[df["ber"] == ber].sort_values("entries")
        ax.plot(x_ticks, sub["avg_ett_evictions"].values,
                marker=BER_MARKERS[ber], color=BER_COLORS[ber],
                label=BER_LABELS[ber], linewidth=1.5, markersize=5)
    ax.set_ylabel("Avg ETT Evictions", fontsize=10)
    ax.set_title("(c) ETT Evictions", fontsize=11)
    ax.set_xticks(x_ticks)
    ax.set_xticklabels(x_labels, fontsize=8)
    ax.set_xlabel("ETT Entries", fontsize=9)
    ax.legend(fontsize=7, loc="best")
    ax.yaxis.grid(True, linestyle="--", alpha=0.4)
    ax.set_axisbelow(True)

    # ---- (d) Invalidated Lines (from ETT eviction) ----
    ax = axes[1, 1]
    for ber in BER_ORDER:
        sub = df[df["ber"] == ber].sort_values("entries")
        ax.plot(x_ticks, sub["avg_ett_evict_inval_lines"].values,
                marker=BER_MARKERS[ber], color=BER_COLORS[ber],
                label=BER_LABELS[ber], linewidth=1.5, markersize=5)
    ax.set_ylabel("Avg Invalidated Lines", fontsize=10)
    ax.set_title("(d) Cache Lines Invalidated by ETT Eviction", fontsize=11)
    ax.set_xticks(x_ticks)
    ax.set_xticklabels(x_labels, fontsize=8)
    ax.set_xlabel("ETT Entries", fontsize=9)
    ax.legend(fontsize=7, loc="best")
    ax.yaxis.grid(True, linestyle="--", alpha=0.4)
    ax.set_axisbelow(True)

    plt.suptitle("ETT Entries Sensitivity Analysis", fontsize=13, fontweight="bold", y=0.98)
    plt.tight_layout(rect=[0, 0, 1, 0.95])

    out_path = os.path.join(SCRIPT_DIR, "ett_entries_sensitivity.png")
    plt.savefig(out_path, dpi=300, bbox_inches="tight", facecolor="white")
    plt.close()
    print(f"Saved: {out_path}")

    # Also save PDF
    out_pdf = os.path.join(SCRIPT_DIR, "ett_entries_sensitivity.pdf")
    fig2, axes2 = plt.subplots(2, 2, figsize=(12, 8))

    for i, (ax_src, ax_dst) in enumerate(zip(axes.flat, axes2.flat)):
        for line in ax_src.get_lines():
            ax_dst.plot(line.get_xdata(), line.get_ydata(),
                       marker=line.get_marker(), color=line.get_color(),
                       label=line.get_label(), linewidth=1.5, markersize=5)
        ax_dst.set_ylabel(ax_src.get_ylabel(), fontsize=10)
        ax_dst.set_title(ax_src.get_title(), fontsize=11)
        ax_dst.set_xticks(x_ticks)
        ax_dst.set_xticklabels(x_labels, fontsize=8)
        ax_dst.set_xlabel(ax_src.get_xlabel(), fontsize=9)
        ax_dst.legend(fontsize=7, loc="best")
        ax_dst.yaxis.grid(True, linestyle="--", alpha=0.4)
        ax_dst.set_axisbelow(True)

    plt.suptitle("ETT Entries Sensitivity Analysis", fontsize=13, fontweight="bold", y=0.98)
    plt.tight_layout(rect=[0, 0, 1, 0.95])
    plt.savefig(out_pdf, dpi=300, bbox_inches="tight", facecolor="white")
    plt.close()
    print(f"Saved: {out_pdf}")

    # Print key insights
    print("\n=== Key Observations ===")
    for ber in BER_ORDER:
        sub = df[df["ber"] == ber].sort_values("entries")
        ipc_1 = sub[sub["entries"] == 1]["ipc_gmean"].values[0]
        ipc_256 = sub[sub["entries"] == 256]["ipc_gmean"].values[0]
        hits_1 = sub[sub["entries"] == 1]["avg_error_way_hits"].values[0]
        hits_256 = sub[sub["entries"] == 256]["avg_error_way_hits"].values[0]
        evict_1 = sub[sub["entries"] == 1]["avg_ett_evictions"].values[0]
        evict_256 = sub[sub["entries"] == 256]["avg_ett_evictions"].values[0]
        print(f"  {ber}: IPC {ipc_1:.4f}→{ipc_256:.4f} ({(ipc_256-ipc_1)/ipc_1*100:+.1f}%), "
              f"Hits {hits_1:.0f}→{hits_256:.0f}, "
              f"Evictions {evict_1:.0f}→{evict_256:.0f}")


if __name__ == "__main__":
    main()
