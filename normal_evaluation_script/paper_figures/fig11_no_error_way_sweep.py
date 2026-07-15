#!/usr/bin/env python3
"""
Fig 11: LLC Way Sensitivity — motivation for LLC Pinning (way-domain).

2MB-LLC GMEAN normalized to its own 16-way GMEAN. X-axis reads
left → right as "ways being given up": 16-way full at left (reference),
8-way at right.

Source: raw_data.xlsx, sheet "Way sweep in No error"
        (error-free; only llc_size = 2MB plotted)
Output: fig11_no_error_way_sweep.{png,pdf,csv}
"""

import os

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib import rcParams
from matplotlib.ticker import FormatStrFormatter, MultipleLocator

from common_normal import load_xlsx_sheet, gmean, suite_of

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

OUTPUT_CSV = os.path.join(SCRIPT_DIR, "fig11_no_error_way_sweep.csv")
OUTPUT_PNG = os.path.join(SCRIPT_DIR, "fig11_no_error_way_sweep.png")
OUTPUT_PDF = os.path.join(SCRIPT_DIR, "fig11_no_error_way_sweep.pdf")

REF_WAYS = 16
TARGET_LLC = "2MB"
CURVE_COLOR = "#0072B2"
SUITES = ["SPEC", "GAP"]
# matches the paper-wide blue + raspberry accent pair
SUITE_COLOR = {"SPEC": "#2E6FDB", "GAP": "#E5487E"}


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
    df = load_xlsx_sheet("Way sweep in No error")
    df = df[df["ipc"].notna() & (df["llc_size"] == TARGET_LLC)]

    # data_map[suite][ways][workload] = ipc
    data_map = {s: {} for s in SUITES}
    wls_by_suite = {s: set() for s in SUITES}
    for _, r in df.iterrows():
        suite = suite_of(r["workload"])
        data_map[suite].setdefault(int(r["llc_ways"]), {})[r["workload"]] = float(r["ipc"])
        wls_by_suite[suite].add(r["workload"])

    ways_set = sorted(
        set().union(*[set(data_map[s].keys()) for s in SUITES if data_map[s]])
    )
    if REF_WAYS not in ways_set:
        raise SystemExit(f"Reference {REF_WAYS}-way data missing")

    # Per-suite normalized curve (each normalized to its own 16-way GMEAN).
    rows = []
    curves = {}
    for suite in SUITES:
        wls = sorted(wls_by_suite[suite])
        if not wls:
            continue
        per_way_gm = {
            k: gmean([data_map[suite].get(k, {}).get(w) for w in wls])
            for k in ways_set
        }
        ref = per_way_gm.get(REF_WAYS, 0.0)
        if not ref:
            print(f"WARN: {suite} reference GMEAN at {REF_WAYS}-way is zero; skipping")
            continue
        curves[suite] = {k: per_way_gm[k] / ref for k in ways_set}
        for k in ways_set:
            rows.append({
                "suite": suite, "llc_size": TARGET_LLC, "ways": k,
                "n_workloads": len(wls),
                "gmean_ipc": per_way_gm[k],
                "ref_gmean_ipc_w16": ref,
                "norm_ipc": per_way_gm[k] / ref,
            })

    pd.DataFrame(rows).to_csv(OUTPUT_CSV, index=False)

    plot_ways = list(reversed(ways_set))
    x_vals = np.arange(len(plot_ways), dtype=float)
    plotted = [s for s in SUITES if s in curves]
    n = len(plotted)
    bar_w = 0.62 / max(n, 1)

    fig, ax = plt.subplots(figsize=(3.74, 1.975))

    for i, suite in enumerate(plotted):
        offset = (i - (n - 1) / 2) * bar_w
        ys = [curves[suite][k] for k in plot_ways]
        ax.bar(
            x_vals + offset, ys, width=bar_w,
            color=SUITE_COLOR[suite], edgecolor="black", linewidth=0.5,
            label=f"{suite} ({len(wls_by_suite[suite])})", zorder=3,
        )
        last_loss = (1.0 - ys[-1]) * 100
        ax.text(
            x_vals[-1] + offset, ys[-1] + 0.003, f"−{last_loss:.1f}%",
            ha="center", va="bottom",
            fontsize=5.0, fontweight="bold", color="black",
            zorder=4,
        )

    ax.axhline(1.0, color="black", linewidth=0.75,
               linestyle=":", zorder=2)

    ax.set_xticks(x_vals)
    ax.set_xticklabels([str(REF_WAYS - k) for k in plot_ways])
    ax.set_xlabel("Reserved LLC Ways")
    ax.set_xlim(x_vals[0] - 0.55, x_vals[-1] + 0.55)

    lo = min(curves[s][k] for s in plotted for k in ways_set)
    ax.set_ylim(min(0.94, lo - 0.01), 1.005)
    ax.set_ylabel("Normalized IPC")
    ax.yaxis.set_major_locator(MultipleLocator(0.02))
    ax.yaxis.set_major_formatter(FormatStrFormatter("%.2f"))
    ax.yaxis.grid(True, linestyle=":", linewidth=0.5, alpha=0.6)
    ax.set_axisbelow(True)

    if n > 1:
        ax.legend(loc="lower center", bbox_to_anchor=(0.5, 1.01),
                  ncol=len(plotted), frameon=True, fancybox=False,
                  framealpha=1.0, edgecolor="black", handlelength=1.2,
                  borderpad=0.3, columnspacing=1.2, handletextpad=0.5)

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

    for suite in plotted:
        print(f"-- {suite}  LLC={TARGET_LLC} ({len(wls_by_suite[suite])} wls, "
              f"ref = {REF_WAYS}-way GMEAN) --")
        print(f"{'ways':>5}  {'norm IPC':>10}")
        for k in ways_set:
            print(f"{k:>5}  {curves[suite][k]:10.4f}")
    print(f"CSV: {OUTPUT_CSV}")
    print(f"PNG: {OUTPUT_PNG}")
    print(f"PDF: {OUTPUT_PDF}")


if __name__ == "__main__":
    main()
