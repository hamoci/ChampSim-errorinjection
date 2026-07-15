#!/usr/bin/env python3
"""
Fig 4: No-error baseline vs Conventional Page offline. (Motivation)

Source: raw_data.xlsx
  - sheet "Way sweep in No error" (llc_size=2MB, llc_ways=16) — baseline
  - sheet "Threshold sweep"       (pin_mode=off, threshold=2)

Also reads fig10_capacity_waste.csv (same directory) to overlay mean
capacity-waste markers on the right log axis.
"""

import os

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib import rcParams
from matplotlib.ticker import LogLocator, NullLocator
from matplotlib.patches import Patch
from matplotlib.lines import Line2D

from common_normal import load_xlsx_sheet, gmean, suite_of

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

OUTPUT_CSV = os.path.join(SCRIPT_DIR, "fig4_no_error_vs_offline.csv")
OUTPUT_PNG = os.path.join(SCRIPT_DIR, "fig4_no_error_vs_offline.png")
OUTPUT_PDF = os.path.join(SCRIPT_DIR, "fig4_no_error_vs_offline.pdf")
WASTE_CSV = os.path.join(SCRIPT_DIR, "fig10_capacity_waste.csv")

REF_SIZE = "2MB"
BASELINE_WAYS = 16
RATES = ["1e-5", "1e-6", "1e-7", "1e-8"]
OFFLINE_THRESHOLD = 2
SUITES = ["SPEC", "GAP"]
# suite = lightness of the offline hue (SPEC dark, GAP light), matching the
# paired-shade scheme used in fig9/fig10.
OFFLINE_COLOR = {"SPEC": "#E5487E", "GAP": "#F4A6C2"}
MTBCE_LABEL = {
    "1e-5": "36 ms",
    "1e-6": "3.6 ms",
    "1e-7": "360 us",
    "1e-8": "36 us",
}

COLOR_WASTE = "#222222"
PAGE_SIZE_MB = 2.0


def load_capacity_waste():
    """Per-(suite, rate) mean offline capacity waste (MB), from fig10 CSV."""
    if not os.path.isfile(WASTE_CSV):
        return None
    df = pd.read_csv(WASTE_CSV, dtype={"rate": str})
    has_suite = "suite" in df.columns
    out = {}
    for suite in SUITES:
        for rate in RATES:
            sub = df[df["rate"] == rate]
            if has_suite:
                sub = sub[sub["suite"] == suite]
            vals = sub["pin_off_pages_retired"]
            out[(suite, rate)] = (float(vals.mean()) * PAGE_SIZE_MB
                                  if not vals.empty else float("nan"))
    return out


def load_no_error_baseline():
    df = load_xlsx_sheet("Way sweep in No error")
    df = df[(df["llc_size"] == REF_SIZE) & (df["llc_ways"] == BASELINE_WAYS)]
    return {r["workload"]: (float(r["ipc"]) if pd.notna(r["ipc"]) else 0.0)
            for _, r in df.iterrows()}


def load_offline_sweep():
    df = load_xlsx_sheet("Threshold sweep")
    df = df[(df["pin_mode"] == "off")
            & (df["retirement_threshold"] == OFFLINE_THRESHOLD)
            & (df["error_rate"].isin(RATES))]
    out = {rate: {} for rate in RATES}
    for _, r in df.iterrows():
        out[r["error_rate"]][r["workload"]] = (
            float(r["ipc"]) if pd.notna(r["ipc"]) else 0.0
        )
    return out


def setup_style():
    rcParams.update({
        "font.family": "sans-serif",
        "font.sans-serif": ["Helvetica", "Arial", "DejaVu Sans"],
        "font.size": 8,
        "axes.linewidth": 0.7,
        "axes.labelsize": 8,
        "axes.titlesize": 8,
        "xtick.labelsize": 7,
        "ytick.labelsize": 7,
        "legend.fontsize": 6.8,
        "pdf.fonttype": 42,
        "ps.fonttype": 42,
    })


def main():
    setup_style()

    baseline = load_no_error_baseline()
    offline = load_offline_sweep()
    if not baseline:
        raise SystemExit(f"No no-error baseline data found for {REF_SIZE}")

    all_wls = set(baseline.keys())
    for rate in RATES:
        all_wls |= set(offline[rate].keys())
    wls_by_suite = {s: sorted(w for w in all_wls if suite_of(w) == s)
                    for s in SUITES}

    # Per-(suite, rate) offline geomean normalized IPC. Panicked runs are
    # IPC 0 and counted (collapsing the bar); completed runs normalized.
    rows = []
    offline_gmean = {}
    for rate in RATES:
        for s in SUITES:
            vals = []
            for wl in wls_by_suite[s]:
                ref_ipc = baseline.get(wl, 0.0)
                off_ipc = offline[rate].get(wl, 0.0)
                norm = off_ipc / ref_ipc if ref_ipc > 0 else 0.0
                vals.append(norm)
                rows.append({
                    "suite": s, "rate": rate, "mtbce": MTBCE_LABEL[rate],
                    "workload": wl, "baseline_ipc_no_error_2mb": ref_ipc,
                    "offline_ipc": off_ipc, "norm_offline_vs_no_error": norm,
                })
            offline_gmean[(s, rate)] = gmean(vals, include_zeros=True)

    pd.DataFrame(rows).to_csv(OUTPUT_CSV, index=False)

    x = np.arange(len(RATES), dtype=float)
    fig, ax = plt.subplots(figsize=(3.74, 1.975))

    bar_w = 0.38
    for i, s in enumerate(SUITES):
        offset = (i - (len(SUITES) - 1) / 2) * bar_w
        ys = [offline_gmean[(s, rate)] for rate in RATES]
        ax.bar(x + offset, ys, width=bar_w,
               color=OFFLINE_COLOR[s], edgecolor="black", linewidth=0.5,
               zorder=3)

    ax.set_xticks(x)
    ax.set_xticklabels(["1", "10", "100", "1000"])
    ax.set_xlabel(r"CE Rate ($\times 10^{5}$ errors/hour)")
    ax.set_xlim(x[0] - 0.5, x[-1] + 0.5)

    ax.set_ylim(0.0, 1.15)
    ax.set_ylabel("Normalized IPC")
    ax.yaxis.grid(True, linestyle=":", linewidth=0.5, alpha=0.6)
    ax.set_axisbelow(True)

    for spine in ax.spines.values():
        spine.set_visible(True)
        spine.set_linewidth(0.7)
        spine.set_color("black")

    waste = load_capacity_waste()
    legend_handles = [
        Patch(facecolor=OFFLINE_COLOR["SPEC"], edgecolor="black", linewidth=0.5,
              label="IPC (SPEC)"),
        Patch(facecolor=OFFLINE_COLOR["GAP"], edgecolor="black", linewidth=0.5,
              label="IPC (GAP)"),
    ]
    if waste is not None:
        ax2 = ax.twinx()
        ax2.set_yscale("log")
        ax2.set_ylim(1.0, 1e6)
        waste_marker = {"SPEC": "D", "GAP": "o"}
        for s in SUITES:
            # Clamp to the log floor (1 MB) so sub-MB points still render at the
            # bottom instead of vanishing; NaN (all-panic, e.g. GAP @1e-8) skip.
            pts = [(xi, max(waste[(s, rate)], 1.0))
                   for xi, rate in zip(x, RATES)
                   if np.isfinite(waste[(s, rate)])]
            if pts:
                wx, wy = zip(*pts)
                ax2.plot(wx, wy, color=COLOR_WASTE, linewidth=1.3,
                         linestyle="--", marker=waste_marker[s], markersize=6.0,
                         markerfacecolor=COLOR_WASTE, markeredgecolor="black",
                         markeredgewidth=0.6, zorder=5)
            legend_handles.append(Line2D(
                [0], [0], marker=waste_marker[s], color=COLOR_WASTE,
                linestyle="--", linewidth=1.3, markerfacecolor=COLOR_WASTE,
                markeredgecolor="black", markeredgewidth=0.6, markersize=5.5,
                label=f"Waste ({s})"))
        ax2.set_ylabel("Capacity Waste (MB)", fontsize=8, labelpad=3)
        ax2.tick_params(axis="y", labelsize=7)
        ax2.yaxis.set_major_locator(LogLocator(base=10.0, numticks=7))
        ax2.yaxis.set_minor_locator(NullLocator())
        ax2.grid(False)
        for spine in ax2.spines.values():
            spine.set_visible(True)
            spine.set_linewidth(0.7)
            spine.set_color("black")

    leg = ax.legend(handles=legend_handles, ncol=2,
                    loc="upper center", bbox_to_anchor=(0.5, 1.30),
                    fontsize=6.4, handlelength=1.5, handletextpad=0.4,
                    columnspacing=1.0, borderpad=0.35, borderaxespad=0.0,
                    frameon=True, fancybox=False, framealpha=1.0,
                    facecolor="white", edgecolor="black")
    leg.get_frame().set_linewidth(0.5)

    plt.tight_layout(pad=0.25)
    plt.savefig(OUTPUT_PNG, dpi=400, bbox_inches="tight",
                facecolor="white", edgecolor="none")
    plt.savefig(OUTPUT_PDF, bbox_inches="tight",
                facecolor="white", edgecolor="none")
    plt.close()

    n_spec = len(wls_by_suite["SPEC"])
    print(f"Workloads: {len(all_wls)} (SPEC={n_spec}, GAP={len(all_wls)-n_spec})")
    print("Rate    MTBCE   SPEC IPC   GAP IPC")
    for rate in RATES:
        print(f"{rate:>6}  {MTBCE_LABEL[rate]:>6}  "
              f"{offline_gmean[('SPEC', rate)]:8.4f}  "
              f"{offline_gmean[('GAP', rate)]:8.4f}")
    print(f"CSV: {OUTPUT_CSV}")
    print(f"PNG: {OUTPUT_PNG}")
    print(f"PDF: {OUTPUT_PDF}")


if __name__ == "__main__":
    main()
