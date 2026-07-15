#!/usr/bin/env python3
"""
Fig 2: Baseline 4KB vs 2MB page performance comparison (vertical layout).

4KB is the normalized 1.0 reference; each bar shows 2MB-page IPC normalized
to the matching 4KB-page run.

Source: results/normal_evaluation_0506/baseline/
        champsim_{4kb,2mb}_32gb_<trace>.txt
"""

import os
import re

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib import rcParams

from common_normal import extract_metrics, extract_workload, gmean

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
RESULTS_DIR = os.path.join(SCRIPT_DIR, "results")
BASELINE_DIR = os.path.join(RESULTS_DIR, "baseline")
MPKI_REF_DIR = os.path.join(RESULTS_DIR, "4_llc_size_baseline")
MPKI_REF_SIZE = "2MB"
RE_MPKI_BASELINE = re.compile(
    r"^llc_baseline_(?P<size>\d+MB)_(?P<trace>.+)\.txt$"
)

OUTPUT_CSV = os.path.join(SCRIPT_DIR, "fig2_baseline_page.csv")
OUTPUT_PNG = os.path.join(SCRIPT_DIR, "fig2_baseline_page.png")
OUTPUT_PDF = os.path.join(SCRIPT_DIR, "fig2_baseline_page.pdf")

RE_FNAME = re.compile(r"^champsim_(?P<page>4kb|2mb)_32gb_(?P<trace>.+)\.txt$")

COLOR_2MB = "#0072B2"
EDGE = "black"


def short_name(workload: str) -> str:
    m = re.match(r"^\d+\.([A-Za-z0-9]+?)(?:_s)?$", workload)
    return m.group(1) if m else workload


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


def load_reference_mpki():
    mpki = {}
    if not os.path.isdir(MPKI_REF_DIR):
        return mpki
    for fname in sorted(os.listdir(MPKI_REF_DIR)):
        m = RE_MPKI_BASELINE.match(fname)
        if not m or m.group("size") != MPKI_REF_SIZE:
            continue
        metrics = extract_metrics(os.path.join(MPKI_REF_DIR, fname))
        wl = extract_workload(m.group("trace"))
        if (metrics.instructions and metrics.instructions > 0
                and metrics.llc_miss is not None):
            mpki[wl] = metrics.llc_miss / metrics.instructions * 1000.0
    return mpki


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
    recs = load_baseline()

    ref_mpki = load_reference_mpki()

    pairs = [(w, v["4kb"].ipc, v["2mb"].ipc)
             for w, v in recs.items() if "4kb" in v and "2mb" in v]
    pairs.sort(key=lambda t: (-ref_mpki.get(t[0], -1.0), short_name(t[0])))
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

    fig, ax = plt.subplots(figsize=(3.74, 1.975))

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
