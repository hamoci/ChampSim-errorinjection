#!/usr/bin/env python3
"""
Fig 10: LLC Capacity Sensitivity *with LLC Pinning enabled*, across CE rates.

Companion to Fig 9: Fig 9 shows that shrinking LLC is cheap in an error-free
baseline (motivation for spending a few ways on pinning). This figure shows
that once pinning is turned on, that property is preserved across the full
CE-rate spectrum — i.e. pinning's benefit is robust to LLC capacity.

X-axis reads left → right as "capacity being given up" (8 MB full →
1 MB quartered). Y-axis is per-workload GMEAN normalized IPC with the
error-free 8 MB run as the reference (same denominator as Fig 9), so the
four rate curves share a common zero and the separation between them is
directly comparable.

Source: pin_on LLC sensitivity   — results/normal_evaluation/5_llc_size_sensitivity/
                                    llc_{1,2,4,8}MB_{1e-5..1e-8}_<trace>.txt
        error-free baseline ref  — results/normal_evaluation/4_llc_size_baseline/
                                    llc_baseline_8MB_<trace>.txt
Output: fig10_llc_sensitivity_pin_on.{png,pdf,csv}
"""

import os
import re
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib import rcParams
from matplotlib.ticker import FormatStrFormatter, MultipleLocator

from common_normal import extract_metrics, extract_workload, gmean

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
BASE_DIR = os.path.dirname(SCRIPT_DIR)
SENS_DIR = os.path.join(BASE_DIR, "results", "normal_evaluation",
                        "5_llc_size_sensitivity")
BASELINE_DIR = os.path.join(BASE_DIR, "results", "normal_evaluation",
                            "4_llc_size_baseline")

OUTPUT_CSV = os.path.join(SCRIPT_DIR, "fig10_llc_sensitivity_pin_on.csv")
OUTPUT_PNG = os.path.join(SCRIPT_DIR, "fig10_llc_sensitivity_pin_on.png")
OUTPUT_PDF = os.path.join(SCRIPT_DIR, "fig10_llc_sensitivity_pin_on.pdf")

RE_SENS = re.compile(
    r"^llc_(?P<size>\d+MB)_(?P<rate>1e-\d+)_(?P<trace>.+)\.txt$"
)
RE_BASE = re.compile(
    r"^llc_baseline_(?P<size>\d+MB)_(?P<trace>.+)\.txt$"
)

SIZES = ["1MB", "2MB", "4MB", "8MB"]
REF_SIZE = "8MB"
# Benign → harsh. Plot curves in this z-order (harsh on top).
RATES = ["1e-5", "1e-6", "1e-7", "1e-8"]

# Color ramp: cool (benign) → warm (harsh). Matches the fig6 palette spirit.
RATE_COLOR = {
    "1e-5": "#4a78c4",   # cool blue   — benign
    "1e-6": "#5ea28c",   # muted teal
    "1e-7": "#d08a3c",   # amber
    "1e-8": "#c0504d",   # warm red    — harsh
}
RATE_MARKER = {
    "1e-5": "o",
    "1e-6": "s",
    "1e-7": "^",
    "1e-8": "D",
}
# Matches MTBCE conversion used in fig6.
MTBCE_LABEL = {
    "1e-5": "36 ms",
    "1e-6": "3.6 ms",
    "1e-7": "360 μs",
    "1e-8": "36 μs",
}


def load_sensitivity():
    out = {(s, r): {} for s in SIZES for r in RATES}
    if not os.path.isdir(SENS_DIR):
        raise SystemExit(f"Sensitivity dir not found: {SENS_DIR}")
    for fname in sorted(os.listdir(SENS_DIR)):
        m = RE_SENS.match(fname)
        if not m:
            continue
        size, rate = m.group("size"), m.group("rate")
        if (size, rate) not in out:
            continue
        metrics = extract_metrics(os.path.join(SENS_DIR, fname))
        wl = extract_workload(m.group("trace"))
        out[(size, rate)][wl] = metrics.ipc if metrics.ipc is not None else 0.0
    return out


def load_baseline_ref():
    """Per-workload error-free IPC at REF_SIZE (shared denominator)."""
    out = {}
    if not os.path.isdir(BASELINE_DIR):
        raise SystemExit(f"Baseline dir not found: {BASELINE_DIR}")
    for fname in sorted(os.listdir(BASELINE_DIR)):
        m = RE_BASE.match(fname)
        if not m or m.group("size") != REF_SIZE:
            continue
        metrics = extract_metrics(os.path.join(BASELINE_DIR, fname))
        wl = extract_workload(m.group("trace"))
        out[wl] = metrics.ipc if metrics.ipc is not None else 0.0
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
        "legend.fontsize": 7.2,
        "pdf.fonttype": 42,
        "ps.fonttype": 42,
    })


def main():
    setup_style()
    sens = load_sensitivity()
    ref = load_baseline_ref()
    if not ref:
        raise SystemExit(f"Missing reference data: llc_baseline_{REF_SIZE}_*")

    all_wls = set(ref.keys())
    for key in sens:
        all_wls |= set(sens[key].keys())
    all_wls = sorted(all_wls)

    # curves[rate] = list(len=SIZES) of GMEAN normalized IPC.
    rows = []
    curves = {r: [] for r in RATES}
    for r in RATES:
        for s in SIZES:
            vals = []
            for w in all_wls:
                denom = ref.get(w, 0.0)
                raw = sens[(s, r)].get(w, 0.0)
                n = (raw / denom) if denom and denom > 0 else 0.0
                vals.append(n)
                rows.append({
                    "llc_size": s, "error_rate": r, "workload": w,
                    "ipc_pin_on": raw,
                    "ref_ipc_baseline_8MB": denom,
                    "norm_ipc": n,
                })
            curves[r].append(gmean(vals))
    pd.DataFrame(rows).to_csv(OUTPUT_CSV, index=False)

    # ── Plot ──
    # X-axis runs left→right as "capacity being given up" (8 MB → 1 MB),
    # matching Fig 9 so the two are readable side-by-side.
    plot_sizes = list(reversed(SIZES))               # 8MB → 1MB
    x_vals = np.arange(len(plot_sizes), dtype=float)

    fig, ax = plt.subplots(figsize=(5.4, 3.0))

    # Reference line: error-free full-LLC performance anchors the top.
    ax.axhline(1.0, color="#606060", linewidth=0.8,
               linestyle=":", zorder=1.5)
    ax.text(x_vals[0] - 0.30, 1.008, "Error-free 8 MB baseline",
            fontsize=7.2, color="#3a3a3a", ha="left", va="bottom")

    # One curve per CE rate. Benign on bottom of draw stack so harsh
    # regimes (usually lower) are not occluded by the nicer curves.
    # Draw harsh → benign so benign (1e-5) ends on top visually; use a
    # zorder that still lets legend markers read cleanly.
    lines = []
    for i, r in enumerate(RATES):
        plot_curve = list(reversed(curves[r]))       # align with plot_sizes
        (ln,) = ax.plot(
            x_vals, plot_curve,
            color=RATE_COLOR[r], linewidth=2.0, linestyle="-",
            marker=RATE_MARKER[r], markersize=7.5,
            markerfacecolor=RATE_COLOR[r],
            markeredgecolor="black", markeredgewidth=0.5,
            zorder=5 - i * 0.1,
            label=f"CE Rate $10^{{{r.split('-')[1]}}}$/hr",
        )
        lines.append(ln)

    # Right-edge slope labels: % IPC lost going 8 MB → 1 MB under each rate.
    # Benign rates (1e-5..1e-7) have nearly-identical curves so we cluster
    # their labels on rows (top of cluster = benign) to avoid overlap; the
    # harsh 1e-8 sits alone at its own y-coordinate.
    x_right = x_vals[-1]
    drops = {}
    for r in RATES:
        v1 = list(reversed(curves[r]))[-1]            # IPC @ 1 MB
        v8 = list(reversed(curves[r]))[0]             # IPC @ 8 MB
        if v8 > 0:
            drops[r] = ((1.0 - v1 / v8) * 100, v1)

    # Anchor the stacked cluster at the benign trio's point; bottom curve
    # (1e-8) labels at its own position. Offsets in points.
    cluster_y = max(drops[r][1] for r in ("1e-5", "1e-6", "1e-7")
                    if r in drops)
    offset_order = ["1e-5", "1e-6", "1e-7"]           # top → bottom
    for i, r in enumerate(offset_order):
        if r not in drops:
            continue
        drop_pct, _ = drops[r]
        ax.annotate(
            f"−{drop_pct:.1f}%",
            xy=(x_right, cluster_y),
            xytext=(8, 8 - i * 10), textcoords="offset points",
            ha="left", va="center",
            fontsize=7.4, fontweight="bold",
            color=RATE_COLOR[r],
        )
    if "1e-8" in drops:
        drop_pct, y_anchor = drops["1e-8"]
        ax.annotate(
            f"−{drop_pct:.1f}%",
            xy=(x_right, y_anchor),
            xytext=(8, 0), textcoords="offset points",
            ha="left", va="center",
            fontsize=7.4, fontweight="bold",
            color=RATE_COLOR["1e-8"],
        )

    # X axis: evenly spaced, matching Fig 9.
    ax.set_xticks(x_vals)
    ax.set_xticklabels(plot_sizes)
    ax.set_xlabel("LLC capacity")
    ax.set_xlim(x_vals[0] - 0.35, x_vals[-1] + 0.95)  # extra room for labels

    # Y range: tight enough to see slope differences, loose enough for
    # harsh-regime curves that sit lower.
    all_y = [v for r in RATES for v in curves[r] if v > 0]
    y_lo = min(all_y) - 0.04 if all_y else 0.0
    ax.set_ylim(max(0.0, y_lo), 1.03)
    ax.set_ylabel("Normalized IPC  (ref = error-free 8 MB)")
    ax.yaxis.set_major_locator(MultipleLocator(0.05))
    ax.yaxis.set_major_formatter(FormatStrFormatter("%.2f"))
    ax.yaxis.grid(True, linestyle=":", linewidth=0.5, alpha=0.6)
    ax.set_axisbelow(True)

    leg = ax.legend(
        loc="lower left", handlelength=2.0, ncol=2,
        columnspacing=1.0, borderpad=0.4,
        frameon=True, fancybox=False, framealpha=1.0,
        title="LLC Pinning ON — CE rate",
        title_fontsize=7.2,
    )
    leg.get_frame().set_facecolor("white")
    leg.get_frame().set_edgecolor("black")
    leg.get_frame().set_linewidth(0.4)

    for spine in ax.spines.values():
        spine.set_visible(True)
        spine.set_linewidth(0.7)
        spine.set_color("black")

    plt.tight_layout(pad=0.3)
    plt.savefig(OUTPUT_PNG, dpi=400, bbox_inches="tight",
                facecolor="white", edgecolor="none")
    plt.savefig(OUTPUT_PDF, bbox_inches="tight",
                facecolor="white", edgecolor="none")
    plt.close()

    # Console summary.
    print(f"Workloads ({len(all_wls)}): {', '.join(all_wls)}")
    header = f"{'Size':>6}  " + "  ".join(f"{r:>8}" for r in RATES)
    print(header)
    for i, s in enumerate(SIZES):
        cells = "  ".join(f"{curves[r][i]:8.4f}" for r in RATES)
        print(f"{s:>6}  {cells}")
    for r in RATES:
        v1, v8 = curves[r][0], curves[r][-1]
        if v8 > 0:
            print(f"  {r}: 8MB→1MB drop = {(1 - v1 / v8) * 100:5.2f}%")
    print(f"CSV: {OUTPUT_CSV}")
    print(f"PNG: {OUTPUT_PNG}")
    print(f"PDF: {OUTPUT_PDF}")


if __name__ == "__main__":
    main()
