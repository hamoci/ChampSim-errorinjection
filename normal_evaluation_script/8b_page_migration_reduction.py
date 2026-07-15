#!/usr/bin/env python3
"""
Page migration reduction from LLC pinning.

The simulator reports page offlining/retirement counters rather than a separate
OS migration counter, so this figure uses retired pages as the migration proxy:
  - Conventional Page Offline: "Baseline Page Retirements"
  - LLC Pinning: "Pages Retired"

Only runs that completed in both modes are used for the plotted comparisons.
Rows for all parsed runs are retained in the CSV with completion flags.

Outputs:
  - fig8b_page_migration_reduction_summary.csv
  - fig8b_page_migration_reduction_workloads_1e-8.csv
  - fig8b_page_migration_reduction.png
  - fig8b_page_migration_reduction.pdf
"""

import os
import re

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib import rcParams
from matplotlib.patches import Patch

from common_normal import extract_metrics, extract_workload

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
BASE_DIR = os.path.dirname(SCRIPT_DIR)
SWEEP_DIR = os.path.join(BASE_DIR, "results", "normal_evaluation",
                         "1_error_rate_sweep")
OFFLINE_DIR = os.path.join(BASE_DIR, "results", "normal_evaluation",
                           "2_retirement_threshold")
BASELINE_DIR = os.path.join(BASE_DIR, "results", "normal_evaluation",
                            "4_llc_size_baseline")

OUTPUT_SUMMARY_CSV = os.path.join(
    SCRIPT_DIR, "fig8b_page_migration_reduction_summary.csv")
OUTPUT_WORKLOAD_CSV = os.path.join(
    SCRIPT_DIR, "fig8b_page_migration_reduction_workloads_1e-8.csv")
OUTPUT_PNG = os.path.join(SCRIPT_DIR, "fig8b_page_migration_reduction.png")
OUTPUT_PDF = os.path.join(SCRIPT_DIR, "fig8b_page_migration_reduction.pdf")

RE_PIN_ON = re.compile(r"^pin_on_(?P<rate>1e-\d+)_(?P<trace>.+)\.txt$")
RE_OFFLINE = re.compile(r"^retire_off_2_(?P<rate>1e-\d+)_(?P<trace>.+)\.txt$")
RE_BASELINE = re.compile(r"^llc_baseline_(?P<size>\d+MB)_(?P<trace>.+)\.txt$")
RE_IPC = re.compile(r"CPU 0 cumulative IPC:\s+([\d.]+)\s+instructions:")
RE_PIN_OFF_RETIRED = re.compile(r"Baseline Page Retirements:\s+(\d+)")
RE_PIN_ON_RETIRED = re.compile(r"Pages Retired:\s+(\d+)")

REF_SIZE = "2MB"
RATES = ["1e-5", "1e-6", "1e-7", "1e-8"]
TARGET_RATE = "1e-8"

COLOR_PIN = "#5e7ac4"
COLOR_OFFLINE = "#f08d39"
EDGE = "black"


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
        "xtick.labelsize": 5.7,
        "ytick.labelsize": 6.2,
        "legend.fontsize": 6.8,
        "pdf.fonttype": 42,
        "ps.fonttype": 42,
    })


def parse_run(path, mode):
    try:
        with open(path, "r") as f:
            txt = f.read()
    except Exception:
        return 0, False

    completed = bool(RE_IPC.search(txt))
    if mode == "off":
        matches = RE_PIN_OFF_RETIRED.findall(txt)
    else:
        matches = RE_PIN_ON_RETIRED.findall(txt)
    migrated_pages = int(matches[-1]) if matches else 0
    return migrated_pages, completed


def load_sweep():
    # out[(mode, rate)][workload] = {"pages": int, "completed": bool}
    out = {}
    if not os.path.isdir(SWEEP_DIR):
        raise SystemExit(f"Sweep dir not found: {SWEEP_DIR}")
    if not os.path.isdir(OFFLINE_DIR):
        raise SystemExit(f"Offline dir not found: {OFFLINE_DIR}")

    for fname in sorted(os.listdir(SWEEP_DIR)):
        match = RE_PIN_ON.match(fname)
        if not match or match.group("rate") not in RATES:
            continue
        rate = match.group("rate")
        workload = extract_workload(match.group("trace"))
        pages, completed = parse_run(os.path.join(SWEEP_DIR, fname), "on")
        out.setdefault(("on", rate), {})[workload] = {
            "pages": pages,
            "completed": completed,
        }

    for fname in sorted(os.listdir(OFFLINE_DIR)):
        match = RE_OFFLINE.match(fname)
        if not match or match.group("rate") not in RATES:
            continue
        rate = match.group("rate")
        workload = extract_workload(match.group("trace"))
        pages, completed = parse_run(os.path.join(OFFLINE_DIR, fname), "off")
        out.setdefault(("off", rate), {})[workload] = {
            "pages": pages,
            "completed": completed,
        }

    return out


def load_baseline_llc_mpki():
    out = {}
    if not os.path.isdir(BASELINE_DIR):
        return out

    for fname in sorted(os.listdir(BASELINE_DIR)):
        match = RE_BASELINE.match(fname)
        if not match or match.group("size") != REF_SIZE:
            continue
        workload = extract_workload(match.group("trace"))
        metrics = extract_metrics(os.path.join(BASELINE_DIR, fname))
        if metrics.instructions and metrics.instructions > 0 and metrics.llc_miss is not None:
            out[workload] = metrics.llc_miss / metrics.instructions * 1000.0
    return out


def reduction_pct(off_pages, on_pages):
    if off_pages <= 0:
        return None
    return (1.0 - on_pages / off_pages) * 100.0


def main():
    setup_style()
    sweep = load_sweep()
    baseline_llc_mpki = load_baseline_llc_mpki()

    all_wls = set()
    for wlmap in sweep.values():
        all_wls |= set(wlmap.keys())
    workloads = sorted(
        all_wls,
        key=lambda w: (-baseline_llc_mpki.get(w, -1.0), short_name(w))
    )

    summary_rows = []
    workload_rows = []
    mean_off = []
    mean_on = []
    reductions = []
    included_counts = []
    incomplete_counts = []

    for rate in RATES:
        off = sweep.get(("off", rate), {})
        on = sweep.get(("on", rate), {})
        included = []
        incomplete = 0

        for workload in workloads:
            off_rec = off.get(workload, {"pages": 0, "completed": False})
            on_rec = on.get(workload, {"pages": 0, "completed": False})
            use = off_rec["completed"] and on_rec["completed"]
            if not use:
                incomplete += 1

            row = {
                "rate": rate,
                "workload": workload,
                "short": short_name(workload),
                "baseline_llc_mpki": baseline_llc_mpki.get(workload, ""),
                "conventional_completed": off_rec["completed"],
                "llc_pinning_completed": on_rec["completed"],
                "included_in_plot": use,
                "conventional_migrated_pages": off_rec["pages"],
                "llc_pinning_migrated_pages": on_rec["pages"],
                "migration_reduction_pct": reduction_pct(
                    off_rec["pages"], on_rec["pages"]),
            }
            if rate == TARGET_RATE:
                workload_rows.append(row)
            if use:
                included.append((off_rec["pages"], on_rec["pages"]))

        off_vals = [v[0] for v in included]
        on_vals = [v[1] for v in included]
        off_mean = float(np.mean(off_vals)) if off_vals else 0.0
        on_mean = float(np.mean(on_vals)) if on_vals else 0.0
        red = reduction_pct(off_mean, on_mean)

        mean_off.append(off_mean)
        mean_on.append(on_mean)
        reductions.append(red)
        included_counts.append(len(included))
        incomplete_counts.append(incomplete)
        summary_rows.append({
            "rate": rate,
            "included_workloads": len(included),
            "incomplete_or_missing_workloads": incomplete,
            "mean_conventional_migrated_pages": off_mean,
            "mean_llc_pinning_migrated_pages": on_mean,
            "migration_reduction_pct": red,
        })

    pd.DataFrame(summary_rows).to_csv(OUTPUT_SUMMARY_CSV, index=False)
    pd.DataFrame(workload_rows).to_csv(OUTPUT_WORKLOAD_CSV, index=False)

    fig, ax = plt.subplots(figsize=(3.74, 1.975))

    x = np.arange(len(RATES), dtype=float)
    bar_w = 0.34
    ax.bar(
        x - bar_w / 2, mean_off, bar_w,
        color=COLOR_OFFLINE, edgecolor=EDGE, linewidth=0.45, zorder=3
    )
    ax.bar(
        x + bar_w / 2, mean_on, bar_w,
        color=COLOR_PIN, edgecolor=EDGE, linewidth=0.45, zorder=3
    )
    for x_pos, red in zip(x, reductions):
        if red is not None:
            pair_top = max(mean_off[int(x_pos)], mean_on[int(x_pos)], 1.0)
            ax.text(
                x_pos, pair_top * 1.35, f"{red:.1f}%",
                ha="center", va="bottom", fontsize=5.7,
                color="#222222"
            )
    first_pair_top = max(mean_off[0], mean_on[0], 1.0)
    ax.text(
        x[0], first_pair_top * 3.0, "Reduction",
        ha="center", va="bottom", fontsize=5.5, fontweight="bold",
        color="#222222", clip_on=False
    )
    ax.set_xticks(x)
    ax.set_xticklabels(["1", "10", "100", "1000"])
    ax.set_xlabel(r"CE Rate ($\times 10^{5}$ errors/hour)")
    ax.set_ylabel("Migrated pages")
    ax.set_yscale("symlog", linthresh=1.0, linscale=0.45)

    y_max = max(
        max(mean_off) if mean_off else 0,
        max(mean_on) if mean_on else 0,
        1,
    ) * 3.0
    ax.set_ylim(0, y_max)
    ax.yaxis.grid(True, linestyle=":", linewidth=0.5, alpha=0.6, which="both")
    ax.set_axisbelow(True)
    ax.tick_params(axis="both", which="both", length=2, pad=1)
    for spine in ax.spines.values():
        spine.set_visible(True)
        spine.set_linewidth(0.7)
        spine.set_color("black")

    legend = ax.legend(
        handles=[
            Patch(facecolor=COLOR_OFFLINE, edgecolor=EDGE, linewidth=0.45,
                  label="Conventional Page Offline"),
            Patch(facecolor=COLOR_PIN, edgecolor=EDGE, linewidth=0.45,
                  label="LLC Pinning"),
        ],
        loc="upper left", bbox_to_anchor=(0.018, 0.982),
        ncol=2, frameon=True, fancybox=False, framealpha=1.0,
        facecolor="white", edgecolor="black",
        handlelength=1.7, handletextpad=0.8, handleheight=0.92,
        borderpad=0.48, labelspacing=0.45, columnspacing=1.65
    )
    legend.get_frame().set_linewidth(0.55)

    fig.subplots_adjust(left=0.13, right=0.995, bottom=0.25, top=0.93)
    plt.savefig(OUTPUT_PNG, dpi=400,
                facecolor="white", edgecolor="none")
    plt.savefig(OUTPUT_PDF,
                facecolor="white", edgecolor="none")
    plt.close()

    print("Rate    included  conventional  pinning  reduction")
    for row in summary_rows:
        red = row["migration_reduction_pct"]
        red_s = f"{red:.1f}%" if red is not None else "N/A"
        print(f"{row['rate']:>6}  {row['included_workloads']:>8}  "
              f"{row['mean_conventional_migrated_pages']:>12.1f}  "
              f"{row['mean_llc_pinning_migrated_pages']:>7.1f}  {red_s:>9}")
    print(f"Summary CSV: {OUTPUT_SUMMARY_CSV}")
    print(f"Workload CSV: {OUTPUT_WORKLOAD_CSV}")
    print(f"PNG: {OUTPUT_PNG}")
    print(f"PDF: {OUTPUT_PDF}")


if __name__ == "__main__":
    main()
