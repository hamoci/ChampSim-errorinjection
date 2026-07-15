#!/usr/bin/env python3
"""
Fig 11: How many LLC ways should we reserve for pinning?

The trade-off is one sentence: more reserved ways cost a little IPC, but
sharply raise the share of error lines actually under protection.
This figure puts cost and reliability on the same panel, focused on the
harsh CE regime (1e-8) where the trade is real.

  Top    — Normalized IPC vs max_ways  (ref: error-free baseline, same LLC size)
  Bottom — Protected Error Lines (%) = pinned_count / total_known_errors
           Fraction of DRAM-error addresses that are still resident in the
           LLC error way (i.e. under protection)
           at end of simulation. Direct reliability metric — the higher,
           the more error addresses we are actively shielding.

Benign rates show no meaningful trade (lines are flat), so we don't plot
them. Console summary prints only the rates present in the current sweep.

Source: pin_on way sweep        — results/normal_evaluation/6_llc_way_sweep/
                                   sweep_{2,4,8}MB_w{1,2,4,8}_{1e-7..1e-8}_<trace>.txt
        error-free baseline ref — results/normal_evaluation/4_llc_size_baseline/
                                   llc_baseline_{2,4,8}MB_<trace>.txt
Output: fig11_max_errway_sweep.{png,pdf,csv}
        fig11_max_errway_sweep_workloads_{2,4,8}MB_1e-8.{png,pdf,csv}

Workload coverage: SPEC CPU2017 workloads found in the sweep directory.
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
OUTPUT_CSV = os.path.join(SCRIPT_DIR, f"fig11_max_errway_sweep{_TAG_SUFFIX}.csv")
OUTPUT_PNG = os.path.join(SCRIPT_DIR, f"fig11_max_errway_sweep{_TAG_SUFFIX}.png")
OUTPUT_PDF = os.path.join(SCRIPT_DIR, f"fig11_max_errway_sweep{_TAG_SUFFIX}.pdf")

RE_BASE = re.compile(
    r"^llc_baseline_(?P<size>\d+MB)_(?P<trace>.+)\.txt$"
)

SIZES = ["2MB", "4MB", "8MB"]
WAYS = [1, 2, 4, 8]
RATES = ["1e-7", "1e-8"]

# Focus rate — the one with a real trade-off.
FOCUS_RATE = os.environ.get("FOCUS_RATE_OVERRIDE", "1e-8")

# Project palette. Warm amber = low-coverage (risky) side,
# cool blue = high-coverage (safe) side; the eye reads "heat → cool"
# as we reserve more error ways and protection broadens.
WAY_COLOR = {
    1: "#f3be7a",   # light amber   — w1 (few ways reserved, low coverage)
    2: "#f08d39",   # dark amber
    4: "#5e7ac4",   # lighter blue
    8: "#3852b4",   # dark blue     — w8 (most reserved, highest coverage)
}
# Slightly darker shade per color, used for marker fill so markers pop
# against their same-color bar. ~25% darker than the bar.
WAY_MARKER_COLOR = {
    1: "#c7923d",
    2: "#bb6715",
    4: "#3d58a1",
    8: "#223891",
}
WAY_MARKER = {1: "o", 2: "s", 4: "^", 8: "D"}


def workload_output_paths(size, rate):
    base = f"fig11_max_errway_sweep_workloads_{size}_{rate}"
    return (
        os.path.join(SCRIPT_DIR, f"{base}.csv"),
        os.path.join(SCRIPT_DIR, f"{base}.png"),
        os.path.join(SCRIPT_DIR, f"{base}.pdf"),
    )


def short_workload_label(workload):
    label = workload.split(".", 1)[1] if "." in workload else workload
    return label[:-2] if label.endswith("_s") else label


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


def plot_workload_breakdown(data, baseline_ref, workloads, size, rate):
    """One compact workload-level view for a single LLC size and CE rate."""
    labels = [short_workload_label(w) for w in workloads] + ["GMEAN"]
    rows = []

    norm_by_way = {w: [] for w in WAYS}
    cov_by_way = {w: [] for w in WAYS}
    for wl in workloads:
        ref_ipc = baseline_ref.get(size, {}).get(wl, 0.0)
        for way in WAYS:
            m_ = data.get((size, way, rate), {}).get(wl)
            raw_ipc = m_.ipc if (m_ and m_.ipc is not None) else 0.0
            norm_ipc = (raw_ipc / ref_ipc) if ref_ipc > 0 else 0.0
            cov = m_.pinned_pct if (m_ and m_.pinned_pct is not None) else float("nan")
            norm_by_way[way].append(norm_ipc)
            cov_by_way[way].append(cov)
            rows.append({
                "llc_size": size,
                "error_rate": rate,
                "workload": wl,
                "max_ways": way,
                "ipc_pin_on": raw_ipc,
                "ref_ipc_no_error_same_workload_size": ref_ipc,
                "norm_ipc": norm_ipc,
                "protected_error_lines_pct": cov,
            })

    for way in WAYS:
        ipc_gm = gmean(norm_by_way[way])
        cov_vals = [v for v in cov_by_way[way] if v == v]
        cov_mean = float(np.mean(cov_vals)) if cov_vals else float("nan")
        norm_by_way[way].append(ipc_gm)
        cov_by_way[way].append(cov_mean)
        rows.append({
            "llc_size": size,
            "error_rate": rate,
            "workload": "GMEAN",
            "max_ways": way,
            "ipc_pin_on": None,
            "ref_ipc_no_error_same_workload_size": None,
            "norm_ipc": ipc_gm,
            "protected_error_lines_pct": cov_mean,
        })

    out_csv, out_png, out_pdf = workload_output_paths(size, rate)
    pd.DataFrame(rows).to_csv(out_csv, index=False)

    fig, ax_bar = plt.subplots(figsize=(7.6, 2.0))
    ax_line = ax_bar.twinx()

    x_vals = np.arange(len(labels), dtype=float)
    bar_w = 0.17
    offsets = {w: (i - (len(WAYS) - 1) / 2) * bar_w
               for i, w in enumerate(WAYS)}

    for way in WAYS:
        xs = x_vals + offsets[way]
        ax_bar.bar(
            xs, norm_by_way[way], width=bar_w,
            color=WAY_COLOR[way], edgecolor="black", linewidth=0.45,
            zorder=2,
        )
        marker_ys = cov_by_way[way]
        valid = [(x, y) for x, y in zip(xs, marker_ys) if y == y]
        if valid:
            ax_line.plot(
                [x for x, _ in valid], [y for _, y in valid],
                linestyle="none", marker=WAY_MARKER[way], markersize=4.6,
                markerfacecolor=WAY_MARKER_COLOR[way],
                markeredgecolor="black", markeredgewidth=0.75,
                zorder=5,
            )

    all_ipc = [v for way in WAYS for v in norm_by_way[way] if v > 0]
    y_lo = max(0.0, min(all_ipc) - 0.02) if all_ipc else 0.0
    ax_bar.set_ylim(y_lo, 1.01)
    ax_bar.yaxis.set_major_locator(MultipleLocator(0.05))
    ax_bar.yaxis.set_major_formatter(FormatStrFormatter("%.2f"))
    ax_bar.yaxis.grid(True, linestyle=":", linewidth=0.45, alpha=0.45)
    ax_bar.set_axisbelow(True)
    ax_bar.set_ylabel("Normalized IPC", fontsize=8.8, labelpad=1.5)
    ax_bar.set_xticks(x_vals)
    ax_bar.set_xticklabels(labels, rotation=26, ha="right", rotation_mode="anchor")
    ax_bar.tick_params(axis="both", labelsize=8.2, pad=1.5, width=0.75)
    ax_bar.set_xlim(x_vals[0] - 0.55, x_vals[-1] + 0.55)

    # Separate the summary from individual workloads without spending space on
    # another panel.
    ax_bar.axvline(len(workloads) - 0.5, color="#808080", linewidth=0.55,
                   linestyle=":", zorder=1)

    ax_line.set_ylim(0, 102)
    ax_line.yaxis.set_major_formatter(FormatStrFormatter("%.0f"))
    ax_line.set_ylabel("Protected Lines (%)", fontsize=8.8, labelpad=1.5)
    ax_line.tick_params(axis="y", labelsize=8.2, pad=1.5, width=0.75)
    ax_line.grid(False)

    for ax in (ax_bar, ax_line):
        for spine in ax.spines.values():
            spine.set_linewidth(0.75)
            spine.set_color("black")

    from matplotlib.patches import Patch
    legend_handles = [
        Patch(facecolor=WAY_COLOR[w], edgecolor="black", linewidth=0.45,
              label=f"{w}-way")
        for w in WAYS
    ]
    leg = fig.legend(
        handles=legend_handles, loc="upper center", bbox_to_anchor=(0.5, 0.99),
        ncol=len(WAYS), handlelength=1.15, columnspacing=1.25,
        borderpad=0.32, handletextpad=0.45, frameon=True, fancybox=False,
        framealpha=1.0, fontsize=8.0,
    )
    leg.get_frame().set_facecolor("white")
    leg.get_frame().set_edgecolor("black")
    leg.get_frame().set_linewidth(0.45)

    plt.tight_layout(rect=(0, 0, 1, 0.88))
    plt.savefig(out_png, dpi=400, bbox_inches="tight",
                facecolor="white", edgecolor="none")
    plt.savefig(out_pdf, bbox_inches="tight",
                facecolor="white", edgecolor="none")
    plt.close()

    return out_csv, out_png, out_pdf


def main():
    setup_style()
    sweep_records = load_llc_way_sweep()
    if not sweep_records:
        raise SystemExit("No way-sweep records loaded.")
    baseline_ref = load_baseline_by_size()

    # Pivot: data[(size, way, rate)][workload] = Metrics
    data = {}
    all_wls = set()
    for rec in sweep_records:
        key = (rec["llc_size"], rec["max_ways"], rec["error_rate"])
        data.setdefault(key, {})[rec["workload"]] = rec["metrics"]
        all_wls.add(rec["workload"])
    all_wls = sorted(all_wls)

    # Aggregated — per (size, rate) we compute:
    #   ipc_curves[size][rate]      : GMEAN norm IPC across workloads,
    #                                 per-workload ref = no-error baseline IPC
    #                                 at the same LLC size.
    #   coverage_curves[size][rate] : Arithmetic mean of pinned_pct (%) across
    #                                 workloads with valid coverage data.
    #                                 nan if no valid cells.
    rows = []
    ipc_curves = {s: {r: [] for r in RATES} for s in SIZES}
    coverage_curves = {s: {r: [] for r in RATES} for s in SIZES}
    for size in SIZES:
        for rate in RATES:
            for way in WAYS:
                cell = data.get((size, way, rate), {})
                ipc_vals, cov_vals = [], []
                for w in all_wls:
                    m_ = cell.get(w)
                    raw_ipc = m_.ipc if (m_ and m_.ipc is not None) else 0.0
                    ref_ipc = baseline_ref.get(size, {}).get(w, 0.0)
                    n_ipc = (raw_ipc / ref_ipc) if ref_ipc > 0 else 0.0
                    ipc_vals.append(n_ipc)

                    cov = (m_.pinned_pct
                           if m_ and m_.pinned_pct is not None else None)
                    if cov is not None:
                        cov_vals.append(cov)

                    rows.append({
                        "llc_size": size, "max_ways": way, "error_rate": rate,
                        "workload": w,
                        "ipc_pin_on": raw_ipc,
                        "ref_ipc_no_error_same_size": ref_ipc,
                        "norm_ipc": n_ipc,
                        "pinning_coverage_pct": cov,
                    })
                ipc_curves[size][rate].append(gmean(ipc_vals))
                # Arithmetic mean of percentages — gmean would distort high
                # values (e.g. 99% vs 100%) and isn't standard for rates.
                coverage_curves[size][rate].append(
                    float(np.mean(cov_vals)) if cov_vals else float("nan")
                )
    pd.DataFrame(rows).to_csv(OUTPUT_CSV, index=False)

    # ── Plot ── single panel, dual y-axis:
    #   X-axis: LLC size (2MB / 4MB / 8MB)
    #   Bars (left axis)  — IPC, 4 bars per group (one per max_ways)
    #   Markers (right axis) — Protected Error Lines (%), one marker per max_ways
    #                          per LLC size group
    from matplotlib.lines import Line2D

    fig, ax_bar = plt.subplots(figsize=(7.6, 3.0))
    ax_line = ax_bar.twinx()

    x_vals = np.arange(len(SIZES), dtype=float)   # one tick per LLC size
    n_ways = len(WAYS)
    bar_w = 0.20
    offsets = {w: (i - (n_ways - 1) / 2) * bar_w
               for i, w in enumerate(WAYS)}

    # ── Bars: IPC (left axis) ──
    # For each max_ways value, draw one bar at each LLC-size group.
    for way_i, way in enumerate(WAYS):
        ys = [ipc_curves[s][FOCUS_RATE][way_i] for s in SIZES]
        ax_bar.bar(
            x_vals + offsets[way], ys, width=bar_w,
            color=WAY_COLOR[way], edgecolor="black", linewidth=0.6,
            label=f"w{way}",
            zorder=2,
        )

    # No-error reference line (= 1.0 by construction).
    ax_bar.axhline(1.0, color="#606060", linewidth=0.8,
                   linestyle=":", zorder=3)

    # Small headroom above the no-error reference line.
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

    # ── Markers on right axis, connected within each LLC-size group ──
    # For each LLC size we draw one thin dashed guide through its four
    # markers (w1→w2→w4→w8) so the reader's eye follows the climb inside
    # the group. Markers keep the per-way color/shape.
    for size_i, size in enumerate(SIZES):
        xs_grp, ys_grp = [], []
        for way_i, way in enumerate(WAYS):
            y = coverage_curves[size][FOCUS_RATE][way_i]
            if not (y == y):  # nan check
                continue
            xs_grp.append(x_vals[size_i] + offsets[way])
            ys_grp.append(y)
        if len(xs_grp) >= 2:
            ax_line.plot(
                xs_grp, ys_grp,
                color="#6a6a6a", linewidth=0.8, linestyle=(0, (2, 2)),
                zorder=4,
            )

    # Overlay the per-way markers on top of the guide line.
    for way_i, way in enumerate(WAYS):
        ys_raw = [coverage_curves[s][FOCUS_RATE][way_i] for s in SIZES]
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

    ax_line.set_ylabel("Protected Error Lines (%) (markers)", fontsize=10.5)
    # Coverage spans a wide range (low w1 vs near-100% w8). Show the full
    # 0–100 range so the gap reads as the headline of the figure. Falls
    # back to 0–100 if no valid data.
    ax_line.set_ylim(0, 102)
    ax_line.yaxis.set_major_formatter(FormatStrFormatter("%.0f"))
    ax_line.grid(False)

    for spine in ax_bar.spines.values():
        spine.set_linewidth(0.8); spine.set_color("black")
    for spine in ax_line.spines.values():
        spine.set_linewidth(0.8); spine.set_color("black")

    # Single legend — color swatch only (markers are already on the chart).
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

    # Leave room at the top for the legend.
    plt.tight_layout(rect=(0, 0, 1, 0.92))
    plt.savefig(OUTPUT_PNG, dpi=400, bbox_inches="tight",
                facecolor="white", edgecolor="none")
    plt.savefig(OUTPUT_PDF, bbox_inches="tight",
                facecolor="white", edgecolor="none")
    plt.close()

    workload_outputs = []
    if FOCUS_RATE in RATES:
        for size in SIZES:
            workload_outputs.append(
                plot_workload_breakdown(data, baseline_ref, all_wls, size, FOCUS_RATE)
            )

    # Console summary — only rates present in the current sweep are listed.
    print(f"Workloads ({len(all_wls)}): {', '.join(all_wls)}")
    for size in SIZES:
        print(f"\n── {size} LLC ──")
        print(f"{'rate':>6}  {'IPC vs no-error (w1..w8)':<32}  "
              f"{'Protected % (w1..w8)':<36}")
        for rate in RATES:
            ipc_vals = ipc_curves[size][rate]
            cov_vals = coverage_curves[size][rate]
            ipc_cells = " ".join(f"{v:5.3f}" for v in ipc_vals)
            cov_cells = " ".join(
                f"{v:6.2f}" if (v == v) else "   n/a"
                for v in cov_vals
            )
            print(f"{rate:>6}  {ipc_cells}  {cov_cells}")
    print(f"\nCSV: {OUTPUT_CSV}")
    print(f"PNG: {OUTPUT_PNG}")
    print(f"PDF: {OUTPUT_PDF}")
    for out_csv, out_png, out_pdf in workload_outputs:
        print(f"Workload CSV: {out_csv}")
        print(f"Workload PNG: {out_png}")
        print(f"Workload PDF: {out_pdf}")


if __name__ == "__main__":
    main()
