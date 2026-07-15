#!/usr/bin/env python3
"""
IPC and protected-line coverage by retirement threshold with LLC pinning enabled.

Source: results/normal_evaluation/2_retirement_threshold/
        retire_on_{threshold}_{rate}_<trace>.txt

Coverage metric:
    Used Slots / Total Known Error Addresses

Normalized IPC:
    per-workload IPC / 2MB no-error baseline IPC

This intentionally uses Used Slots instead of "Pinned in Error Way" because
older result files have a known reporting mismatch for that field.
"""

import math
import os
import re

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib import rcParams
from matplotlib.ticker import PercentFormatter

from common_normal import extract_metrics, extract_workload, gmean

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
BASE_DIR = os.path.dirname(SCRIPT_DIR)
DATA_DIR = os.path.join(BASE_DIR, "results", "normal_evaluation",
                        "2_retirement_threshold")
BASELINE_DIR = os.path.join(BASE_DIR, "results", "normal_evaluation",
                            "4_llc_size_baseline")

OUTPUT_SUMMARY_CSV = os.path.join(
    SCRIPT_DIR, "fig7d_retirement_threshold_protected_lines.csv")
OUTPUT_WORKLOAD_CSV = os.path.join(
    SCRIPT_DIR, "fig7d_retirement_threshold_protected_lines_workloads.csv")
OUTPUT_PNG = os.path.join(
    SCRIPT_DIR, "fig7d_retirement_threshold_protected_lines.png")
OUTPUT_PDF = os.path.join(
    SCRIPT_DIR, "fig7d_retirement_threshold_protected_lines.pdf")

RE_FNAME = re.compile(
    r"^retire_on_(?P<thr>\d+)_(?P<rate>1e-\d+)_(?P<trace>.+)\.txt$"
)
RE_COMPLETE = re.compile(r"Simulation complete")
RE_IPC = re.compile(r"CPU 0 cumulative IPC:\s+([\d.]+)\s+instructions:")
RE_USED_SLOTS = re.compile(r"Used Slots:\s+(\d+)\s+\(([\d.]+)%\)")
RE_KNOWN = re.compile(r"Total Known Error Addresses:\s+(\d+)")
RE_PINNED = re.compile(r"Pinned in Error Way:\s+(\d+)\s+\(([\d.]+)%\)")
RE_BASELINE = re.compile(r"^llc_baseline_(?P<size>\d+MB)_(?P<trace>.+)\.txt$")

THRESHOLDS = [4, 8, 16, 32]
RATES = ["1e-5", "1e-6", "1e-7", "1e-8"]
PLOT_RATES = ["1e-8"]
REF_SIZE = "2MB"

COLOR_HARSH = "#f08d39"
COLOR_MARKER = "#F3BE7A"
EDGE = "black"
RATE_STYLE = {
    "1e-8": {
        "bar_color": COLOR_HARSH,
        "marker_color": COLOR_MARKER,
        "marker": "o",
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


def parse_result(path):
    with open(path, "r", errors="replace") as f:
        txt = f.read()

    used_match = RE_USED_SLOTS.search(txt)
    known_match = RE_KNOWN.search(txt)
    pinned_match = RE_PINNED.search(txt)
    completed = bool(RE_COMPLETE.search(txt))

    used_slots = int(used_match.group(1)) if used_match else None
    known_addrs = int(known_match.group(1)) if known_match else None
    pinned_count = int(pinned_match.group(1)) if pinned_match else None
    ipc_matches = RE_IPC.findall(txt)
    ipc = float(ipc_matches[-1]) if ipc_matches else 0.0

    coverage = math.nan
    if completed and used_slots is not None and known_addrs and known_addrs > 0:
        coverage = used_slots / known_addrs

    return {
        "completed": completed,
        "used_slots": used_slots,
        "known_error_addresses": known_addrs,
        "pinned_in_error_way_reported": pinned_count,
        "ipc": ipc,
        "protected_line_ratio_used_over_known": coverage,
        "included_in_protected_mean": not math.isnan(coverage),
    }


def load_data():
    rows = []
    if not os.path.isdir(DATA_DIR):
        raise SystemExit(f"Data dir not found: {DATA_DIR}")

    for fname in sorted(os.listdir(DATA_DIR)):
        match = RE_FNAME.match(fname)
        if not match:
            continue

        threshold = int(match.group("thr"))
        rate = match.group("rate")
        if threshold not in THRESHOLDS or rate not in RATES:
            continue

        rec = parse_result(os.path.join(DATA_DIR, fname))
        rec.update({
            "threshold": threshold,
            "rate": rate,
            "trace": match.group("trace"),
            "workload": extract_workload(match.group("trace")),
        })
        rows.append(rec)

    return pd.DataFrame(rows)


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
        baseline[workload] = metrics.ipc or 0.0

    return baseline


def main():
    setup_style()
    df = load_data()
    if df.empty:
        raise SystemExit("No retire_on threshold results loaded.")
    baseline = load_baseline_ipc()

    df["baseline_ipc_2MB_no_error"] = df["workload"].map(baseline).fillna(0.0)
    df["norm_ipc"] = np.where(
        (df["completed"])
        & (df["ipc"] > 0.0)
        & (df["baseline_ipc_2MB_no_error"] > 0.0),
        df["ipc"] / df["baseline_ipc_2MB_no_error"],
        np.nan,
    )
    df["protected_line_pct_used_over_known"] = (
        df["protected_line_ratio_used_over_known"] * 100.0
    )
    df["included_in_ipc_gmean"] = ~df["norm_ipc"].isna()

    summary_rows = []
    ipc_means = {rate: [] for rate in RATES}
    protected_means = {rate: [] for rate in RATES}
    counts = {rate: [] for rate in RATES}
    ipc_counts = {rate: [] for rate in RATES}

    for rate in RATES:
        for threshold in THRESHOLDS:
            sub = df[
                (df["rate"] == rate)
                & (df["threshold"] == threshold)
            ]
            protected_vals = sub[
                sub["included_in_protected_mean"]
            ]["protected_line_ratio_used_over_known"].tolist()
            ipc_vals = sub[
                sub["included_in_ipc_gmean"]
            ]["norm_ipc"].tolist()

            protected_avg = float(np.mean(protected_vals)) if protected_vals else math.nan
            ipc_avg = gmean(ipc_vals) if ipc_vals else math.nan

            protected_means[rate].append(protected_avg)
            ipc_means[rate].append(ipc_avg)
            counts[rate].append(len(protected_vals))
            ipc_counts[rate].append(len(ipc_vals))
            summary_rows.append({
                "rate": rate,
                "threshold": threshold,
                "included_workloads_for_ipc": len(ipc_vals),
                "gmean_norm_ipc": ipc_avg,
                "included_workloads_for_protected_lines": len(protected_vals),
                "mean_protected_line_ratio_used_over_known": protected_avg,
                "mean_protected_line_pct_used_over_known":
                    protected_avg * 100.0 if not math.isnan(protected_avg) else math.nan,
            })

    summary_df = pd.DataFrame(summary_rows)
    workload_df = df.copy()
    summary_df.to_csv(OUTPUT_SUMMARY_CSV, index=False)
    workload_df.to_csv(OUTPUT_WORKLOAD_CSV, index=False)

    fig, ax_bar = plt.subplots(figsize=(3.74, 1.975))
    ax_marker = ax_bar.twinx()
    x_vals = np.arange(len(THRESHOLDS), dtype=float)
    bar_w = 0.42
    offsets = {
        rate: (idx - (len(PLOT_RATES) - 1) / 2) * bar_w
        for idx, rate in enumerate(PLOT_RATES)
    }

    for rate in PLOT_RATES:
        style = RATE_STYLE[rate]
        xs = x_vals + offsets[rate]
        ax_bar.bar(
            xs, ipc_means[rate], width=bar_w,
            color=style["bar_color"], edgecolor=EDGE, linewidth=0.55,
            alpha=0.9, zorder=3
        )
        ax_marker.plot(
            xs, protected_means[rate],
            color=style["marker_color"], linewidth=0, linestyle="none",
            marker=style["marker"], markersize=6.5,
            markerfacecolor=style["marker_color"],
            markeredgecolor=EDGE, markeredgewidth=0.8,
            zorder=5
        )

    ax_bar.set_xticks(x_vals)
    ax_bar.set_xticklabels([str(t) for t in THRESHOLDS])
    ax_bar.set_xlim(x_vals[0] - 0.58, x_vals[-1] + 0.58)
    ax_bar.set_xlabel("Page Offline Threshold", labelpad=1.5)

    ax_bar.set_ylim(0.0, 1.08)
    ax_bar.set_ylabel("Normalized IPC (bars)", labelpad=3)
    ax_bar.yaxis.grid(True, linestyle=":", linewidth=0.5, alpha=0.6)
    ax_bar.set_axisbelow(True)

    ax_marker.set_ylim(0.85, 1.005)
    ax_marker.set_ylabel("Protected Lines (markers)", labelpad=3)
    ax_marker.yaxis.set_major_formatter(PercentFormatter(xmax=1.0, decimals=0))
    ax_marker.grid(False)

    for ax in (ax_bar, ax_marker):
        for spine in ax.spines.values():
            spine.set_visible(True)
            spine.set_linewidth(0.7)
            spine.set_color("black")

    fig.subplots_adjust(left=0.17, right=0.78, bottom=0.24, top=0.94)
    plt.savefig(OUTPUT_PNG, dpi=400,
                facecolor="white", edgecolor="none")
    plt.savefig(OUTPUT_PDF,
                facecolor="white", edgecolor="none")
    plt.close()

    print(f"{'thr':>4}  " + "  ".join(f"{rate + ' IPC':>12}" for rate in PLOT_RATES)
          + "  " + "  ".join(f"{rate + ' prot':>14}" for rate in PLOT_RATES))
    for idx, threshold in enumerate(THRESHOLDS):
        cells = []
        for rate in PLOT_RATES:
            val = ipc_means[rate][idx]
            cells.append("nan".rjust(12) if math.isnan(val)
                         else f"{val:12.4f}")
        for rate in PLOT_RATES:
            val = protected_means[rate][idx]
            n = counts[rate][idx]
            cells.append("nan".rjust(14) if math.isnan(val)
                         else f"{val * 100:8.2f}% n={n}".rjust(14))
        print(f"{threshold:>4}  " + "  ".join(cells))
    print(f"Summary CSV: {OUTPUT_SUMMARY_CSV}")
    print(f"Workload CSV: {OUTPUT_WORKLOAD_CSV}")
    print(f"PNG: {OUTPUT_PNG}")
    print(f"PDF: {OUTPUT_PDF}")


if __name__ == "__main__":
    main()
