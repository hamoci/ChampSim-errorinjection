#!/usr/bin/env python3
"""
Retirement threshold comparison with LLC pinning enabled/disabled.

Source: results/normal_evaluation/2_retirement_threshold/
        retire_{on,off}_{threshold}_{rate}_<trace>.txt

The plot compares LLC pinning off/on at the same retirement threshold under
the harshest CE injection rate. Normalized IPC uses the 2MB no-error baseline.
The CSV outputs retain the full rate/threshold/workload sweep.
"""

import os
import re

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib import rcParams
from matplotlib.patches import Patch

from common_normal import extract_metrics, extract_workload, gmean

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
BASE_DIR = os.path.dirname(SCRIPT_DIR)
DATA_DIR = os.path.join(BASE_DIR, "results", "normal_evaluation",
                        "2_retirement_threshold")
BASELINE_DIR = os.path.join(BASE_DIR, "results", "normal_evaluation",
                            "4_llc_size_baseline")

OUTPUT_SUMMARY_CSV = os.path.join(
    SCRIPT_DIR, "fig7b_retirement_threshold_pinning_comparison_summary.csv")
OUTPUT_WORKLOAD_CSV = os.path.join(
    SCRIPT_DIR, "fig7b_retirement_threshold_pinning_comparison_workloads.csv")
OUTPUT_PNG = os.path.join(
    SCRIPT_DIR, "fig7b_retirement_threshold_pinning_comparison.png")
OUTPUT_PDF = os.path.join(
    SCRIPT_DIR, "fig7b_retirement_threshold_pinning_comparison.pdf")

RE_FNAME = re.compile(
    r"^retire_(?P<mode>on|off)_(?P<thr>\d+)_(?P<rate>1e-\d+)_(?P<trace>.+)\.txt$"
)
RE_BASELINE = re.compile(r"^llc_baseline_(?P<size>\d+MB)_(?P<trace>.+)\.txt$")
RE_IPC = re.compile(r"CPU 0 cumulative IPC:\s+([\d.]+)\s+instructions:")
RE_PIN_OFF_RETIRED = re.compile(r"Baseline Page Retirements:\s+(\d+)")
RE_PIN_ON_RETIRED = re.compile(r"Pages Retired:\s+(\d+)")

REF_SIZE = "2MB"
RATES = ["1e-5", "1e-6", "1e-7", "1e-8"]
REQUESTED_THRESHOLDS = [2, 4, 8, 16, 32]
TARGET_RATE = "1e-8"

COLOR_OFF = "#f08d39"
COLOR_ON = "#5e7ac4"
EDGE = "black"


def setup_style():
    rcParams.update({
        "font.family": "sans-serif",
        "font.sans-serif": ["Helvetica", "Arial", "DejaVu Sans"],
        "font.size": 7,
        "axes.linewidth": 0.7,
        "axes.labelsize": 7.5,
        "axes.titlesize": 7.5,
        "xtick.labelsize": 6.4,
        "ytick.labelsize": 6.4,
        "legend.fontsize": 6.8,
        "pdf.fonttype": 42,
        "ps.fonttype": 42,
    })


def short_name(workload: str) -> str:
    match = re.match(r"^\d+\.([A-Za-z0-9]+?)(?:_s)?$", workload)
    return match.group(1) if match else workload


def parse_threshold_run(path, mode):
    try:
        with open(path, "r") as f:
            txt = f.read()
    except Exception:
        return {"ipc": 0.0, "completed": False, "retired_pages": 0}

    ipc_matches = RE_IPC.findall(txt)
    ipc = float(ipc_matches[-1]) if ipc_matches else 0.0
    completed = len(ipc_matches) > 0

    if mode == "off":
        retired_matches = RE_PIN_OFF_RETIRED.findall(txt)
    else:
        retired_matches = RE_PIN_ON_RETIRED.findall(txt)
    retired = int(retired_matches[-1]) if retired_matches else 0

    return {"ipc": ipc, "completed": completed, "retired_pages": retired}


def load_threshold_sweep():
    data = {}
    if not os.path.isdir(DATA_DIR):
        raise SystemExit(f"Data dir not found: {DATA_DIR}")

    for fname in sorted(os.listdir(DATA_DIR)):
        match = RE_FNAME.match(fname)
        if not match:
            continue
        mode = match.group("mode")
        threshold = int(match.group("thr"))
        rate = match.group("rate")
        workload = extract_workload(match.group("trace"))
        rec = parse_threshold_run(os.path.join(DATA_DIR, fname), mode)
        data.setdefault((mode, threshold, rate), {})[workload] = rec
    return data


def load_baseline_ipc():
    baseline = {}
    if not os.path.isdir(BASELINE_DIR):
        raise SystemExit(f"Baseline dir not found: {BASELINE_DIR}")

    for fname in sorted(os.listdir(BASELINE_DIR)):
        match = RE_BASELINE.match(fname)
        if not match or match.group("size") != REF_SIZE:
            continue
        metrics = extract_metrics(os.path.join(BASELINE_DIR, fname))
        workload = extract_workload(match.group("trace"))
        baseline[workload] = metrics.ipc if metrics.ipc is not None else 0.0
    return baseline


def norm_ipc(record, baseline_ipc):
    if not record or baseline_ipc <= 0:
        return 0.0
    return record["ipc"] / baseline_ipc if record["ipc"] > 0 else 0.0


def main():
    setup_style()
    data = load_threshold_sweep()
    baseline = load_baseline_ipc()

    all_workloads = set(baseline.keys())
    for wlmap in data.values():
        all_workloads |= set(wlmap.keys())
    workloads = sorted(all_workloads, key=short_name)

    summary_rows = []
    workload_rows = []
    summary = {}

    for rate in RATES:
        for threshold in REQUESTED_THRESHOLDS:
            off = data.get(("off", threshold, rate), {})
            on = data.get(("on", threshold, rate), {})
            off_vals = []
            on_vals = []
            off_pages = []
            on_pages = []
            included = 0

            for workload in workloads:
                base_ipc = baseline.get(workload, 0.0)
                off_rec = off.get(workload)
                on_rec = on.get(workload)
                off_norm = norm_ipc(off_rec, base_ipc)
                on_norm = norm_ipc(on_rec, base_ipc)
                use = (
                    base_ipc > 0
                    and off_rec is not None and on_rec is not None
                    and off_rec["completed"] and on_rec["completed"]
                    and off_norm > 0 and on_norm > 0
                )

                if use:
                    off_vals.append(off_norm)
                    on_vals.append(on_norm)
                    off_pages.append(off_rec["retired_pages"])
                    on_pages.append(on_rec["retired_pages"])
                    included += 1

                workload_rows.append({
                    "rate": rate,
                    "threshold": threshold,
                    "workload": workload,
                    "short": short_name(workload),
                    "baseline_ipc_2MB_no_error": base_ipc,
                    "pinning_off_ipc": off_rec["ipc"] if off_rec else "",
                    "pinning_on_ipc": on_rec["ipc"] if on_rec else "",
                    "pinning_off_completed": off_rec["completed"] if off_rec else False,
                    "pinning_on_completed": on_rec["completed"] if on_rec else False,
                    "pinning_off_norm_ipc": off_norm,
                    "pinning_on_norm_ipc": on_norm,
                    "pinning_off_retired_pages": off_rec["retired_pages"] if off_rec else "",
                    "pinning_on_retired_pages": on_rec["retired_pages"] if on_rec else "",
                    "included_in_gmean": use,
                })

            g_off = gmean(off_vals)
            g_on = gmean(on_vals)
            ratio = (g_on / g_off) if g_off > 0 else 0.0
            row = {
                "rate": rate,
                "threshold": threshold,
                "included_workloads": included,
                "pinning_off_gmean_norm_ipc": g_off,
                "pinning_on_gmean_norm_ipc": g_on,
                "pinning_on_vs_off_ratio": ratio,
                "mean_pinning_off_retired_pages": float(np.mean(off_pages)) if off_pages else 0.0,
                "mean_pinning_on_retired_pages": float(np.mean(on_pages)) if on_pages else 0.0,
            }
            summary_rows.append(row)
            summary[(threshold, rate)] = row

    pd.DataFrame(summary_rows).to_csv(OUTPUT_SUMMARY_CSV, index=False)
    pd.DataFrame(workload_rows).to_csv(OUTPUT_WORKLOAD_CSV, index=False)

    plot_thresholds = [
        t for t in REQUESTED_THRESHOLDS
        if summary.get((t, TARGET_RATE), {}).get("included_workloads", 0) > 0
    ]
    if not plot_thresholds:
        raise SystemExit(f"No paired pinning on/off data for {TARGET_RATE}")

    off_plot = [
        summary[(t, TARGET_RATE)]["pinning_off_gmean_norm_ipc"]
        for t in plot_thresholds
    ]
    on_plot = [
        summary[(t, TARGET_RATE)]["pinning_on_gmean_norm_ipc"]
        for t in plot_thresholds
    ]

    fig, ax = plt.subplots(figsize=(3.74, 1.975))
    x = np.arange(len(plot_thresholds), dtype=float)
    bar_w = 0.34

    ax.bar(
        x - bar_w / 2, off_plot, bar_w,
        color=COLOR_OFF, edgecolor=EDGE, linewidth=0.45,
        label="LLC Pinning Off", zorder=3
    )
    ax.bar(
        x + bar_w / 2, on_plot, bar_w,
        color=COLOR_ON, edgecolor=EDGE, linewidth=0.45,
        label="LLC Pinning On", zorder=3
    )

    ax.axhline(1.0, color="gray", linestyle=":", linewidth=0.7, zorder=1)
    ax.text(
        x[-1] + 0.48, 1.01, TARGET_RATE,
        ha="right", va="bottom", fontsize=6.2, color="#333333"
    )

    ax.set_xticks(x)
    ax.set_xticklabels([str(t) for t in plot_thresholds])
    ax.set_xlabel("Retirement Threshold")
    ax.set_ylabel("Normalized IPC")
    ax.set_ylim(0.0, max(1.08, max(off_plot + on_plot) * 1.08))
    ax.yaxis.grid(True, linestyle=":", linewidth=0.5, alpha=0.6)
    ax.set_axisbelow(True)
    ax.tick_params(axis="both", which="both", length=2, pad=1)

    legend = ax.legend(
        loc="upper left", ncol=2, frameon=True, fancybox=False,
        framealpha=1.0, facecolor="white", edgecolor="black",
        handlelength=1.6, handletextpad=0.7, borderpad=0.38,
        columnspacing=1.2
    )
    legend.get_frame().set_linewidth(0.55)

    for spine in ax.spines.values():
        spine.set_visible(True)
        spine.set_linewidth(0.7)
        spine.set_color("black")

    fig.subplots_adjust(left=0.14, right=0.995, bottom=0.24, top=0.96)
    plt.savefig(OUTPUT_PNG, dpi=400,
                facecolor="white", edgecolor="none")
    plt.savefig(OUTPUT_PDF,
                facecolor="white", edgecolor="none")
    plt.close()

    print(f"Target rate: {TARGET_RATE}")
    print(f"{'thr':>4}  {'n':>2}  {'off':>7}  {'on':>7}  {'on/off':>7}")
    for threshold in plot_thresholds:
        row = summary[(threshold, TARGET_RATE)]
        print(f"{threshold:>4}  {row['included_workloads']:>2}  "
              f"{row['pinning_off_gmean_norm_ipc']:>7.4f}  "
              f"{row['pinning_on_gmean_norm_ipc']:>7.4f}  "
              f"{row['pinning_on_vs_off_ratio']:>7.4f}")
    print(f"Summary CSV: {OUTPUT_SUMMARY_CSV}")
    print(f"Workload CSV: {OUTPUT_WORKLOAD_CSV}")
    print(f"PNG: {OUTPUT_PNG}")
    print(f"PDF: {OUTPUT_PDF}")


if __name__ == "__main__":
    main()
