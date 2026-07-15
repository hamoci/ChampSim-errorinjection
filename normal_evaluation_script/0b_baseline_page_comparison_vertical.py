#!/usr/bin/env python3
"""
Baseline: 4KB vs 2MB page performance comparison.

Vertical one-column variant of fig0. 4KB is the normalized 1.0 reference,
and each bar shows 2MB-page IPC normalized to the matching 4KB-page run.
"""

import importlib.util
import os

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib import rcParams

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
BASE_FIG0 = os.path.join(SCRIPT_DIR, "0_baseline_page_comparison.py")

OUTPUT_CSV = os.path.join(SCRIPT_DIR, "fig0_baseline_page_comparison_vertical.csv")
OUTPUT_PNG = os.path.join(SCRIPT_DIR, "fig0_baseline_page_comparison_vertical.png")
OUTPUT_PDF = os.path.join(SCRIPT_DIR, "fig0_baseline_page_comparison_vertical.pdf")

COLOR_2MB = "#5e7ac4"   # muted blue
EDGE = "black"


def load_fig0_module():
    spec = importlib.util.spec_from_file_location("fig0_baseline_page_comparison",
                                                  BASE_FIG0)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def setup_style():
    rcParams.update({
        "font.family": "sans-serif",
        "font.sans-serif": ["Helvetica", "Arial", "DejaVu Sans"],
        "font.size": 8,
        "axes.linewidth": 0.7,
        "axes.labelsize": 8,
        "axes.titlesize": 8,
        "xtick.labelsize": 5.8,
        "ytick.labelsize": 7,
        "legend.fontsize": 7,
        "pdf.fonttype": 42,
        "ps.fonttype": 42,
    })


def main():
    setup_style()
    fig0 = load_fig0_module()
    recs = fig0.load_baseline()

    pairs = [(w, v["4kb"].ipc, v["2mb"].ipc)
             for w, v in recs.items() if "4kb" in v and "2mb" in v]
    pairs.sort(key=lambda t: fig0.short_name(t[0]))
    if not pairs:
        raise SystemExit("No matching 4KB/2MB pairs found.")

    workloads = [fig0.short_name(w) for w, _, _ in pairs]
    ipc4 = [p[1] for p in pairs]
    ipc2 = [p[2] for p in pairs]
    speedup = [b / a if a > 0 else 0 for a, b in zip(ipc4, ipc2)]

    g4 = fig0.gmean(ipc4)
    g2 = fig0.gmean(ipc2)
    g_su = g2 / g4 if g4 > 0 else 0

    labels = workloads + ["gmean"]
    ipc4_plot = ipc4 + [g4]
    ipc2_plot = ipc2 + [g2]
    su_plot = speedup + [g_su]

    pd.DataFrame({
        "workload": [p[0] for p in pairs] + ["GMEAN"],
        "short": labels,
        "ipc_4kb": ipc4_plot,
        "ipc_2mb": ipc2_plot,
        "speedup_2mb_over_4kb": su_plot,
    }).to_csv(OUTPUT_CSV, index=False)

    fig, ax = plt.subplots(figsize=(3.35, 1.75))

    x = np.arange(len(labels))
    norm2 = np.array(su_plot)
    bars = ax.bar(x, norm2, width=0.62,
                  label="2MB page", color=COLOR_2MB,
                  edgecolor=EDGE, linewidth=0.55)
    bars[-1].set_linewidth(1.15)

    baseline = ax.axhline(1.0, color="black", linewidth=0.75,
                          linestyle=":", label="4KB page")
    ax.yaxis.grid(True, linestyle=":", linewidth=0.5, alpha=0.6)
    ax.set_axisbelow(True)

    ymax = max(norm2) + 0.20
    ax.set_ylim(0, ymax)
    ax.set_ylabel("Normalized IPC")
    ax.set_yticks([0.0, 0.5, 1.0, 1.5, 2.0])
    ax.set_yticklabels(["0", "0.5", "1.0", "1.5", "2.0"])

    ax.set_xticks(x)
    ax.set_xticklabels(labels, rotation=45, ha="right", rotation_mode="anchor")
    ax.tick_params(axis="x", which="both", length=2, pad=1)
    ax.tick_params(axis="y", which="both", length=2, pad=1)
    ax.set_xlim(-0.55, len(labels) - 0.45)

    # Separator before gmean.
    ax.axvline(len(workloads) - 0.5, color="gray",
               linestyle="--", linewidth=0.6, alpha=0.7)
    ax.text(len(labels) - 1, g_su + 0.04, f"{g_su:.2f}x",
            ha="center", va="bottom", fontsize=6.4, fontweight="bold")

    for tick in ax.get_xticklabels():
        if tick.get_text() == "gmean":
            tick.set_fontweight("bold")

    ax.legend(handles=[baseline, bars[0]],
              labels=["4KB page", "2MB page"],
              loc="upper left", ncol=2, handlelength=1.2,
              columnspacing=0.7, borderpad=0.15, borderaxespad=0.25,
              handletextpad=0.35, fontsize=6.3, frameon=False)

    for spine in ax.spines.values():
        spine.set_visible(True)
        spine.set_linewidth(0.7)
        spine.set_color("black")

    plt.tight_layout(pad=0.25)
    plt.savefig(OUTPUT_PNG, dpi=400, bbox_inches="tight",
                facecolor="white", edgecolor="none")
    plt.savefig(OUTPUT_PDF, bbox_inches="tight",
                facecolor="white", edgecolor="none")
    plt.close()

    print(f"Workloads: {len(workloads)}")
    print(f"GMEAN IPC  4KB={g4:.4f}  2MB={g2:.4f}  speedup={g_su:.3f}x")
    print(f"CSV: {OUTPUT_CSV}")
    print(f"PNG: {OUTPUT_PNG}")
    print(f"PDF: {OUTPUT_PDF}")


if __name__ == "__main__":
    main()
