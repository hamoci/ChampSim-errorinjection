#!/usr/bin/env python3
"""
Fig 0: Baseline LLC MPKI per workload (2MB LLC, no errors).
Bars sorted by MPKI in descending order.

Source: raw_data.xlsx, sheet "Way sweep in No error"
        (filtered to llc_size = 2MB, llc_ways = 16)
Output: fig0_baseline_llc_mpki.{csv,png,pdf}
"""

import os
import re

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib import rcParams

from common_normal import load_xlsx_sheet, suite_of

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

OUTPUT_CSV = os.path.join(SCRIPT_DIR, "fig0_baseline_llc_mpki.csv")
OUTPUT_PNG = os.path.join(SCRIPT_DIR, "fig0_baseline_llc_mpki.png")
OUTPUT_PDF = os.path.join(SCRIPT_DIR, "fig0_baseline_llc_mpki.pdf")

TARGET_SIZE = "2MB"
BASELINE_WAYS = 16
BAR_COLOR = "#0072B2"
SUITES = ["SPEC", "GAP"]
# matches the paper-wide blue + raspberry accent pair
SUITE_COLOR = {"SPEC": "#2E6FDB", "GAP": "#E5487E"}


def short_name(workload):
    m = re.match(r"^\d+\.([A-Za-z0-9]+?)(?:_s)?$", workload)
    return m.group(1) if m else workload


def setup_style():
    rcParams.update({
        "font.family": "sans-serif",
        "font.sans-serif": ["Helvetica", "Arial", "DejaVu Sans"],
        "font.size": 8,
        "axes.linewidth": 0.7,
        "axes.labelsize": 8,
        "axes.titlesize": 8,
        "xtick.labelsize": 6.8,
        "ytick.labelsize": 7,
        "legend.fontsize": 7,
        "pdf.fonttype": 42,
        "ps.fonttype": 42,
    })


def main():
    setup_style()
    df = load_xlsx_sheet("Way sweep in No error")
    df = df[(df["llc_size"] == TARGET_SIZE) & (df["llc_ways"] == BASELINE_WAYS)]

    records = []
    for _, r in df.iterrows():
        if pd.isna(r["llc_mpki"]):
            continue
        wl = r["workload"]
        records.append({
            "suite": suite_of(wl),
            "llc_size": TARGET_SIZE,
            "workload": wl,
            "short": short_name(wl),
            "ipc": r["ipc"],
            "llc_mpki": float(r["llc_mpki"]),
        })

    # SPEC group then GAP group, each sorted by descending MPKI.
    records.sort(key=lambda r: (SUITES.index(r["suite"]), -r["llc_mpki"]))
    pd.DataFrame(records).to_csv(OUTPUT_CSV, index=False)

    labels = [r["short"] for r in records]
    mpki_vals = [r["llc_mpki"] for r in records]
    colors = [SUITE_COLOR[r["suite"]] for r in records]
    x = np.arange(len(labels))

    fig, ax = plt.subplots(figsize=(7.0, 1.975))
    ax.bar(x, mpki_vals, width=0.7,
           color=colors, edgecolor="black", linewidth=0.5,
           zorder=3)

    for xi, v in zip(x, mpki_vals):
        ax.text(xi, v + 0.4, f"{v:.0f}",
                ha="center", va="bottom", fontsize=5.0,
                color="#1a1a1a")

    # Divider between the SPEC and GAP groups.
    n_spec = sum(1 for r in records if r["suite"] == "SPEC")
    if 0 < n_spec < len(records):
        ax.axvline(n_spec - 0.5, color="#808080", linewidth=0.6,
                   linestyle="--", zorder=1)

    ax.set_xticks(x)
    ax.set_xticklabels(labels, rotation=45, ha="right", rotation_mode="anchor")
    ax.set_xlim(x[0] - 0.55, x[-1] + 0.55)
    ax.set_ylabel("LLC MPKI")
    ax.set_ylim(0, max(mpki_vals) * 1.15)
    ax.yaxis.grid(True, linestyle=":", linewidth=0.5, alpha=0.6)
    ax.set_axisbelow(True)
    ax.tick_params(axis="x", which="both", length=2, pad=1)
    ax.tick_params(axis="y", which="both", length=2, pad=1)
    from matplotlib.patches import Patch
    ax.legend(handles=[Patch(facecolor=SUITE_COLOR[s], edgecolor="black",
                             linewidth=0.5, label=s) for s in SUITES],
              loc="upper right", frameon=True, fancybox=False,
              framealpha=1.0, edgecolor="black", handlelength=1.2)
    for spine in ax.spines.values():
        spine.set_visible(True)
        spine.set_linewidth(0.7)
        spine.set_color("black")

    plt.tight_layout(pad=0.25)
    plt.savefig(OUTPUT_PNG, dpi=400, bbox_inches="tight",
                facecolor="white", edgecolor="none")
    plt.savefig(OUTPUT_PDF, bbox_inches="tight",
                facecolor="white", edgecolor="none")
    plt.close()

    print(f"Workloads: {len(records)}")
    for r in records:
        print(f"  {r['short']:>12}  MPKI={r['llc_mpki']:7.2f}")
    print(f"CSV: {OUTPUT_CSV}")
    print(f"PNG: {OUTPUT_PNG}")
    print(f"PDF: {OUTPUT_PDF}")


if __name__ == "__main__":
    main()
