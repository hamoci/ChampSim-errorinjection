#!/usr/bin/env python3
"""
Page offline threshold sensitivity with LLC pinning enabled.

Source: results/normal_evaluation/2_retirement_threshold/
        retire_on_{threshold}_{rate}_<trace>.txt

Normalization: per-workload no-error IPC from the 2MB LLC baseline. The plot
uses the same presentation style as fig7, but only shows the pinning-on runs
for thresholds 4, 8, 16, and 32.
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
DATA_DIR = os.path.join(BASE_DIR, "results", "normal_evaluation",
                        "2_retirement_threshold")
BASELINE_DIR = os.path.join(BASE_DIR, "results", "normal_evaluation",
                            "4_llc_size_baseline")

OUTPUT_CSV = os.path.join(SCRIPT_DIR, "fig7c_page_offline_threshold_pin_on.csv")
OUTPUT_PNG = os.path.join(SCRIPT_DIR, "fig7c_page_offline_threshold_pin_on.png")
OUTPUT_PDF = os.path.join(SCRIPT_DIR, "fig7c_page_offline_threshold_pin_on.pdf")

RE_FNAME = re.compile(
    r"^retire_on_(?P<thr>\d+)_(?P<rate>1e-\d+)_(?P<trace>.+)\.txt$"
)
RE_BASELINE = re.compile(r"^llc_baseline_(?P<size>\d+MB)_(?P<trace>.+)\.txt$")

REF_SIZE = "2MB"
THRESHOLDS = [4, 8, 16, 32]
RATES = ["1e-5", "1e-6", "1e-7", "1e-8"]
PLOT_RATES = ["1e-7", "1e-8"]
SELECTED_THR = 32

COLOR_HARSH = "#f08d39"
COLOR_MED = "#5e7ac4"
COLOR_SELECT = "#c0392b"


def setup_style():
    rcParams.update({
        "font.family": "sans-serif",
        "font.sans-serif": ["Helvetica", "Arial", "DejaVu Sans"],
        "font.size": 9,
        "axes.linewidth": 0.7,
        "axes.labelsize": 9,
        "axes.titlesize": 9,
        "xtick.labelsize": 8,
        "ytick.labelsize": 8,
        "legend.fontsize": 8,
        "pdf.fonttype": 42,
        "ps.fonttype": 42,
    })


def load_pinning_on_data():
    data = {}
    if not os.path.isdir(DATA_DIR):
        raise SystemExit(f"Data dir not found: {DATA_DIR}")

    for fname in sorted(os.listdir(DATA_DIR)):
        match = RE_FNAME.match(fname)
        if not match:
            continue
        threshold = int(match.group("thr"))
        rate = match.group("rate")
        if threshold not in THRESHOLDS or rate not in RATES:
            continue

        path = os.path.join(DATA_DIR, fname)
        metrics = extract_metrics(path)
        workload = extract_workload(match.group("trace"))
        data.setdefault((threshold, rate), {})[workload] = metrics.ipc or 0.0

    return data


def load_baseline_ipc():
    baseline = {}
    if not os.path.isdir(BASELINE_DIR):
        raise SystemExit(f"Baseline dir not found: {BASELINE_DIR}")

    for fname in sorted(os.listdir(BASELINE_DIR)):
        match = RE_BASELINE.match(fname)
        if not match or match.group("size") != REF_SIZE:
            continue
        metrics = extract_metrics(os.path.join(BASELINE_DIR, fname))
        workload = extract_workload(match.group("trace"))
        baseline[workload] = metrics.ipc or 0.0

    return baseline


def main():
    setup_style()
    data = load_pinning_on_data()
    baseline = load_baseline_ipc()

    workloads = set(baseline.keys())
    for wlmap in data.values():
        workloads |= set(wlmap.keys())
    workloads = sorted(workloads)

    rows = []
    norm = {rate: [] for rate in RATES}
    included = {rate: [] for rate in RATES}

    for rate in RATES:
        for threshold in THRESHOLDS:
            cur = data.get((threshold, rate), {})
            vals = []
            count = 0

            for workload in workloads:
                base_ipc = baseline.get(workload, 0.0)
                ipc = cur.get(workload, 0.0)
                use = base_ipc > 0.0 and ipc > 0.0
                norm_ipc = ipc / base_ipc if use else 0.0
                if use:
                    vals.append(norm_ipc)
                    count += 1

                rows.append({
                    "threshold": threshold,
                    "rate": rate,
                    "workload": workload,
                    "ipc": ipc,
                    "baseline_ipc_2MB_no_error": base_ipc,
                    "norm_ipc": norm_ipc,
                    "included_in_gmean": use,
                })

            norm[rate].append(gmean(vals))
            included[rate].append(count)

    pd.DataFrame(rows).to_csv(OUTPUT_CSV, index=False)

    fig, ax = plt.subplots(figsize=(3.74, 1.975))
    x_vals = np.array(THRESHOLDS, dtype=float)
    xlim_lo = THRESHOLDS[0] / 1.25
    xlim_hi = THRESHOLDS[-1] * 1.45

    ax.axhline(1.0, color="#606060", linewidth=0.7,
               linestyle=":", zorder=1.5)
    ax.text(xlim_lo * 1.02, 1.015, "No-error upper bound",
            fontsize=6.8, color="#606060", va="bottom", ha="left")

    ax.plot(
        x_vals, norm["1e-7"],
        color=COLOR_MED, linewidth=1.4, linestyle="--",
        marker="s", markersize=5.5, markerfacecolor="white",
        markeredgecolor=COLOR_MED, markeredgewidth=1.2,
        label=r"CE Rate $10^{7}$/hr", zorder=3
    )

    ax.plot(
        x_vals, norm["1e-8"],
        color=COLOR_HARSH, linewidth=2.4, linestyle="-",
        zorder=4, label=r"CE Rate $10^{8}$/hr"
    )
    ax.scatter(
        x_vals[:-1], norm["1e-8"][:-1],
        s=8**2, marker="o",
        facecolor=COLOR_HARSH, edgecolor="black", linewidth=0.6,
        zorder=4.1
    )

    sel_idx = THRESHOLDS.index(SELECTED_THR)
    sel_x = float(THRESHOLDS[sel_idx])
    sel_y = norm["1e-8"][sel_idx]
    ax.scatter(
        [sel_x], [sel_y], s=220, marker="*",
        color=COLOR_SELECT, edgecolor="black", linewidth=0.6,
        zorder=6
    )
    ax.text(
        sel_x * 0.72, sel_y - 0.075, f"{sel_y * 100:.0f}% IPC achieved",
        fontsize=8, fontweight="bold", color=COLOR_SELECT,
        ha="left", va="top"
    )

    ax.set_xscale("log", base=2)
    ax.set_xticks(THRESHOLDS)
    ax.set_xticklabels([str(t) for t in THRESHOLDS])
    ax.set_xlim(xlim_lo, xlim_hi)
    ax.set_xlabel("Page Offline Threshold")

    ax.set_ylim(0.4, 1.08)
    ax.set_ylabel("Normalized IPC")
    ax.yaxis.grid(True, linestyle=":", linewidth=0.5, alpha=0.6)
    ax.set_axisbelow(True)

    legend = ax.legend(
        loc="lower center", handlelength=2.4,
        borderpad=0.4, frameon=True, fancybox=False,
        framealpha=1.0
    )
    legend.get_frame().set_facecolor("white")
    legend.get_frame().set_edgecolor("black")
    legend.get_frame().set_linewidth(0.4)

    for spine in ax.spines.values():
        spine.set_visible(True)
        spine.set_linewidth(0.7)
        spine.set_color("black")

    plt.tight_layout(pad=0.3)
    plt.savefig(OUTPUT_PNG, dpi=400,
                facecolor="white", edgecolor="none")
    plt.savefig(OUTPUT_PDF,
                facecolor="white", edgecolor="none")
    plt.close()

    print(f"{'thr':>4}  " + "  ".join(f"{rate:>7}" for rate in PLOT_RATES))
    for idx, threshold in enumerate(THRESHOLDS):
        print(f"{threshold:>4}  " +
              "  ".join(f"{norm[rate][idx]:7.4f}" for rate in PLOT_RATES))
    print(f"CSV: {OUTPUT_CSV}")
    print(f"PNG: {OUTPUT_PNG}")
    print(f"PDF: {OUTPUT_PDF}")


if __name__ == "__main__":
    main()
