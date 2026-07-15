#!/usr/bin/env python3
"""
Fig 12: IPC and protected-line coverage by retirement threshold, comparing
LLC pinning ON vs OFF.

Source: raw_data.xlsx
  - sheet "Threshold sweep"       (pin_mode = on or off)
  - sheet "Way sweep in No error" (llc_size=2MB, llc_ways=16) — baseline

Coverage metric (Protected Lines %):
  · pin-on : (pinned + retired) / (live_known + retired) * 100
      = protected_lines / total_error_lines * 100  (pre-computed)
  · pin-off: retired / (retired + live) * 100
      = protected_lines / total_error_lines * 100  (pre-computed)
  Both formulas count retired-page error lines as protected (page
  offlining covers them) — matches fig9's definition.

Normalized IPC:
    per-workload IPC / 2MB no-error baseline IPC
"""

import math
import os

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib import rcParams
from matplotlib.ticker import FuncFormatter

from common_normal import load_xlsx_sheet, gmean, suite_of

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

OUTPUT_SUMMARY_CSV = os.path.join(SCRIPT_DIR, "fig12_protected_lines.csv")
OUTPUT_WORKLOAD_CSV = os.path.join(SCRIPT_DIR, "fig12_protected_lines_workloads.csv")
OUTPUT_PNG = os.path.join(SCRIPT_DIR, "fig12_protected_lines.png")
OUTPUT_PDF = os.path.join(SCRIPT_DIR, "fig12_protected_lines.pdf")

THRESHOLDS = [2, 4, 8, 16, 32, 256]
RATES = ["1e-5", "1e-6", "1e-7", "1e-8"]
PLOT_RATES = ["1e-8"]
PIN_MODES = ["on", "off"]
SUITES = ["SPEC", "GAP"]
REF_SIZE = "2MB"
BASELINE_WAYS = 16

COLOR_HARSH = "#2E6FDB"
COLOR_PIN_OFF = "#E5487E"
COLOR_MARKER_ON = "#1F4FA0"
COLOR_MARKER_OFF = "#B52E5E"
EDGE = "black"
RATE_STYLE = {
    "1e-8": {
        "bar_color_on": COLOR_HARSH,
        "bar_color_off": COLOR_PIN_OFF,
        "marker_color_on": COLOR_MARKER_ON,
        "marker_color_off": COLOR_MARKER_OFF,
        "marker_on": "o",
        "marker_off": "s",
        "label": r"CE Rate $10^{8}$/hr",
    },
}


def setup_style():
    rcParams.update({
        "font.family": "sans-serif",
        "font.sans-serif": ["Helvetica", "Arial", "DejaVu Sans"],
        "font.size": 7,
        "axes.linewidth": 0.7,
        "axes.labelsize": 7.5,
        "axes.titlesize": 7.5,
        "xtick.labelsize": 7,
        "ytick.labelsize": 7,
        "legend.fontsize": 7,
        "pdf.fonttype": 42,
        "ps.fonttype": 42,
    })


def load_data():
    df = load_xlsx_sheet("Threshold sweep").copy()
    df = df[df["error_rate"].isin(RATES)
            & df["retirement_threshold"].isin(THRESHOLDS)]

    df["completed"] = df["ipc"].notna()
    df["protected_line_ratio"] = np.where(
        df["protected_lines_pct"].notna(),
        df["protected_lines_pct"] / 100.0,
        np.nan,
    )
    df["included_in_protected_mean"] = df["protected_line_ratio"].notna()
    df = df.rename(columns={
        "error_rate": "rate",
        "pin_mode": "pin_mode",
        "retirement_threshold": "threshold",
    })
    return df.reset_index(drop=True)


def load_baseline_ipc():
    df = load_xlsx_sheet("Way sweep in No error")
    df = df[(df["llc_size"] == REF_SIZE) & (df["llc_ways"] == BASELINE_WAYS)]
    return {r["workload"]: (float(r["ipc"]) if pd.notna(r["ipc"]) else 0.0)
            for _, r in df.iterrows()}


def main():
    setup_style()
    df = load_data()
    if df.empty:
        raise SystemExit("No retire threshold results loaded.")
    baseline = load_baseline_ipc()

    df["suite"] = df["workload"].map(suite_of)
    df["baseline_ipc_2MB_no_error"] = df["workload"].map(baseline).fillna(0.0)
    # Normalized IPC: completed -> ipc/baseline; incomplete (panic) -> 0.0,
    # still counted in the geomean (so the bar collapses); completed-without-
    # baseline -> NaN (dropped, can't normalize).
    with np.errstate(divide="ignore", invalid="ignore"):
        ratio = df["ipc"] / df["baseline_ipc_2MB_no_error"]
    df["norm_ipc"] = np.where(
        df["completed"] & (df["baseline_ipc_2MB_no_error"] > 0.0),
        ratio,
        np.where(~df["completed"].astype(bool), 0.0, np.nan),
    )
    df["protected_line_pct"] = df["protected_line_ratio"] * 100.0

    summary_rows = []
    # keyed by (suite, rate, pin)
    keys = [(s, r, p) for s in SUITES for r in RATES for p in PIN_MODES]
    ipc_means = {k: [] for k in keys}
    protected_means = {k: [] for k in keys}

    for suite in SUITES:
        for rate in RATES:
            for pin in PIN_MODES:
                for threshold in THRESHOLDS:
                    sub = df[
                        (df["suite"] == suite)
                        & (df["rate"] == rate)
                        & (df["threshold"] == threshold)
                        & (df["pin_mode"] == pin)
                    ]
                    protected_vals = sub[
                        sub["included_in_protected_mean"]
                    ]["protected_line_ratio"].tolist()
                    # keep 0.0 (panic) and real ratios; drop NaN (no baseline)
                    ipc_vals = sub["norm_ipc"].dropna().tolist()

                    protected_avg = (float(np.mean(protected_vals))
                                     if protected_vals else math.nan)
                    ipc_avg = (gmean(ipc_vals, include_zeros=True)
                               if ipc_vals else math.nan)

                    protected_means[(suite, rate, pin)].append(protected_avg)
                    ipc_means[(suite, rate, pin)].append(ipc_avg)
                    n_panic = int((~sub["completed"].astype(bool)).sum())
                    summary_rows.append({
                        "suite": suite,
                        "rate": rate,
                        "pin_mode": pin,
                        "threshold": threshold,
                        "n_workloads_ipc": len(ipc_vals),
                        "n_incomplete_panic": n_panic,
                        "gmean_norm_ipc": ipc_avg,
                        "n_workloads_protected": len(protected_vals),
                        "mean_protected_line_ratio": protected_avg,
                        "mean_protected_line_pct":
                            protected_avg * 100.0
                            if not math.isnan(protected_avg) else math.nan,
                    })

    pd.DataFrame(summary_rows).to_csv(OUTPUT_SUMMARY_CSV, index=False)
    df.to_csv(OUTPUT_WORKLOAD_CSV, index=False)

    rate = PLOT_RATES[0]
    style = RATE_STYLE[rate]
    fig, axes = plt.subplots(1, 2, figsize=(7.0, 2.05), sharey=True)
    x_vals = np.arange(len(THRESHOLDS), dtype=float)
    bar_w = 0.36
    pin_offsets = {
        pin: (idx - (len(PIN_MODES) - 1) / 2) * bar_w
        for idx, pin in enumerate(PIN_MODES)
    }

    marker_axes = []
    for ax_bar, suite in zip(axes, SUITES):
        ax_marker = ax_bar.twinx()
        marker_axes.append(ax_marker)
        for pin in PIN_MODES:
            ax_bar.bar(
                x_vals + pin_offsets[pin], ipc_means[(suite, rate, pin)],
                width=bar_w, color=style[f"bar_color_{pin}"],
                edgecolor=EDGE, linewidth=0.55, alpha=0.9, zorder=3,
            )
        for pin in PIN_MODES:
            ys = protected_means[(suite, rate, pin)]
            valid = [(x, y) for x, y in zip(x_vals, ys)
                     if not (isinstance(y, float) and math.isnan(y))]
            if valid:
                vx, vy = zip(*valid)
                ax_marker.plot(
                    vx, vy, color=style[f"marker_color_{pin}"],
                    linewidth=0.9, linestyle=(0, (2, 1.5)),
                    marker=style[f"marker_{pin}"], markersize=5.0,
                    markerfacecolor=style[f"marker_color_{pin}"],
                    markeredgecolor=style[f"marker_color_{pin}"],
                    markeredgewidth=0.0, alpha=0.95, zorder=5,
                )
        ax_bar.set_xticks(x_vals)
        ax_bar.set_xticklabels([str(t) for t in THRESHOLDS])
        ax_bar.set_xlim(x_vals[0] - 0.58, x_vals[-1] + 0.58)
        ax_bar.set_xlabel("Page Offline Threshold", labelpad=1.5)
        ax_bar.set_ylim(0.0, 1.05)
        ax_bar.yaxis.grid(True, linestyle=":", linewidth=0.5, alpha=0.6)
        ax_bar.set_axisbelow(True)
        ax_bar.set_title(suite, fontsize=8, pad=2)
        ax_marker.set_ylim(0.0, 1.05)
        ax_marker.yaxis.set_major_formatter(
            FuncFormatter(lambda v, pos: f"{v * 100:.0f}"))
        ax_marker.grid(False)
        for ax in (ax_bar, ax_marker):
            for spine in ax.spines.values():
                spine.set_visible(True)
                spine.set_linewidth(0.7)
                spine.set_color("black")

    axes[0].set_ylabel("Normalized IPC", labelpad=3)
    # Only show the protected-lines axis label on the rightmost marker axis.
    marker_axes[0].set_yticklabels([])
    marker_axes[1].set_ylabel("Protected Lines (%)", labelpad=3)

    from matplotlib.patches import Patch
    from matplotlib.lines import Line2D
    from matplotlib.legend_handler import HandlerTuple

    bar_on = Patch(facecolor=COLOR_HARSH, edgecolor=EDGE, linewidth=0.55)
    bar_off = Patch(facecolor=COLOR_PIN_OFF, edgecolor=EDGE, linewidth=0.55)
    mk_on = Line2D([0], [0], marker="o", linestyle=(0, (2, 1.5)),
                   linewidth=0.9, color=COLOR_MARKER_ON,
                   markerfacecolor=COLOR_MARKER_ON,
                   markeredgecolor=COLOR_MARKER_ON, markersize=5.5)
    mk_off = Line2D([0], [0], marker="s", linestyle=(0, (2, 1.5)),
                    linewidth=0.9, color=COLOR_MARKER_OFF,
                    markerfacecolor=COLOR_MARKER_OFF,
                    markeredgecolor=COLOR_MARKER_OFF, markersize=5.5)

    leg = fig.legend(
        [(bar_on, mk_on), (bar_off, mk_off)],
        ["w/ LLC Pinning", "w/o LLC Pinning"], ncol=2,
        handler_map={tuple: HandlerTuple(ndivide=None, pad=0.6)},
        loc="upper center", bbox_to_anchor=(0.5, 1.02),
        fontsize=7.0, handlelength=2.8, handletextpad=0.5,
        columnspacing=1.4, borderpad=0.35, borderaxespad=0.0,
        frameon=True, fancybox=False, framealpha=1.0,
        facecolor="white", edgecolor="black",
    )
    leg.get_frame().set_linewidth(0.45)

    fig.subplots_adjust(left=0.075, right=0.93, bottom=0.20, top=0.84,
                        wspace=0.12)
    plt.savefig(OUTPUT_PNG, dpi=400, bbox_inches="tight",
                facecolor="white", edgecolor="none")
    plt.savefig(OUTPUT_PDF, bbox_inches="tight",
                facecolor="white", edgecolor="none")
    plt.close()

    def _f(x, w, suf=""):
        if isinstance(x, float) and math.isnan(x):
            return "nan".rjust(w)
        if suf == "%":
            return f"{x * 100:.2f}%".rjust(w)
        return f"{x:.4f}".rjust(w)

    for suite in SUITES:
        print(f"\n=== {suite}  Rate {rate} ===")
        print(f"{'thr':>4}  {'IPC on':>9}  {'IPC off':>9}  "
              f"{'Prot on':>9}  {'Prot off':>9}")
        for idx, threshold in enumerate(THRESHOLDS):
            print(f"{threshold:>4}  "
                  f"{_f(ipc_means[(suite, rate, 'on')][idx], 9)}  "
                  f"{_f(ipc_means[(suite, rate, 'off')][idx], 9)}  "
                  f"{_f(protected_means[(suite, rate, 'on')][idx], 9, '%')}  "
                  f"{_f(protected_means[(suite, rate, 'off')][idx], 9, '%')}")
    print(f"Summary CSV: {OUTPUT_SUMMARY_CSV}")
    print(f"Workload CSV: {OUTPUT_WORKLOAD_CSV}")
    print(f"PNG: {OUTPUT_PNG}")
    print(f"PDF: {OUTPUT_PDF}")


if __name__ == "__main__":
    main()
