#!/usr/bin/env python3
"""
Fig 12: LLC Way Sensitivity — motivation for LLC Pinning (way-domain).

Replaces fig9 (capacity sensitivity). Same narrative, but X is the
number of LLC ways: pinning reserves ways for error data, so reviewers
expect the cost-of-shrinking story to be told in ways, not capacity.

X-axis reads left → right as "ways being given up": 16-way full at
left (reference), 8-way at right. Per-LLC GMEAN curves are normalized
to that LLC's own 16-way GMEAN. Per-point labels give exact IPC loss
at each reduction.

Source: results/normal_evaluation/7_no_error_way_sweep/
        noerr_{2MB,4MB}_w{8..16}_<trace>.txt  (error-free)
Output: fig12_no_error_way_sweep.{png,pdf,csv}
"""

import os
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib import rcParams
from matplotlib.ticker import FormatStrFormatter, MultipleLocator

from common_normal import load_no_error_way_sweep, gmean

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_CSV = os.path.join(SCRIPT_DIR, "fig12_no_error_way_sweep.csv")
OUTPUT_PNG = os.path.join(SCRIPT_DIR, "fig12_no_error_way_sweep.png")
OUTPUT_PDF = os.path.join(SCRIPT_DIR, "fig12_no_error_way_sweep.pdf")

REF_WAYS = 16  # per-LLC normalization reference
TARGET_LLC = "2MB"  # smallest LLC = worst-case (most way-sensitive) curve
CURVE_COLOR = "#5e7ac4"


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
    data = load_no_error_way_sweep()
    if not data:
        raise SystemExit("No data found")

    # Index: data_map[llc][ways][workload] = ipc
    data_map = {}
    workloads = set()
    for r in data:
        m = r["metrics"]
        if m.ipc is None:
            continue
        data_map.setdefault(r["llc_size"], {}).setdefault(r["ways"], {})[r["workload"]] = m.ipc
        workloads.add(r["workload"])

    workloads = sorted(workloads)
    if TARGET_LLC not in data_map:
        raise SystemExit(f"Target LLC {TARGET_LLC} data missing")
    ways_set = sorted(data_map[TARGET_LLC].keys())
    if REF_WAYS not in ways_set:
        raise SystemExit(f"Reference {REF_WAYS}-way data missing")

    # GMEAN curve, normalized to REF_WAYS GMEAN.
    rows = []
    per_way_gm = {}
    for k in ways_set:
        per_way_gm[k] = gmean([data_map[TARGET_LLC].get(k, {}).get(w) for w in workloads])
    ref = per_way_gm.get(REF_WAYS, 0.0)
    if not ref:
        raise SystemExit(f"Reference GMEAN at {REF_WAYS}-way is zero")
    curve = [per_way_gm[k] / ref for k in ways_set]
    for k, gm in per_way_gm.items():
        rows.append({
            "llc_size": TARGET_LLC, "ways": k,
            "gmean_ipc": gm,
            "ref_gmean_ipc_w16": ref,
            "norm_ipc": gm / ref,
        })

    pd.DataFrame(rows).to_csv(OUTPUT_CSV, index=False)

    # ── Plot ──
    plot_ways = list(reversed(ways_set))                # 16 → 8
    plot_curve = list(reversed(curve))
    x_vals = np.arange(len(plot_ways), dtype=float)

    fig, ax = plt.subplots(figsize=(3.74, 1.975))

    # Shaded "cost of shrinking ways" region.
    ax.fill_between(
        x_vals, plot_curve, [1.0] * len(x_vals),
        color=CURVE_COLOR, alpha=0.35, linewidth=0,
        zorder=1.5,
    )

    # Reference line at 1.0 anchors the full-way performance.
    ax.axhline(1.0, color="#606060", linewidth=0.8,
               linestyle=":", zorder=2)

    ax.plot(
        x_vals, plot_curve,
        color=CURVE_COLOR, linewidth=2.2, linestyle="-",
        marker="o", markersize=8,
        markerfacecolor=CURVE_COLOR, markeredgecolor="black",
        markeredgewidth=0.6,
        zorder=5,
        label=f"GMEAN IPC ({len(workloads)} SPEC CPU2017 workloads, LLC={TARGET_LLC})",
    )

    # Per-point loss labels: "−x%" vs REF_WAYS reference.
    for i, v in enumerate(plot_curve):
        if i == 0:
            continue
        loss_pct = (1.0 - v) * 100
        last = i == len(plot_curve) - 1
        ax.annotate(
            f"−{loss_pct:.1f}%",
            xy=(x_vals[i], v),
            xytext=(0, -7) if last else (0, -10),
            textcoords="offset points",
            ha="center", va="top",
            fontsize=6.5, fontweight="bold", color="#1a1a1a",
        )

    # X-axis: way counts, evenly spaced.
    ax.set_xticks(x_vals)
    ax.set_xticklabels([str(k) for k in plot_ways])
    ax.set_xlabel("LLC ways")
    ax.set_xlim(x_vals[0] - 0.35, x_vals[-1] + 0.35)

    # Tight Y range; emphasize gentle slope.
    ax.set_ylim(0.94, 1.01)
    ax.set_ylabel("Normalized IPC")
    ax.yaxis.set_major_locator(MultipleLocator(0.02))
    ax.yaxis.set_major_formatter(FormatStrFormatter("%.2f"))
    ax.yaxis.grid(True, linestyle=":", linewidth=0.5, alpha=0.6)
    ax.set_axisbelow(True)

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
    print(f"Workloads ({len(workloads)}): {', '.join(workloads)}")
    print(f"-- LLC={TARGET_LLC} (ref = {REF_WAYS}-way GMEAN) --")
    print(f"{'ways':>5}  {'norm IPC':>10}")
    for k, v in zip(ways_set, curve):
        print(f"{k:>5}  {v:10.4f}")
    print(f"CSV: {OUTPUT_CSV}")
    print(f"PNG: {OUTPUT_PNG}")
    print(f"PDF: {OUTPUT_PDF}")


if __name__ == "__main__":
    main()
