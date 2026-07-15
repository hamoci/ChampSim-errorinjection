#!/usr/bin/env python3
"""
Page offline threshold sensitivity (pin-off only).

Story: motivate the choice of page-offline threshold = 32. Under harsh CE
rates, aggressive (low) thresholds take pages offline prematurely and
collapse IPC; thr=32 preserves throughput while still bounding per-page
error count.

Source: results/normal_evaluation/2_retirement_threshold/
        retire_off_{thr}_{rate}_<trace>.txt
Normalization: per-workload ref = pin_off @ 1e-5 @ thr=32.
Hero line: 1e-8 (harsh). Supporting: 1e-7. Benign rates (1e-5/1e-6) are
flat within 1% and shown only as a single annotated band.
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

OUTPUT_CSV = os.path.join(SCRIPT_DIR, "fig7_page_offline_threshold_pin_off.csv")
OUTPUT_PNG = os.path.join(SCRIPT_DIR, "fig7_page_offline_threshold_pin_off.png")
OUTPUT_PDF = os.path.join(SCRIPT_DIR, "fig7_page_offline_threshold_pin_off.pdf")

RE_FNAME = re.compile(
    r"^retire_off_(?P<thr>\d+)_(?P<rate>1e-\d+)_(?P<trace>.+)\.txt$"
)

THRESHOLDS = [2, 4, 8, 16, 32]
RATES = ["1e-5", "1e-6", "1e-7", "1e-8"]  # benign → harsh
REF_RATE = "1e-5"
REF_THR = 32

# MTBCE (matches fig6 labels).
MTBCE_LABEL = {
    "1e-5": "36 ms",
    "1e-6": "3.6 ms",
    "1e-7": "360 μs",
    "1e-8": "36 μs",
}

# Hero = 1e-8 (harsh, dark). Secondary = 1e-7. Benign rates collapsed.
COLOR_HARSH = "#f08d39"   # strong red — the "danger" curve
COLOR_MED = "#5e7ac4"     # muted blue — supporting
COLOR_BENIGN = "#9aa0a6"  # gray — de-emphasized
COLOR_SELECT = "#c0392b"  # dark green — the recommended choice
COLOR_WARN_BG = "#fdecea"  # pale red band — aggressive page-offline region


def load_data():
    # out[(thr, rate)] = {workload: ipc}
    out = {}
    if not os.path.isdir(DATA_DIR):
        raise SystemExit(f"Data dir not found: {DATA_DIR}")
    for fname in sorted(os.listdir(DATA_DIR)):
        m = RE_FNAME.match(fname)
        if not m:
            continue
        metrics = extract_metrics(os.path.join(DATA_DIR, fname))
        ipc = metrics.ipc if metrics.ipc is not None else 0.0
        wl = extract_workload(m.group("trace"))
        key = (int(m.group("thr")), m.group("rate"))
        out.setdefault(key, {})[wl] = ipc
    return out


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


def main():
    setup_style()
    data = load_data()

    ref = data.get((REF_THR, REF_RATE), {})
    if not ref:
        raise SystemExit(f"Missing reference: pin_off @ {REF_RATE} @ thr={REF_THR}")

    all_wls = set(ref.keys())
    for t in THRESHOLDS:
        for r in RATES:
            all_wls |= set(data.get((t, r), {}).keys())
    all_wls = sorted(all_wls)

    rows = []
    # norm[rate] = [gmean per threshold]
    norm = {r: [] for r in RATES}
    for r in RATES:
        for t in THRESHOLDS:
            d = data.get((t, r), {})
            vals = []
            for w in all_wls:
                denom = ref.get(w, 0.0)
                n = (d.get(w, 0.0) / denom) if denom > 0 else 0.0
                vals.append(n)
                rows.append({
                    "threshold": t, "rate": r, "workload": w,
                    "ipc": d.get(w, 0.0),
                    "ref_ipc_off_1e-5_thr32": denom,
                    "norm_ipc": n,
                })
            norm[r].append(gmean(vals))
    pd.DataFrame(rows).to_csv(OUTPUT_CSV, index=False)

    # ── Plot ──
    fig, ax = plt.subplots(figsize=(3.74, 1.975))

    x_vals = np.array(THRESHOLDS, dtype=float)
    xlim_lo = THRESHOLDS[0] / 1.25
    xlim_hi = THRESHOLDS[-1] * 1.45

    # No-error reference.
    ax.axhline(1.0, color="#606060", linewidth=0.7,
               linestyle=":", zorder=1.5)
    ax.text(xlim_lo * 1.02, 1.015, "No-error upper bound",
            fontsize=6.8, color="#606060", va="bottom", ha="left")

    # Supporting line: 1e-7.
    ax.plot(x_vals, norm["1e-7"],
            color=COLOR_MED, linewidth=1.4, linestyle="--",
            marker="s", markersize=5.5, markerfacecolor="white",
            markeredgecolor=COLOR_MED, markeredgewidth=1.2,
            label=r"CE Rate $10^{7}$/hr", zorder=3)

    # Hero line: 1e-8. Marker at thr=32 hidden so the green "Selected" star is clean.
    ax.plot(x_vals, norm["1e-8"],
            color=COLOR_HARSH, linewidth=2.4, linestyle="-",
            zorder=4, label=r"CE Rate $10^{8}$/hr")
    ax.scatter(x_vals[:-1], norm["1e-8"][:-1],
               s=8**2, marker="o",
               facecolor=COLOR_HARSH, edgecolor="black", linewidth=0.6,
               zorder=4.1)

    # Selected-choice highlight: thr=32.
    sel_idx = THRESHOLDS.index(32)
    sel_x = float(THRESHOLDS[sel_idx])
    sel_y = norm["1e-8"][sel_idx]
    ax.scatter([sel_x], [sel_y], s=220, marker="*",
               color=COLOR_SELECT, edgecolor="black", linewidth=0.6,
               zorder=6)
    ax.text(sel_x, sel_y - 0.06, f"{sel_y*100:.0f}% IPC achieved",
            fontsize=8, fontweight="bold", color=COLOR_SELECT,
            ha="center", va="top")

    ax.set_xscale("log", base=2)
    ax.set_xticks(THRESHOLDS)
    ax.set_xticklabels([str(t) for t in THRESHOLDS])
    ax.set_xlim(xlim_lo, xlim_hi)
    ax.set_xlabel("Page Offline Threshold")

    ax.set_ylim(0.0, 1.12)
    ax.set_ylabel("Normalized IPC")
    ax.yaxis.grid(True, linestyle=":", linewidth=0.5, alpha=0.6)
    ax.set_axisbelow(True)

    leg = ax.legend(loc="lower center", handlelength=2.4,
                    borderpad=0.4, frameon=True, fancybox=False,
                    framealpha=1.0)
    leg.get_frame().set_facecolor("white")
    leg.get_frame().set_edgecolor("black")
    leg.get_frame().set_linewidth(0.4)

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

    print(f"{'thr':>4}  " + "  ".join(f"{r:>7}" for r in RATES))
    for i, t in enumerate(THRESHOLDS):
        print(f"{t:>4}  " + "  ".join(f"{norm[r][i]:7.4f}" for r in RATES))
    print(f"CSV: {OUTPUT_CSV}")
    print(f"PNG: {OUTPUT_PNG}")
    print(f"PDF: {OUTPUT_PDF}")


if __name__ == "__main__":
    main()
