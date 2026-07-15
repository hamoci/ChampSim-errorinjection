#!/usr/bin/env python3
"""
No-error baseline vs Conventional Page offline.

Source:
  - results/normal_evaluation/4_llc_size_baseline/
      llc_baseline_2MB_<trace>.txt              (no errors)
  - results/normal_evaluation/2_retirement_threshold/
      retire_off_2_{1e-5..1e-8}_<trace>.txt     (Conventional Page offline,
                                                 retirement threshold = 2)

Normalization: per-workload IPC normalized to the matching no-error 2MB LLC
baseline. The plotted curve is the GMEAN across workloads.
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
BASELINE_DIR = os.path.join(BASE_DIR, "results", "normal_evaluation",
                            "4_llc_size_baseline")
SWEEP_DIR = os.path.join(BASE_DIR, "results", "normal_evaluation",
                         "2_retirement_threshold")

OUTPUT_CSV = os.path.join(SCRIPT_DIR, "fig13_no_error_vs_offline.csv")
OUTPUT_PNG = os.path.join(SCRIPT_DIR, "fig13_no_error_vs_offline.png")
OUTPUT_PDF = os.path.join(SCRIPT_DIR, "fig13_no_error_vs_offline.pdf")
WASTE_CSV = os.path.join(SCRIPT_DIR, "fig8_capacity_waste.csv")

RE_BASELINE = re.compile(r"^llc_baseline_(?P<size>\d+MB)_(?P<trace>.+)\.txt$")
RE_OFFLINE = re.compile(r"^retire_off_2_(?P<rate>1e-\d+)_(?P<trace>.+)\.txt$")

REF_SIZE = "2MB"

# Simulator semantics: 1e-5 is the most benign point, 1e-8 is harshest.
RATES = ["1e-5", "1e-6", "1e-7", "1e-8"]
MTBCE_LABEL = {
    "1e-5": "36 ms",
    "1e-6": "3.6 ms",
    "1e-7": "360 us",
    "1e-8": "36 us",
}

COLOR_OFFLINE = "#f08d39"   # orange
COLOR_BASE = "#303030"
COLOR_WASTE = "#5e7ac4"     # blue diamond for capacity waste markers


def load_capacity_waste():
    """Mean Conventional Page Offline waste (MB) per rate, read from fig8 CSV."""
    if not os.path.isfile(WASTE_CSV):
        return None
    df = pd.read_csv(WASTE_CSV, dtype={"rate": str})
    return {rate: float(df[df["rate"] == rate]["pin_off_waste_MB"].mean())
            for rate in RATES}


def load_no_error_baseline():
    out = {}
    if not os.path.isdir(BASELINE_DIR):
        raise SystemExit(f"Baseline dir not found: {BASELINE_DIR}")

    for fname in sorted(os.listdir(BASELINE_DIR)):
        match = RE_BASELINE.match(fname)
        if not match or match.group("size") != REF_SIZE:
            continue

        metrics = extract_metrics(os.path.join(BASELINE_DIR, fname))
        wl = extract_workload(match.group("trace"))
        out[wl] = metrics.ipc if metrics.ipc is not None else 0.0

    return out


def load_offline_sweep():
    out = {rate: {} for rate in RATES}
    if not os.path.isdir(SWEEP_DIR):
        raise SystemExit(f"Sweep dir not found: {SWEEP_DIR}")

    for fname in sorted(os.listdir(SWEEP_DIR)):
        match = RE_OFFLINE.match(fname)
        if not match:
            continue

        rate = match.group("rate")
        if rate not in out:
            continue

        metrics = extract_metrics(os.path.join(SWEEP_DIR, fname))
        wl = extract_workload(match.group("trace"))
        out[rate][wl] = metrics.ipc if metrics.ipc is not None else 0.0

    return out


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
        "legend.fontsize": 6.8,
        "pdf.fonttype": 42,
        "ps.fonttype": 42,
    })


def main():
    setup_style()

    baseline = load_no_error_baseline()
    offline = load_offline_sweep()
    if not baseline:
        raise SystemExit(f"No no-error baseline data found for {REF_SIZE}")

    all_wls = set(baseline.keys())
    for rate in RATES:
        all_wls |= set(offline[rate].keys())
    all_wls = sorted(all_wls)

    rows = []
    offline_gmean = []
    for rate in RATES:
        vals = []
        for wl in all_wls:
            ref_ipc = baseline.get(wl, 0.0)
            off_ipc = offline[rate].get(wl, 0.0)
            norm = off_ipc / ref_ipc if ref_ipc > 0 else 0.0
            vals.append(norm)
            rows.append({
                "rate": rate,
                "mtbce": MTBCE_LABEL[rate],
                "workload": wl,
                "baseline_ipc_no_error_2mb": ref_ipc,
                "offline_ipc": off_ipc,
                "norm_offline_vs_no_error": norm,
            })
        offline_gmean.append(gmean(vals))

    pd.DataFrame(rows).to_csv(OUTPUT_CSV, index=False)

    x = np.arange(len(RATES), dtype=float)
    fig, ax = plt.subplots(figsize=(3.35, 1.45))

    ax.bar(x, offline_gmean, width=0.56,
           color=COLOR_OFFLINE, edgecolor="black", linewidth=0.6,
           zorder=3)

    # Only label the worst-case bar (smallest IPC) — draws the eye to the collapse.
    for xi, value in zip(x, offline_gmean):
        if value < 0.2:
            ax.text(xi, value + 0.025, f"{value:.2f}",
                    ha="center", va="bottom", fontsize=6.7,
                    fontweight="bold")

    ax.set_xticks(x)
    ax.set_xticklabels(["1", "10", "100", "1000"])
    ax.set_xlabel(r"CE Rate ($\times 10^{5}$ errors/hour)")
    ax.set_xlim(x[0] - 0.45, x[-1] + 0.45)

    ax.set_ylim(0.0, 1.08)
    ax.set_ylabel("Normalized IPC")
    ax.yaxis.grid(True, linestyle=":", linewidth=0.5, alpha=0.6)
    ax.set_axisbelow(True)

    for spine in ax.spines.values():
        spine.set_visible(True)
        spine.set_linewidth(0.7)
        spine.set_color("black")

    # Capacity waste markers on right (log) axis: shows the dual cost of
    # Conventional Page Offline — IPC drops AND capacity waste explodes.
    waste = load_capacity_waste()
    if waste is not None:
        ax2 = ax.twinx()
        ax2.set_yscale("log")
        ax2.set_ylim(0.1, 1e5)
        waste_vals = [waste[rate] for rate in RATES]
        ax2.plot(x, waste_vals,
                 color=COLOR_WASTE, linewidth=0.9, linestyle=":",
                 marker="D", markersize=5.5,
                 markerfacecolor=COLOR_WASTE, markeredgecolor="black",
                 markeredgewidth=0.5, zorder=5)
        ax2.set_ylabel("Capacity Waste (MB)", fontsize=7, labelpad=2)
        ax2.tick_params(axis="y", labelsize=6.2)
        ax2.grid(False)
        for spine in ax2.spines.values():
            spine.set_visible(True)
            spine.set_linewidth(0.7)
            spine.set_color("black")

        from matplotlib.lines import Line2D
        from matplotlib.patches import Patch
        legend_handles = [
            Patch(facecolor=COLOR_OFFLINE, edgecolor="black", linewidth=0.5,
                  label="IPC"),
            Line2D([0], [0], marker="D", color="none",
                   markerfacecolor=COLOR_WASTE, markeredgecolor="black",
                   markeredgewidth=0.5, markersize=5,
                   label="Waste"),
        ]
        leg = ax.legend(handles=legend_handles, ncol=2,
                        loc="lower center", bbox_to_anchor=(0.5, 1.04),
                        fontsize=6.5, handlelength=1.1, handletextpad=0.4,
                        columnspacing=1.2, borderpad=0.3, borderaxespad=0.0,
                        frameon=True, fancybox=False, framealpha=1.0,
                        facecolor="white", edgecolor="black")
        leg.get_frame().set_linewidth(0.4)

    plt.tight_layout(pad=0.25)
    plt.savefig(OUTPUT_PNG, dpi=400, bbox_inches="tight",
                facecolor="white", edgecolor="none")
    plt.savefig(OUTPUT_PDF, bbox_inches="tight",
                facecolor="white", edgecolor="none")
    plt.close()

    print(f"Workloads: {len(all_wls)}")
    print("Rate    MTBCE    Conventional Page offline norm IPC")
    for rate, val in zip(RATES, offline_gmean):
        print(f"{rate:>6}  {MTBCE_LABEL[rate]:>6}  {val:18.4f}")
    print(f"CSV: {OUTPUT_CSV}")
    print(f"PNG: {OUTPUT_PNG}")
    print(f"PDF: {OUTPUT_PDF}")


if __name__ == "__main__":
    main()
