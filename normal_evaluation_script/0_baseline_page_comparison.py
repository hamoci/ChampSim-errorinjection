#!/usr/bin/env python3
"""
Baseline: 4KB vs 2MB page performance comparison.

Source: results/normal_evaluation/baseline/champsim_{4kb,2mb}_32gb_<workload>.txt
Output: single panel with normalized IPC (4KB = 1.0 reference), 2MB shown as speedup.
Top-tier architecture conference style (HPCA/ISCA/MICRO).
"""

import os
import re
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib import rcParams

from common_normal import extract_metrics, extract_workload, gmean

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
BASE_DIR = os.path.dirname(SCRIPT_DIR)
BASELINE_DIR = os.path.join(BASE_DIR, "results", "normal_evaluation", "baseline")

OUTPUT_CSV = os.path.join(SCRIPT_DIR, "fig0_baseline_page_comparison.csv")
OUTPUT_PNG = os.path.join(SCRIPT_DIR, "fig0_baseline_page_comparison.png")
OUTPUT_PDF = os.path.join(SCRIPT_DIR, "fig0_baseline_page_comparison.pdf")

RE_FNAME = re.compile(r"^champsim_(?P<page>4kb|2mb)_32gb_(?P<trace>.+)\.txt$")

COLOR_2MB = "#5e7ac4"   # muted blue
EDGE = "black"


def load_baseline():
    records = {}
    if not os.path.isdir(BASELINE_DIR):
        raise SystemExit(f"Baseline dir not found: {BASELINE_DIR}")
    for fname in sorted(os.listdir(BASELINE_DIR)):
        m = RE_FNAME.match(fname)
        if not m:
            continue
        path = os.path.join(BASELINE_DIR, fname)
        metrics = extract_metrics(path)
        if metrics.ipc is None:
            continue
        wl = extract_workload(m.group("trace"))
        records.setdefault(wl, {})[m.group("page")] = metrics
    return records


def short_name(workload: str) -> str:
    m = re.match(r"^\d+\.([A-Za-z0-9]+?)(?:_s)?$", workload)
    return m.group(1) if m else workload


def setup_style():
    rcParams.update({
        "font.family": "sans-serif",
        "font.sans-serif": ["Helvetica", "Arial", "DejaVu Sans"],
        "font.size": 8,
        "axes.linewidth": 0.7,
        "axes.labelsize": 8,
        "axes.titlesize": 8,
        "xtick.labelsize": 7,
        "ytick.labelsize": 7,
        "legend.fontsize": 7,
        "pdf.fonttype": 42,
        "ps.fonttype": 42,
    })


def main():
    setup_style()
    recs = load_baseline()

    pairs = [(w, v["4kb"].ipc, v["2mb"].ipc)
             for w, v in recs.items() if "4kb" in v and "2mb" in v]
    pairs.sort(key=lambda t: short_name(t[0]))
    if not pairs:
        raise SystemExit("No matching 4KB/2MB pairs found.")

    workloads = [short_name(w) for w, _, _ in pairs]
    ipc4 = [p[1] for p in pairs]
    ipc2 = [p[2] for p in pairs]
    speedup = [b / a if a > 0 else 0 for a, b in zip(ipc4, ipc2)]

    g4 = gmean(ipc4)
    g2 = gmean(ipc2)
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

    # One-column paper layout: 2MB bars against the 4KB=1.0 baseline.
    fig, ax = plt.subplots(figsize=(3.35, 2.65))

    y = np.arange(len(labels))
    norm2 = np.array(su_plot)  # equivalent to ipc_2mb / ipc_4kb

    bars = ax.barh(y, norm2, 0.58,
                   label="2MB page", color=COLOR_2MB,
                   edgecolor=EDGE, linewidth=0.55)
    bars[-1].set_linewidth(1.2)

    baseline = ax.axvline(1.0, color="black", linewidth=0.75,
                          linestyle=":", label="4KB page")
    ax.xaxis.grid(True, linestyle=":", linewidth=0.5, alpha=0.6)
    ax.set_axisbelow(True)

    xmax = max(norm2) + 0.28
    ax.set_xlim(0, xmax)
    ax.set_xlabel("Normalized IPC (4KB = 1.0)")
    ax.set_xticks([0.0, 0.5, 1.0, 1.5, 2.0])
    ax.set_xticklabels(["0", "0.5", "1.0", "1.5", "2.0"])

    ax.set_yticks(y)
    ax.set_yticklabels(labels)
    ax.invert_yaxis()
    ax.tick_params(axis="y", which="both", length=0, pad=2)
    ax.tick_params(axis="x", which="both", length=2, pad=1)

    # Separator before gmean.
    ax.axhline(len(workloads) - 0.5, color="gray",
               linestyle="--", linewidth=0.6, alpha=0.7)

    for yi, v in zip(y, norm2):
        ax.text(v + 0.035, yi, f"{v:.2f}x",
                ha="left", va="center", fontsize=6.4)

    for tick in ax.get_yticklabels():
        if tick.get_text() == "gmean":
            tick.set_fontweight("bold")

    ax.legend(handles=[baseline, bars[0]],
              labels=["4KB page", "2MB page"],
              loc="upper center", bbox_to_anchor=(0.5, 1.10),
              ncol=2, handlelength=1.4, columnspacing=0.8,
              borderpad=0.15, borderaxespad=0.2,
              handletextpad=0.35, fontsize=6.7,
              frameon=False)

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
