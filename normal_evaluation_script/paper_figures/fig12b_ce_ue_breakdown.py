#!/usr/bin/env python3
"""
Fig 12b: IPC and UE-vulnerable line fraction by page-offline threshold
         (LLC pinning ON vs OFF) — fig12 layout, CE/UE reliability metric.

Same two-panel (SPEC/GAP) layout and IPC bars as fig12, but the right-axis
marker reports the metric in SEC-DED terms ("Protected CE") rather than the
vaguer "protected lines":

  Protected CE (%) = protected_lines_pct
     = fraction of CE-bearing lines isolated (pinned or page-retired) so a
       second bit error cannot escalate CE -> UE (uncorrectable). Higher = safer.

  Bars (left axis)    — Normalized IPC vs 2MB no-error baseline.
  Markers (right axis)— Protected CE (%).

Source: raw_data.xlsx
  - sheet "Threshold sweep"       (pin_mode on/off, thresholds 2..256, 1e-8)
  - sheet "Way sweep in No error" (llc_size=2MB, llc_ways=16) — IPC baseline
Output: fig12b_ce_ue_breakdown.{csv,png,pdf}, *_workloads.csv
"""

import math
import os

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib import rcParams
from matplotlib.ticker import FuncFormatter
from matplotlib.patches import Patch
from matplotlib.lines import Line2D

from common_normal import load_xlsx_sheet, gmean, suite_of

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

OUTPUT_SUMMARY_CSV = os.path.join(SCRIPT_DIR, "fig12b_ce_ue_breakdown.csv")
OUTPUT_WORKLOAD_CSV = os.path.join(SCRIPT_DIR, "fig12b_ce_ue_breakdown_workloads.csv")
OUTPUT_PNG = os.path.join(SCRIPT_DIR, "fig12b_ce_ue_breakdown.png")
OUTPUT_PDF = os.path.join(SCRIPT_DIR, "fig12b_ce_ue_breakdown.pdf")

THRESHOLDS = [2, 4, 8, 16, 32, 256]
RATES = ["1e-5", "1e-6", "1e-7", "1e-8"]
PLOT_RATES = ["1e-8"]
PIN_MODES = ["on", "off"]
SUITES = ["SPEC", "GAP"]
REF_SIZE = "2MB"
BASELINE_WAYS = 16

COLOR_HARSH = "#2E6FDB"      # pin ON bar
COLOR_PIN_OFF = "#F08D39"    # pin OFF bar
COLOR_MARKER_ON = "#1F4FA0"  # pin ON marker
COLOR_MARKER_OFF = "#F08D39"  # pin OFF marker
EDGE = "black"


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
    # Protected-CE ratio (0..1): CE-bearing lines isolated (pinned or retired)
    # so a second bit error cannot escalate CE -> UE.
    df["prot_ratio"] = np.where(
        df["protected_lines_pct"].notna(),
        df["protected_lines_pct"] / 100.0,
        np.nan,
    )
    df["has_fate"] = df["prot_ratio"].notna()
    df = df.rename(columns={
        "error_rate": "rate",
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
    with np.errstate(divide="ignore", invalid="ignore"):
        ratio = df["ipc"] / df["baseline_ipc_2MB_no_error"]
    df["norm_ipc"] = np.where(
        df["completed"] & (df["baseline_ipc_2MB_no_error"] > 0.0),
        ratio,
        np.where(~df["completed"].astype(bool), 0.0, np.nan),
    )
    df["prot_pct"] = df["prot_ratio"] * 100.0

    summary_rows = []
    keys = [(s, r, p) for s in SUITES for r in RATES for p in PIN_MODES]
    ipc_means = {k: [] for k in keys}
    prot_means = {k: [] for k in keys}

    for suite in SUITES:
        for rate in RATES:
            for pin in PIN_MODES:
                for threshold in THRESHOLDS:
                    sub = df[(df["suite"] == suite) & (df["rate"] == rate)
                             & (df["threshold"] == threshold)
                             & (df["pin_mode"] == pin)]
                    prot_vals = sub[sub["has_fate"]]["prot_ratio"].tolist()
                    ipc_vals = sub["norm_ipc"].dropna().tolist()
                    prot_avg = float(np.mean(prot_vals)) if prot_vals else math.nan
                    ipc_avg = (gmean(ipc_vals, include_zeros=True)
                               if ipc_vals else math.nan)
                    prot_means[(suite, rate, pin)].append(prot_avg)
                    ipc_means[(suite, rate, pin)].append(ipc_avg)
                    summary_rows.append({
                        "suite": suite, "rate": rate, "pin_mode": pin,
                        "threshold": threshold,
                        "n_workloads_ipc": len(ipc_vals),
                        "gmean_norm_ipc": ipc_avg,
                        "n_workloads_prot": len(prot_vals),
                        "mean_protected_ce_pct":
                            prot_avg * 100.0 if not math.isnan(prot_avg) else math.nan,
                    })

    pd.DataFrame(summary_rows).to_csv(OUTPUT_SUMMARY_CSV, index=False)
    df.to_csv(OUTPUT_WORKLOAD_CSV, index=False)

    rate = PLOT_RATES[0]
    fig, axes = plt.subplots(1, 2, figsize=(7.0, 2.05), sharey=True)
    x_vals = np.arange(len(THRESHOLDS), dtype=float)
    bar_w = 0.36
    pin_offsets = {pin: (i - (len(PIN_MODES) - 1) / 2) * bar_w
                   for i, pin in enumerate(PIN_MODES)}
    bar_color = {"on": COLOR_HARSH, "off": COLOR_PIN_OFF}
    mk_color = {"on": COLOR_MARKER_ON, "off": COLOR_MARKER_OFF}
    mk_shape = {"on": "o", "off": "s"}

    marker_axes = []
    for ax_bar, suite in zip(axes, SUITES):
        ax_marker = ax_bar.twinx()
        marker_axes.append(ax_marker)
        for pin in PIN_MODES:
            ax_bar.bar(
                x_vals + pin_offsets[pin], ipc_means[(suite, rate, pin)],
                width=bar_w, color=bar_color[pin],
                edgecolor=EDGE, linewidth=0.55, alpha=0.9, zorder=3,
            )
        for pin in PIN_MODES:
            ys = prot_means[(suite, rate, pin)]
            valid = [(x, y) for x, y in zip(x_vals, ys)
                     if not (isinstance(y, float) and math.isnan(y))]
            if valid:
                vx, vy = zip(*valid)
                ax_marker.plot(
                    vx, vy, color=mk_color[pin],
                    linewidth=0.9, linestyle=(0, (2, 1.5)),
                    marker=mk_shape[pin], markersize=5.0,
                    markerfacecolor=mk_color[pin],
                    markeredgecolor="white", markeredgewidth=0.5,
                    alpha=0.95, zorder=5,
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
    marker_axes[0].set_yticklabels([])
    marker_axes[1].set_ylabel("Protected CE (%)", labelpad=3)

    # --- 4-item legend: bars (IPC) and markers (UE-vuln) kept separate ---
    bar_on = Patch(facecolor=COLOR_HARSH, edgecolor=EDGE, linewidth=0.55)
    bar_off = Patch(facecolor=COLOR_PIN_OFF, edgecolor=EDGE, linewidth=0.55)
    mk_on = Line2D([0], [0], marker="o", linestyle=(0, (2, 1.5)),
                   linewidth=0.9, color=COLOR_MARKER_ON,
                   markerfacecolor=COLOR_MARKER_ON,
                   markeredgecolor="white", markeredgewidth=0.5, markersize=5.5)
    mk_off = Line2D([0], [0], marker="s", linestyle=(0, (2, 1.5)),
                    linewidth=0.9, color=COLOR_MARKER_OFF,
                    markerfacecolor=COLOR_MARKER_OFF,
                    markeredgecolor="white", markeredgewidth=0.5, markersize=5.5)
    leg = fig.legend(
        [bar_on, bar_off, mk_on, mk_off],
        ["IPC — w/ Pinning", "IPC — w/o Pinning",
         "Protected CE — w/ Pinning", "Protected CE — w/o Pinning"],
        ncol=2, loc="upper center", bbox_to_anchor=(0.5, 1.08),
        fontsize=6.8, handlelength=2.2, handletextpad=0.5,
        columnspacing=1.4, labelspacing=0.4, borderpad=0.35,
        frameon=True, fancybox=False, framealpha=1.0,
        facecolor="white", edgecolor="black",
    )
    leg.get_frame().set_linewidth(0.45)

    fig.subplots_adjust(left=0.075, right=0.93, bottom=0.20, top=0.80,
                        wspace=0.12)
    plt.savefig(OUTPUT_PNG, dpi=400, bbox_inches="tight",
                facecolor="white", edgecolor="none")
    plt.savefig(OUTPUT_PDF, bbox_inches="tight",
                facecolor="white", edgecolor="none")
    plt.close()

    def _f(x, w, pct=False):
        if isinstance(x, float) and math.isnan(x):
            return "nan".rjust(w)
        return (f"{x * 100:.1f}%".rjust(w) if pct else f"{x:.4f}".rjust(w))

    for suite in SUITES:
        print(f"\n=== {suite}  Rate {rate} ===")
        print(f"{'thr':>4}  {'IPC on':>9}  {'IPC off':>9}  "
              f"{'ProtCE on':>10}  {'ProtCE off':>10}")
        for i, t in enumerate(THRESHOLDS):
            print(f"{t:>4}  {_f(ipc_means[(suite, rate, 'on')][i], 9)}  "
                  f"{_f(ipc_means[(suite, rate, 'off')][i], 9)}  "
                  f"{_f(prot_means[(suite, rate, 'on')][i], 10, True)}  "
                  f"{_f(prot_means[(suite, rate, 'off')][i], 10, True)}")
    print(f"\nSummary CSV: {OUTPUT_SUMMARY_CSV}\nPNG: {OUTPUT_PNG}")


if __name__ == "__main__":
    main()
