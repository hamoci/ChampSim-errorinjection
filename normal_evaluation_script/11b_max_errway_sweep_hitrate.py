#!/usr/bin/env python3
"""
Fig 11b: Variant of fig11 with a runtime-effectiveness Y-axis.

Same trade-off study as 11_max_errway_sweep.py, but the right Y-axis is
swapped from end-of-sim "Protected DRAM Errors (%)" (a snapshot of which
ever-observed error lines are currently resident in the error way) to a
runtime metric:

  Error-Line LLC Hit Rate (%)
    = stat_error_way_hit / (stat_error_way_hit + stat_error_way_miss)

Why this is more meaningful for readers:
  - Snapshot coverage punishes cold/dead error lines forever (denominator
    is the cumulative set of every error line ever observed). Even with
    perfect protection of the hot working set, the metric ceilings well
    below 100% because of trash in the denominator.
  - Hit-rate is dynamic: of the actual runtime accesses to error lines,
    what fraction landed in the protected error way? Ceilings near 100%
    when protection is effective, drops sharply when error lines get
    evicted before reuse.

Bars (left axis) and figure layout are otherwise identical to fig11 so
that the two figures can be placed side by side for comparison.

Source: pin_on way sweep        — results/normal_evaluation/6_llc_way_sweep/
        error-free baseline ref — results/normal_evaluation/4_llc_size_baseline/
Output: fig11b_max_errway_sweep_hitrate.{png,pdf,csv}
"""

import os
import re
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib import rcParams
from matplotlib.ticker import FormatStrFormatter, MultipleLocator

from common_normal import (
    extract_metrics, extract_workload, gmean,
    load_llc_way_sweep,
)

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
BASE_DIR = os.path.dirname(SCRIPT_DIR)
BASELINE_DIR = os.path.join(BASE_DIR, "results", "normal_evaluation",
                            "4_llc_size_baseline")

_FOCUS_TAG = os.environ.get("FOCUS_RATE_OVERRIDE", "")
_TAG_SUFFIX = f"_{_FOCUS_TAG}" if _FOCUS_TAG else ""
OUTPUT_CSV = os.path.join(SCRIPT_DIR,
                          f"fig11b_max_errway_sweep_hitrate{_TAG_SUFFIX}.csv")
OUTPUT_PNG = os.path.join(SCRIPT_DIR,
                          f"fig11b_max_errway_sweep_hitrate{_TAG_SUFFIX}.png")
OUTPUT_PDF = os.path.join(SCRIPT_DIR,
                          f"fig11b_max_errway_sweep_hitrate{_TAG_SUFFIX}.pdf")

RE_BASE = re.compile(
    r"^llc_baseline_(?P<size>\d+MB)_(?P<trace>.+)\.txt$"
)

SIZES = ["2MB", "4MB", "8MB"]
WAYS = [1, 2, 4, 8]
RATES = ["1e-5", "1e-6", "1e-7", "1e-8"]

FOCUS_RATE = os.environ.get("FOCUS_RATE_OVERRIDE", "1e-8")

WAY_COLOR = {
    1: "#f3be7a",
    2: "#f08d39",
    4: "#5e7ac4",
    8: "#3852b4",
}
WAY_MARKER_COLOR = {
    1: "#c7923d",
    2: "#bb6715",
    4: "#3d58a1",
    8: "#223891",
}
WAY_MARKER = {1: "o", 2: "s", 4: "^", 8: "D"}


def load_baseline_by_size():
    out = {s: {} for s in SIZES}
    if not os.path.isdir(BASELINE_DIR):
        raise SystemExit(f"Baseline dir not found: {BASELINE_DIR}")
    for fname in sorted(os.listdir(BASELINE_DIR)):
        m = RE_BASE.match(fname)
        if not m or m.group("size") not in out:
            continue
        metrics = extract_metrics(os.path.join(BASELINE_DIR, fname))
        wl = extract_workload(m.group("trace"))
        out[m.group("size")][wl] = metrics.ipc if metrics.ipc is not None else 0.0
    return out


def setup_style():
    rcParams.update({
        "font.family": "sans-serif",
        "font.sans-serif": ["Helvetica", "Arial", "DejaVu Sans"],
        "font.size": 10,
        "axes.linewidth": 0.8,
        "axes.labelsize": 10.5,
        "axes.titlesize": 10.5,
        "xtick.labelsize": 10,
        "ytick.labelsize": 10,
        "legend.fontsize": 9,
        "pdf.fonttype": 42,
        "ps.fonttype": 42,
    })


def main():
    setup_style()
    sweep_records = load_llc_way_sweep()
    if not sweep_records:
        raise SystemExit("No way-sweep records loaded.")
    baseline_ref = load_baseline_by_size()

    data = {}
    all_wls = set()
    for rec in sweep_records:
        key = (rec["llc_size"], rec["max_ways"], rec["error_rate"])
        data.setdefault(key, {})[rec["workload"]] = rec["metrics"]
        all_wls.add(rec["workload"])
    all_wls = sorted(all_wls)

    rows = []
    ipc_curves = {s: {r: [] for r in RATES} for s in SIZES}
    # Hit-rate curve: per (size, rate, way), arithmetic mean of
    # err_way_hit_rate (%) across workloads with valid data.
    hitrate_curves = {s: {r: [] for r in RATES} for s in SIZES}
    for size in SIZES:
        for rate in RATES:
            w1_cell = data.get((size, 1, rate), {})
            for way in WAYS:
                cell = data.get((size, way, rate), {})
                ipc_vals, hr_vals = [], []
                for w in all_wls:
                    m_ = cell.get(w)
                    m1_ = w1_cell.get(w)
                    raw_ipc = m_.ipc if (m_ and m_.ipc is not None) else 0.0
                    ref_ipc = m1_.ipc if (m1_ and m1_.ipc is not None) else 0.0
                    n_ipc = (raw_ipc / ref_ipc) if ref_ipc > 0 else 0.0
                    ipc_vals.append(n_ipc)

                    hr = (m_.err_way_hit_rate
                          if m_ and m_.err_way_hit_rate is not None else None)
                    if hr is not None:
                        hr_vals.append(hr)

                    rows.append({
                        "llc_size": size, "max_ways": way, "error_rate": rate,
                        "workload": w,
                        "ipc_pin_on": raw_ipc,
                        "ref_ipc_w1_same_size_rate": ref_ipc,
                        "norm_ipc": n_ipc,
                        "err_way_hit_rate_pct": hr,
                        "err_way_hits": (m_.err_way_hits if m_ else None),
                        "err_way_fills": (m_.err_way_fills if m_ else None),
                    })
                ipc_curves[size][rate].append(gmean(ipc_vals))
                hitrate_curves[size][rate].append(
                    float(np.mean(hr_vals)) if hr_vals else float("nan")
                )
    pd.DataFrame(rows).to_csv(OUTPUT_CSV, index=False)

    from matplotlib.lines import Line2D

    fig, ax_bar = plt.subplots(figsize=(7.6, 3.0))
    ax_line = ax_bar.twinx()

    x_vals = np.arange(len(SIZES), dtype=float)
    n_ways = len(WAYS)
    bar_w = 0.20
    offsets = {w: (i - (n_ways - 1) / 2) * bar_w
               for i, w in enumerate(WAYS)}

    for way_i, way in enumerate(WAYS):
        ys = [ipc_curves[s][FOCUS_RATE][way_i] for s in SIZES]
        ax_bar.bar(
            x_vals + offsets[way], ys, width=bar_w,
            color=WAY_COLOR[way], edgecolor="black", linewidth=0.6,
            label=f"w{way}",
            zorder=2,
        )

    ax_bar.axhline(1.0, color="#606060", linewidth=0.8,
                   linestyle=":", zorder=3)

    all_y_ipc = [v for s in SIZES for v in ipc_curves[s][FOCUS_RATE] if v > 0]
    y_lo = min(all_y_ipc) - 0.015
    ax_bar.set_ylim(max(0.0, y_lo), 1.01)
    ax_bar.yaxis.set_major_locator(MultipleLocator(0.01))
    ax_bar.yaxis.set_major_formatter(FormatStrFormatter("%.2f"))
    ax_bar.yaxis.grid(True, linestyle=":", linewidth=0.5, alpha=0.6)
    ax_bar.set_axisbelow(True)
    ax_bar.set_ylabel("Normalized IPC (bars)", fontsize=10.5)
    ax_bar.set_xticks(x_vals)
    ax_bar.set_xticklabels(SIZES)
    ax_bar.set_xlabel("LLC size", fontsize=10.5)
    ax_bar.set_xlim(x_vals[0] - 0.55, x_vals[-1] + 0.55)

    for size_i, size in enumerate(SIZES):
        xs_grp, ys_grp = [], []
        for way_i, way in enumerate(WAYS):
            y = hitrate_curves[size][FOCUS_RATE][way_i]
            if not (y == y):
                continue
            xs_grp.append(x_vals[size_i] + offsets[way])
            ys_grp.append(y)
        if len(xs_grp) >= 2:
            ax_line.plot(
                xs_grp, ys_grp,
                color="#6a6a6a", linewidth=0.8, linestyle=(0, (2, 2)),
                zorder=4,
            )

    for way_i, way in enumerate(WAYS):
        ys_raw = [hitrate_curves[s][FOCUS_RATE][way_i] for s in SIZES]
        xs = [x_vals[i] + offsets[way] for i, y in enumerate(ys_raw)
              if y == y]
        ys = [y for y in ys_raw if y == y]
        if not ys:
            continue
        ax_line.plot(
            xs, ys,
            linestyle="none",
            marker=WAY_MARKER[way], markersize=7,
            markerfacecolor=WAY_MARKER_COLOR[way],
            markeredgecolor="black", markeredgewidth=1.2,
            zorder=5,
        )

    ax_line.set_ylabel("Error-Line LLC Hit Rate (%) (markers)", fontsize=10.5)
    ax_line.set_ylim(0, 102)
    ax_line.yaxis.set_major_formatter(FormatStrFormatter("%.0f"))
    ax_line.grid(False)

    for spine in ax_bar.spines.values():
        spine.set_linewidth(0.8); spine.set_color("black")
    for spine in ax_line.spines.values():
        spine.set_linewidth(0.8); spine.set_color("black")

    from matplotlib.patches import Patch
    legend_handles = [
        Patch(facecolor=WAY_COLOR[w], edgecolor="black", linewidth=0.6,
              label=f"Max Error Ways = {w}")
        for w in WAYS
    ]
    leg = fig.legend(
        handles=legend_handles,
        loc="upper center", bbox_to_anchor=(0.5, 1.00),
        ncol=len(WAYS), handlelength=1.6, handleheight=1.0,
        columnspacing=1.8, borderpad=0.5, handletextpad=0.6,
        frameon=True, fancybox=False, framealpha=1.0,
    )
    leg.get_frame().set_facecolor("white")
    leg.get_frame().set_edgecolor("black")
    leg.get_frame().set_linewidth(0.5)

    plt.tight_layout(rect=(0, 0, 1, 0.92))
    plt.savefig(OUTPUT_PNG, dpi=400, bbox_inches="tight",
                facecolor="white", edgecolor="none")
    plt.savefig(OUTPUT_PDF, bbox_inches="tight",
                facecolor="white", edgecolor="none")
    plt.close()

    print(f"Workloads ({len(all_wls)}): {', '.join(all_wls)}")
    for size in SIZES:
        print(f"\n── {size} LLC ──")
        print(f"{'rate':>6}  {'IPC vs w1 (w1..w8)':<28}  "
              f"{'Err-Line LLC Hit % (w1..w8)':<36}")
        for rate in RATES:
            ipc_vals = ipc_curves[size][rate]
            hr_vals = hitrate_curves[size][rate]
            ipc_cells = " ".join(f"{v:5.3f}" for v in ipc_vals)
            hr_cells = " ".join(
                f"{v:6.2f}" if (v == v) else "   n/a"
                for v in hr_vals
            )
            print(f"{rate:>6}  {ipc_cells}  {hr_cells}")
    print(f"\nCSV: {OUTPUT_CSV}")
    print(f"PNG: {OUTPUT_PNG}")
    print(f"PDF: {OUTPUT_PDF}")


if __name__ == "__main__":
    main()
