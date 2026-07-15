#!/usr/bin/env python3
"""
Main result: LLC Pinning vs Conventional Page offline.

Source:
  - results/normal_evaluation/4_llc_size_baseline/
      llc_baseline_2MB_<trace>.txt
  - results/normal_evaluation/1_error_rate_sweep/
      pin_on_{rate}_<trace>.txt
  - results/normal_evaluation/2_retirement_threshold/
      retire_off_2_{rate}_<trace>.txt   (offline baseline, threshold=2)

Plot:
  Left:  GMEAN normalized IPC across the MTBCE sweep.
  Right: Per-workload normalized IPC at MTBCE = 1e-8, plus GMEAN.
Normalization: per-workload IPC normalized to the matching no-error 2MB LLC
baseline. Workloads are ordered by descending no-error baseline LLC MPKI.
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
BASELINE_DIR = os.path.join(BASE_DIR, "results", "normal_evaluation",
                            "4_llc_size_baseline")
SWEEP_DIR = os.path.join(BASE_DIR, "results", "normal_evaluation",
                         "1_error_rate_sweep")
OFFLINE_DIR = os.path.join(BASE_DIR, "results", "normal_evaluation",
                           "2_retirement_threshold")

OUTPUT_CSV = os.path.join(SCRIPT_DIR, "fig6_pinning_vs_offline.csv")
OUTPUT_PNG = os.path.join(SCRIPT_DIR, "fig6_pinning_vs_offline.png")
OUTPUT_PDF = os.path.join(SCRIPT_DIR, "fig6_pinning_vs_offline.pdf")

RE_BASELINE = re.compile(r"^llc_baseline_(?P<size>\d+MB)_(?P<trace>.+)\.txt$")
RE_PIN_ON = re.compile(r"^pin_on_(?P<rate>1e-\d+)_(?P<trace>.+)\.txt$")
RE_OFFLINE = re.compile(r"^retire_off_2_(?P<rate>1e-\d+)_(?P<trace>.+)\.txt$")

REF_SIZE = "2MB"
RATES = ["1e-5", "1e-6", "1e-7", "1e-8"]
TARGET_RATE = "1e-8"
MTBCE_LABEL = {
    "1e-5": "1",
    "1e-6": "10",
    "1e-7": "100",
    "1e-8": "1000",
}

COLOR_PIN = "#5e7ac4"       # muted blue
COLOR_OFFLINE = "#f08d39"   # orange
EDGE = "black"


def short_name(workload: str) -> str:
    match = re.match(r"^\d+\.([A-Za-z0-9]+?)(?:_s)?$", workload)
    return match.group(1) if match else workload


def load_no_error_baseline():
    ipc = {}
    llc_mpki = {}
    if not os.path.isdir(BASELINE_DIR):
        raise SystemExit(f"Baseline dir not found: {BASELINE_DIR}")

    for fname in sorted(os.listdir(BASELINE_DIR)):
        match = RE_BASELINE.match(fname)
        if not match or match.group("size") != REF_SIZE:
            continue
        metrics = extract_metrics(os.path.join(BASELINE_DIR, fname))
        workload = extract_workload(match.group("trace"))
        ipc[workload] = metrics.ipc if metrics.ipc is not None else 0.0
        if metrics.instructions and metrics.instructions > 0 and metrics.llc_miss is not None:
            llc_mpki[workload] = metrics.llc_miss / metrics.instructions * 1000.0

    return ipc, llc_mpki


def load_sweep():
    out = {}
    if not os.path.isdir(SWEEP_DIR):
        raise SystemExit(f"Sweep dir not found: {SWEEP_DIR}")
    if not os.path.isdir(OFFLINE_DIR):
        raise SystemExit(f"Offline dir not found: {OFFLINE_DIR}")

    for fname in sorted(os.listdir(SWEEP_DIR)):
        match = RE_PIN_ON.match(fname)
        if not match or match.group("rate") not in RATES:
            continue
        metrics = extract_metrics(os.path.join(SWEEP_DIR, fname))
        workload = extract_workload(match.group("trace"))
        key = ("on", match.group("rate"))
        out.setdefault(key, {})[workload] = metrics.ipc if metrics.ipc is not None else 0.0

    for fname in sorted(os.listdir(OFFLINE_DIR)):
        match = RE_OFFLINE.match(fname)
        if not match or match.group("rate") not in RATES:
            continue
        metrics = extract_metrics(os.path.join(OFFLINE_DIR, fname))
        workload = extract_workload(match.group("trace"))
        key = ("off", match.group("rate"))
        out.setdefault(key, {})[workload] = metrics.ipc if metrics.ipc is not None else 0.0

    return out


def setup_style():
    rcParams.update({
        "font.family": "sans-serif",
        "font.sans-serif": ["Helvetica", "Arial", "DejaVu Sans"],
        "font.size": 7,
        "axes.linewidth": 0.7,
        "axes.labelsize": 7.5,
        "axes.titlesize": 7.5,
        "xtick.labelsize": 5.4,
        "ytick.labelsize": 6.2,
        "legend.fontsize": 6.8,
        "pdf.fonttype": 42,
        "ps.fonttype": 42,
    })


def main():
    setup_style()
    baseline, baseline_llc_mpki = load_no_error_baseline()
    sweep = load_sweep()

    if not baseline:
        raise SystemExit(f"No no-error baseline data found for {REF_SIZE}")
    for rate in RATES:
        if ("on", rate) not in sweep or ("off", rate) not in sweep:
            raise SystemExit(f"Missing pin_on or pin_off data at {rate}")

    workloads = sorted(
        baseline.keys(),
        key=lambda w: (-baseline_llc_mpki.get(w, -1.0), short_name(w))
    )
    rows = []
    norm_off = {}
    norm_on = {}
    gmean_off = {}
    gmean_on = {}

    for rate in RATES:
        norm_off[rate] = []
        norm_on[rate] = []
        for workload in workloads:
            ref_ipc = baseline.get(workload, 0.0)
            off_ipc = sweep[("off", rate)].get(workload, 0.0)
            on_ipc = sweep[("on", rate)].get(workload, 0.0)
            n_off = off_ipc / ref_ipc if ref_ipc > 0 else 0.0
            n_on = on_ipc / ref_ipc if ref_ipc > 0 else 0.0
            norm_off[rate].append(n_off)
            norm_on[rate].append(n_on)
            rows.append({
                "rate": rate,
                "mtbce": MTBCE_LABEL[rate],
                "workload": workload,
                "short": short_name(workload),
                "baseline_llc_mpki": baseline_llc_mpki.get(workload, ""),
                "baseline_ipc_no_error_2mb": ref_ipc,
                "conventional_page_offline_ipc": off_ipc,
                "llc_pinning_ipc": on_ipc,
                "norm_conventional_page_offline": n_off,
                "norm_llc_pinning": n_on,
            })

        gmean_off[rate] = gmean(norm_off[rate])
        gmean_on[rate] = gmean(norm_on[rate])
        rows.append({
            "rate": rate,
            "mtbce": MTBCE_LABEL[rate],
            "workload": "GMEAN",
            "short": "gmean",
            "baseline_llc_mpki": "",
            "baseline_ipc_no_error_2mb": "",
            "conventional_page_offline_ipc": "",
            "llc_pinning_ipc": "",
            "norm_conventional_page_offline": gmean_off[rate],
            "norm_llc_pinning": gmean_on[rate],
        })
    pd.DataFrame(rows).to_csv(OUTPUT_CSV, index=False)

    fig, (ax_left, ax_right) = plt.subplots(
        1, 2, figsize=(7.48, 1.975), sharey=True,
        gridspec_kw={"width_ratios": [1.0, 1.65], "wspace": 0.20}
    )

    # Left: GMEAN across MTBCE.
    rate_x = np.arange(len(RATES), dtype=float)
    gmean_bar_w = 0.34
    gmean_off_vals = [gmean_off[rate] for rate in RATES]
    gmean_on_vals = [gmean_on[rate] for rate in RATES]
    ax_left.bar(
        rate_x - gmean_bar_w / 2,
        gmean_off_vals,
        gmean_bar_w, color=COLOR_OFFLINE, edgecolor=EDGE,
        linewidth=0.45, zorder=3
    )
    ax_left.bar(
        rate_x + gmean_bar_w / 2,
        gmean_on_vals,
        gmean_bar_w, color=COLOR_PIN, edgecolor=EDGE,
        linewidth=0.45, zorder=3
    )
    ax_left.axhline(1.0, color="gray", linestyle=":", linewidth=0.7, zorder=1)
    ax_left.set_title("(a) Geomean IPC across CE Injection Rates", pad=3)
    ax_left.set_xticks(rate_x)
    ax_left.set_xticklabels([MTBCE_LABEL[rate] for rate in RATES])
    ax_left.set_xlabel(r"CE Rate ($\times 10^{5}$ errors/hour)", labelpad=1.5)
    ax_left.set_ylabel("Normalized IPC")
    ax_left.set_xlim(rate_x[0] - 0.55, rate_x[-1] + 0.55)

    # Right: per-workload behavior at the harshest point.
    target_labels = [short_name(w) for w in workloads] + ["GMEAN"]
    target_x = np.arange(len(target_labels), dtype=float)
    target_off = norm_off[TARGET_RATE] + [gmean_off[TARGET_RATE]]
    target_on = norm_on[TARGET_RATE] + [gmean_on[TARGET_RATE]]
    target_bar_w = 0.34
    gmean_x = float(len(workloads))

    ax_right.axvspan(gmean_x - 0.5, gmean_x + 0.5, color="#eef2f8",
                     zorder=0, linewidth=0)
    ax_right.axvline(gmean_x - 0.5, color="#666666", linestyle="--",
                     linewidth=0.65, alpha=0.75, zorder=1)
    ax_right.bar(
        target_x - target_bar_w / 2, target_off, target_bar_w,
        color=COLOR_OFFLINE, edgecolor=EDGE, linewidth=0.45,
        zorder=3
    )
    ax_right.bar(
        target_x + target_bar_w / 2, target_on, target_bar_w,
        color=COLOR_PIN, edgecolor=EDGE, linewidth=0.45,
        zorder=3
    )
    ax_right.axhline(1.0, color="gray", linestyle=":", linewidth=0.7, zorder=1)
    ax_right.set_title(f"(b) Per-workload IPC at worst-case CE Injection Rate", pad=3)
    ax_right.set_xticks(target_x)
    ax_right.set_xticklabels(target_labels, rotation=32, ha="right",
                             rotation_mode="anchor")
    for tick in ax_right.get_xticklabels():
        if tick.get_text() == "GMEAN":
            tick.set_fontweight("bold")
    ax_right.set_xlabel("")
    ax_right.set_ylabel("Normalized IPC")
    ax_right.tick_params(axis="y", labelleft=True)
    ax_right.set_xlim(target_x[0] - 0.55, target_x[-1] + 0.55)

    y_top = max(
        max(max(norm_on[rate]) for rate in RATES),
        max(max(norm_off[rate]) for rate in RATES),
        max(gmean_on.values()),
        max(gmean_off.values()),
        1.0,
    ) * 1.06
    for ax in (ax_left, ax_right):
        ax.set_ylim(0.0, y_top)
        ax.yaxis.grid(True, linestyle=":", linewidth=0.5, alpha=0.6)
        ax.set_axisbelow(True)
        ax.tick_params(axis="both", which="both", length=2, pad=1)
        for spine in ax.spines.values():
            spine.set_visible(True)
            spine.set_linewidth(0.7)
            spine.set_color("black")

    legend = fig.legend(
        handles=[
            Patch(facecolor=COLOR_OFFLINE, edgecolor=EDGE, linewidth=0.45,
                  label="Conventional Page Offline"),
            Patch(facecolor=COLOR_PIN, edgecolor=EDGE, linewidth=0.45,
                  label="LLC Pinning"),
        ],
        loc="upper center",
        bbox_to_anchor=(0.5, 0.959), ncol=2, frameon=True,
        fancybox=False, framealpha=1.0, facecolor="white",
        edgecolor="black", handlelength=1.7, columnspacing=1.5
    )
    legend.get_frame().set_linewidth(0.55)
    fig.subplots_adjust(left=0.065, right=0.977, bottom=0.209, top=0.769,
                        wspace=0.20)
    plt.savefig(OUTPUT_PNG, dpi=400,
                facecolor="white", edgecolor="none")
    plt.savefig(OUTPUT_PDF,
                facecolor="white", edgecolor="none")
    plt.close()

    print(f"Workloads: {len(workloads)}")
    print("Rate    offline  pinning  gain")
    for rate in RATES:
        g_off = gmean_off[rate]
        g_on = gmean_on[rate]
        gain_pct = (g_on / g_off - 1.0) * 100 if g_off > 0 else 0.0
        print(f"{rate:>6}  {g_off:7.4f}  {g_on:7.4f}  {gain_pct:+6.1f}%")
    print(f"CSV: {OUTPUT_CSV}")
    print(f"PNG: {OUTPUT_PNG}")
    print(f"PDF: {OUTPUT_PDF}")


if __name__ == "__main__":
    main()
