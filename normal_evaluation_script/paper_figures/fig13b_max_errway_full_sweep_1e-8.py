#!/usr/bin/env python3
"""
Fig 13b: Full reserved-way sweep (1/2/4/6/8/10/12) at 2MB LLC, CE rate 1e-8.

GMEAN summary of fig13 across the complete max_error_way range, to answer
"how many LLC ways should we reserve?" — protection vs the IPC cost of taking
ways away from the normal cache.

  Bars (left axis)   — Normalized IPC (GMEAN) vs 2MB/16-way no-error baseline.
  Line (right axis)  — Protected Error Lines (%) = mean of protected_lines_pct.
Two panels: SPEC and GAP.

Source: raw_data.xlsx
  - sheet "Max error way sweep"   (error_rate = 1e-8, max_error_way 1..12)
  - sheet "Way sweep in No error" (llc_size = 2MB, llc_ways = 16) — baseline
Output: fig13b_max_errway_full_sweep_1e-8.{csv,png,pdf}
"""

import os

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib import rcParams
from matplotlib.ticker import FormatStrFormatter
from matplotlib.patches import Patch
from matplotlib.lines import Line2D

from common_normal import load_xlsx_sheet, gmean

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_CSV = os.path.join(SCRIPT_DIR, "fig13b_max_errway_full_sweep_1e-8.csv")
OUTPUT_PNG = os.path.join(SCRIPT_DIR, "fig13b_max_errway_full_sweep_1e-8.png")
OUTPUT_PDF = os.path.join(SCRIPT_DIR, "fig13b_max_errway_full_sweep_1e-8.pdf")

TARGET_RATE = "1e-8"
WAYS = [1, 2, 4, 6, 8, 10, 12]
SUITES = ["SPEC", "GAP"]

COLOR_IPC = "#3182bd"
COLOR_PROT = "#d62728"
EDGE = "black"


def setup_style():
    rcParams.update({
        "font.family": "sans-serif",
        "font.sans-serif": ["Helvetica", "Arial", "DejaVu Sans"],
        "font.size": 7, "axes.linewidth": 0.7,
        "axes.labelsize": 7.5, "xtick.labelsize": 7, "ytick.labelsize": 7,
        "legend.fontsize": 7, "pdf.fonttype": 42, "ps.fonttype": 42,
    })


def main():
    setup_style()
    df = load_xlsx_sheet("Max error way sweep")
    df = df[df["error_rate"] == TARGET_RATE].copy()

    bl = load_xlsx_sheet("Way sweep in No error")
    bl = bl[(bl["llc_size"] == "2MB") & (bl["llc_ways"] == 16)]
    base = {r["workload"]: (float(r["ipc"]) if pd.notna(r["ipc"]) else 0.0)
            for _, r in bl.iterrows()}

    df["base_ipc"] = df["workload"].map(base).fillna(0.0)
    df["norm_ipc"] = np.where(
        df["completed"] & (df["base_ipc"] > 0) & df["ipc"].notna(),
        df["ipc"] / df["base_ipc"], np.nan)

    rows, ipc_g, prot_m = [], {s: [] for s in SUITES}, {s: [] for s in SUITES}
    for s in SUITES:
        for w in WAYS:
            sub = df[(df["suite"] == s) & (df["max_error_way"] == w)]
            ipc_vals = sub["norm_ipc"].dropna().tolist()
            prot_vals = sub["protected_lines_pct"].dropna().tolist()
            gi = gmean(ipc_vals) if ipc_vals else float("nan")
            pm = float(np.mean(prot_vals)) if prot_vals else float("nan")
            ipc_g[s].append(gi)
            prot_m[s].append(pm)
            rows.append({"suite": s, "max_error_way": w, "n": len(ipc_vals),
                         "gmean_norm_ipc": gi, "mean_protected_pct": pm})
    pd.DataFrame(rows).to_csv(OUTPUT_CSV, index=False)

    fig, axes = plt.subplots(1, 2, figsize=(7.0, 2.3), sharey=True)
    x = np.arange(len(WAYS), dtype=float)
    markers = []
    for ax, s in zip(axes, SUITES):
        axm = ax.twinx()
        markers.append(axm)
        ax.bar(x, ipc_g[s], 0.62, color=COLOR_IPC, edgecolor=EDGE,
               linewidth=0.5, zorder=2, alpha=0.9)
        axm.plot(x, prot_m[s], color=COLOR_PROT, linewidth=1.3, marker="o",
                 markersize=4.5, markerfacecolor=COLOR_PROT,
                 markeredgecolor="white", markeredgewidth=0.6, zorder=5)
        for xv, pv in zip(x, prot_m[s]):
            axm.annotate(f"{pv:.0f}", (xv, pv), textcoords="offset points",
                         xytext=(0, 5), ha="center", fontsize=5.4,
                         color=COLOR_PROT)
        ax.set_xticks(x)
        ax.set_xticklabels([str(w) for w in WAYS])
        ax.set_xlabel("Reserved error ways (of 16)", labelpad=2)
        ax.set_ylim(0.0, 1.05)
        ax.set_xlim(x[0] - 0.6, x[-1] + 0.6)
        ax.yaxis.grid(True, linestyle=":", linewidth=0.5, alpha=0.55)
        ax.set_axisbelow(True)
        ax.set_title(s, fontsize=8, pad=2)
        axm.set_ylim(70, 102)
        axm.yaxis.set_major_formatter(FormatStrFormatter("%.0f"))
        for a in (ax, axm):
            for sp in a.spines.values():
                sp.set_linewidth(0.7); sp.set_color("black")

    axes[0].set_ylabel("Normalized IPC", labelpad=3)
    markers[0].set_yticklabels([])
    markers[1].set_ylabel("Protected Lines (%)", labelpad=3)

    handles = [
        Patch(facecolor=COLOR_IPC, edgecolor=EDGE, linewidth=0.5,
              label="Normalized IPC"),
        Line2D([0], [0], color=COLOR_PROT, marker="o", markersize=5,
               markerfacecolor=COLOR_PROT, markeredgecolor="white",
               label="Protected Lines (%)"),
    ]
    fig.legend(handles=handles, loc="upper center", ncol=2,
               bbox_to_anchor=(0.5, 1.04), frameon=True, fancybox=False,
               framealpha=1.0, facecolor="white", edgecolor="black",
               fontsize=7).get_frame().set_linewidth(0.5)

    fig.subplots_adjust(left=0.075, right=0.93, bottom=0.18, top=0.83,
                        wspace=0.1)
    plt.savefig(OUTPUT_PNG, dpi=400, bbox_inches="tight",
                facecolor="white", edgecolor="none")
    plt.savefig(OUTPUT_PDF, bbox_inches="tight",
                facecolor="white", edgecolor="none")
    plt.close()

    print(f"{'way':>4} | " + " ".join(f"{s+'_IPC':>9} {s+'_prot':>9}"
                                       for s in SUITES))
    for i, w in enumerate(WAYS):
        print(f"{w:>4} | " + " ".join(
            f"{ipc_g[s][i]:>9.4f} {prot_m[s][i]:>8.1f}%" for s in SUITES))
    print(f"\nCSV: {OUTPUT_CSV}\nPNG: {OUTPUT_PNG}")


if __name__ == "__main__":
    main()
