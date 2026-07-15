#!/usr/bin/env python3
"""
Baseline LLC MPKI characterization.

Source:
  - results/normal_evaluation/4_llc_size_baseline/
      llc_baseline_2MB_<trace>.txt

LLC MPKI is computed from no-error baseline runs as:
    LLC misses / retired instructions * 1000

Output:
  - fig6c_baseline_llc_mpki.csv
  - fig6c_baseline_llc_mpki.png
  - fig6c_baseline_llc_mpki.pdf
"""

import os
import re

import matplotlib.pyplot as plt
import pandas as pd
from matplotlib import rcParams

from common_normal import extract_metrics, extract_workload

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
BASE_DIR = os.path.dirname(SCRIPT_DIR)
BASELINE_DIR = os.path.join(BASE_DIR, "results", "normal_evaluation",
                            "4_llc_size_baseline")

REF_SIZE = "2MB"

OUTPUT_CSV = os.path.join(SCRIPT_DIR, "fig6c_baseline_llc_mpki.csv")
OUTPUT_PNG = os.path.join(SCRIPT_DIR, "fig6c_baseline_llc_mpki.png")
OUTPUT_PDF = os.path.join(SCRIPT_DIR, "fig6c_baseline_llc_mpki.pdf")

RE_BASELINE = re.compile(r"^llc_baseline_(?P<size>\d+MB)_(?P<trace>.+)\.txt$")


def short_name(workload: str) -> str:
    match = re.match(r"^\d+\.([A-Za-z0-9]+?)(?:_s)?$", workload)
    return match.group(1) if match else workload


def setup_style():
    rcParams.update({
        "font.family": "sans-serif",
        "font.sans-serif": ["Helvetica", "Arial", "DejaVu Sans"],
        "font.size": 7,
        "axes.linewidth": 0.7,
        "axes.labelsize": 7.5,
        "axes.titlesize": 7.5,
        "xtick.labelsize": 6,
        "ytick.labelsize": 6.2,
        "pdf.fonttype": 42,
        "ps.fonttype": 42,
    })


def load_baseline_llc_mpki():
    rows = []
    if not os.path.isdir(BASELINE_DIR):
        raise SystemExit(f"Baseline dir not found: {BASELINE_DIR}")

    for fname in sorted(os.listdir(BASELINE_DIR)):
        match = RE_BASELINE.match(fname)
        if not match or match.group("size") != REF_SIZE:
            continue

        path = os.path.join(BASELINE_DIR, fname)
        metrics = extract_metrics(path)
        workload = extract_workload(match.group("trace"))

        if not metrics.instructions or metrics.instructions <= 0:
            continue
        if metrics.llc_miss is None:
            continue

        llc_mpki = metrics.llc_miss / metrics.instructions * 1000.0
        rows.append({
            "llc_size": REF_SIZE,
            "workload": workload,
            "short": short_name(workload),
            "ipc": metrics.ipc,
            "instructions": metrics.instructions,
            "llc_access": metrics.llc_access,
            "llc_hit": metrics.llc_hit,
            "llc_miss": metrics.llc_miss,
            "llc_miss_rate_pct": metrics.llc_miss_rate,
            "llc_mpki": llc_mpki,
        })

    if not rows:
        raise SystemExit(f"No valid {REF_SIZE} no-error baseline LLC stats found")

    rows.sort(key=lambda r: (-r["llc_mpki"], r["short"]))
    return rows


def main():
    setup_style()
    rows = load_baseline_llc_mpki()
    df = pd.DataFrame(rows)
    df.to_csv(OUTPUT_CSV, index=False)

    x = range(len(df))
    fig, ax = plt.subplots(figsize=(4.8, 1.9))
    bars = ax.bar(
        x, df["llc_mpki"],
        width=0.62, color="#5e7ac4", edgecolor="black", linewidth=0.45,
        zorder=3
    )

    ax.set_xticks(list(x))
    ax.set_xticklabels(df["short"], rotation=32, ha="right",
                       rotation_mode="anchor")
    ax.set_ylabel("LLC MPKI")
    ax.set_xlabel("")
    ax.set_title(f"No-error baseline LLC MPKI ({REF_SIZE})", pad=3)
    ax.set_xlim(-0.5, len(df) - 0.5)
    ax.set_ylim(0, max(df["llc_mpki"]) * 1.14)
    ax.yaxis.grid(True, linestyle=":", linewidth=0.5, alpha=0.6)
    ax.set_axisbelow(True)
    ax.tick_params(axis="both", which="both", length=2, pad=1)

    for bar, value in zip(bars, df["llc_mpki"]):
        ax.text(
            bar.get_x() + bar.get_width() / 2, bar.get_height(),
            f"{value:.1f}", ha="center", va="bottom",
            fontsize=5.2, rotation=90, clip_on=False
        )

    for spine in ax.spines.values():
        spine.set_visible(True)
        spine.set_linewidth(0.7)
        spine.set_color("black")

    fig.subplots_adjust(left=0.095, right=0.995, bottom=0.31, top=0.83)
    plt.savefig(OUTPUT_PNG, dpi=400, bbox_inches="tight",
                facecolor="white", edgecolor="none")
    plt.savefig(OUTPUT_PDF, bbox_inches="tight",
                facecolor="white", edgecolor="none")
    plt.close()

    print(f"Workloads: {len(df)}")
    print(f"LLC MPKI range: {df['llc_mpki'].min():.3f} - {df['llc_mpki'].max():.3f}")
    print("Order:", ", ".join(df["short"]))
    print(f"CSV: {OUTPUT_CSV}")
    print(f"PNG: {OUTPUT_PNG}")
    print(f"PDF: {OUTPUT_PDF}")


if __name__ == "__main__":
    main()
