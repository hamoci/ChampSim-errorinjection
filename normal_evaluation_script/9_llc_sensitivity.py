#!/usr/bin/env python3
"""
Fig 9: LLC Capacity Sensitivity — motivation for LLC Pinning.

Narrative: LLC Pinning reserves ways for error data, so effective LLC
shrinks. This figure shows that the penalty for shrinking LLC is small
— even halving capacity costs only ~5–9% IPC — which is why sacrificing
a few ways to protect error pages is a good trade.

X-axis reads left → right as "capacity being given up" (8 MB full →
1 MB quartered). Per-point labels give the exact IPC loss at each
reduction, and the shaded region between the curve and the 8 MB
reference visualizes the (small) cost of shrinking.

Source: results/normal_evaluation/4_llc_size_baseline/
        llc_baseline_{1MB,2MB,4MB,8MB}_<trace>.txt  (error-free)
Output: fig9_llc_sensitivity.{png,pdf,csv}
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
BASELINE_DIR = os.path.join(BASE_DIR, "results", "normal_evaluation",
                            "4_llc_size_baseline")

OUTPUT_CSV = os.path.join(SCRIPT_DIR, "fig9_llc_sensitivity.csv")
OUTPUT_PNG = os.path.join(SCRIPT_DIR, "fig9_llc_sensitivity.png")
OUTPUT_PDF = os.path.join(SCRIPT_DIR, "fig9_llc_sensitivity.pdf")

RE_BASELINE = re.compile(
    r"^llc_baseline_(?P<size>\d+MB)_(?P<trace>.+)\.txt$"
)

SIZES = ["1MB", "2MB", "4MB", "8MB"]
REF_SIZE = "8MB"  # per-workload normalization reference
SIZE_MB = {"1MB": 1, "2MB": 2, "4MB": 4, "8MB": 8}

GMEAN_COLOR = "#111111"


def load_baseline():
    """Return data[size][workload] = ipc (None if parse failed)."""
    out = {s: {} for s in SIZES}
    if not os.path.isdir(BASELINE_DIR):
        raise SystemExit(f"Baseline dir not found: {BASELINE_DIR}")
    for fname in sorted(os.listdir(BASELINE_DIR)):
        m = RE_BASELINE.match(fname)
        if not m:
            continue
        size = m.group("size")
        if size not in out:
            continue
        metrics = extract_metrics(os.path.join(BASELINE_DIR, fname))
        wl = extract_workload(m.group("trace"))
        out[size][wl] = metrics.ipc if metrics.ipc is not None else 0.0
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
    data = load_baseline()

    ref = data[REF_SIZE]
    if not ref:
        raise SystemExit(f"Missing reference data: {REF_SIZE}")

    all_wls = set()
    for s in SIZES:
        all_wls |= set(data[s].keys())
    all_wls = sorted(all_wls)

    # Per-workload normalized curve + CSV rows.
    rows = []
    curves = {}  # wl -> list of normalized IPC across SIZES
    for w in all_wls:
        denom = ref.get(w, 0.0)
        vals = []
        for s in SIZES:
            raw = data[s].get(w, 0.0)
            n = (raw / denom) if denom and denom > 0 else 0.0
            vals.append(n)
            rows.append({
                "llc_size": s, "llc_mb": SIZE_MB[s],
                "workload": w,
                "ipc": raw,
                "ref_ipc_8MB": denom,
                "norm_ipc": n,
            })
        curves[w] = vals

    # GMEAN across workloads at each size. gmean filters zeros, so parse
    # failures are excluded from the aggregate curve.
    gmean_curve = []
    for i, s in enumerate(SIZES):
        gmean_curve.append(gmean([curves[w][i] for w in all_wls]))

    pd.DataFrame(rows).to_csv(OUTPUT_CSV, index=False)

    # Sensitivity = 1 - (IPC@1MB / IPC@8MB). Pick most / least sensitive
    # non-broken workloads to call out in the annotation.
    sens = {w: (1.0 - curves[w][0]) for w in all_wls
            if curves[w][0] > 0 and curves[w][-1] > 0}
    most_sens = max(sens, key=sens.get) if sens else None
    least_sens = min(sens, key=sens.get) if sens else None

    # ── Plot ──
    # X-axis runs left→right as "capacity being given up": 8 MB full at
    # left (reference), 1 MB quartered at right.
    plot_sizes = list(reversed(SIZES))                 # 8MB → 1MB
    plot_curve = list(reversed(gmean_curve))
    x_vals = np.arange(len(plot_sizes), dtype=float)   # evenly spaced

    fig, ax = plt.subplots(figsize=(5.4, 2.5))

    # Shaded "cost of shrinking" region between the reference (1.0) and
    # the GMEAN curve. Thin band → visual proof that the penalty is small.
    ax.fill_between(
        x_vals, plot_curve, [1.0] * len(x_vals),
        color="#5e7ac4", alpha=0.35, linewidth=0,
        zorder=1.5,
    )

    # Reference line: full-LLC performance anchors the top.
    ax.axhline(1.0, color="#606060", linewidth=0.8,
               linestyle=":", zorder=2)
    ax.text(x_vals[0] - 0.30, 1.008, "8 MB LLC",
            fontsize=7.5, color="#3a3a3a",
            ha="left", va="bottom")

    # GMEAN curve — the "it barely drops" line.
    (gmean_line,) = ax.plot(
        x_vals, plot_curve,
        color="#5e7ac4", linewidth=2.2, linestyle="-",
        marker="o", markersize=8,
        markerfacecolor="#5e7ac4", markeredgecolor="black",
        markeredgewidth=0.6,
        zorder=5,
        label="GMEAN IPC (10 SPEC CPU2017 workloads)",
    )

    # Per-point loss labels: "−x%" vs 8 MB reference.
    for i, (s, v) in enumerate(zip(plot_sizes, plot_curve)):
        if i == 0:
            continue  # skip baseline label
        loss_pct = (1.0 - v) * 100
        ax.annotate(
            f"−{loss_pct:.1f}%",
            xy=(x_vals[i], v),
            xytext=(0, -14),
            textcoords="offset points",
            ha="center", va="top",
            fontsize=8, fontweight="bold", color="#1a1a1a",
        )

    # X-axis: evenly spaced with capacity label + "capacity remaining"
    # percentage underneath to reinforce the sacrifice framing.
    ax.set_xticks(x_vals)
    ax.set_xticklabels(plot_sizes)
    ax.set_xlabel("LLC capacity (per-core)")
    ax.set_xlim(x_vals[0] - 0.35, x_vals[-1] + 0.35)

    # Tight Y range: emphasizes the gentle slope without visual distortion.
    y_lo = min(plot_curve) - 0.04
    ax.set_ylim(max(0.0, y_lo), 1.03)
    ax.set_ylabel("Normalized IPC")
    ax.yaxis.set_major_locator(MultipleLocator(0.05))
    ax.yaxis.set_major_formatter(FormatStrFormatter("%.2f"))
    ax.yaxis.grid(True, linestyle=":", linewidth=0.5, alpha=0.6)
    ax.set_axisbelow(True)

    leg = ax.legend(
        loc="lower left", handlelength=2.0,
        borderpad=0.4, frameon=True, fancybox=False, framealpha=1.0,
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
    print(f"{'Size':>6}  {'GMEAN norm IPC':>16}")
    for s, v in zip(SIZES, gmean_curve):
        print(f"{s:>6}  {v:16.4f}")
    if most_sens and least_sens:
        print(f"Most LLC-sensitive:  {most_sens}  "
              f"(1MB @ {curves[most_sens][0]:.3f} of 8MB)")
        print(f"Least LLC-sensitive: {least_sens}  "
              f"(1MB @ {curves[least_sens][0]:.3f} of 8MB)")
    print(f"CSV: {OUTPUT_CSV}")
    print(f"PNG: {OUTPUT_PNG}")
    print(f"PDF: {OUTPUT_PDF}")


if __name__ == "__main__":
    main()
