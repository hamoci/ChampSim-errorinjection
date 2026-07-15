#!/usr/bin/env python3
"""
Fig 9: LLC Pinning vs Conventional Page offline.

Source: raw_data.xlsx
  - sheet "Way sweep in No error" (llc_size=2MB, llc_ways=16) — no-error baseline
  - sheet "Threshold sweep"       (pin_mode=on,  threshold=32) — LLC Pinning
                                  (pin_mode=off, threshold=2)  — Page Offline

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

from common_normal import load_xlsx_sheet, gmean, suite_of

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

OUTPUT_CSV = os.path.join(SCRIPT_DIR, "fig9_pinning_vs_offline.csv")
OUTPUT_PNG = os.path.join(SCRIPT_DIR, "fig9_pinning_vs_offline.png")
OUTPUT_PDF = os.path.join(SCRIPT_DIR, "fig9_pinning_vs_offline.pdf")

REF_SIZE = "2MB"
BASELINE_WAYS = 16
RATES = ["1e-5", "1e-6", "1e-7", "1e-8"]
TARGET_RATE = "1e-8"
LLC_PINNING_THRESHOLD = 32
OFFLINE_THRESHOLD = 2
PIN_MODES = ["off", "on"]
SUITES = ["SPEC", "GAP"]
# method = hue (blue pinning / orange offline); suite = lightness (SPEC dark,
# GAP light). Paired shades read cleaner than hatch.
BAR_COLOR = {
    ("off", "SPEC"): "#E5487E", ("off", "GAP"): "#F4A6C2",
    ("on", "SPEC"): "#2E6FDB", ("on", "GAP"): "#9FBEF0",
}
MTBCE_LABEL = {
    "1e-5": "1",
    "1e-6": "10",
    "1e-7": "100",
    "1e-8": "1000",
}

COLOR_PIN = "#0072B2"
COLOR_OFFLINE = "#D55E00"
EDGE = "black"


def short_name(workload: str) -> str:
    match = re.match(r"^\d+\.([A-Za-z0-9]+?)(?:_s)?$", workload)
    return match.group(1) if match else workload


def load_no_error_baseline():
    df = load_xlsx_sheet("Way sweep in No error")
    df = df[(df["llc_size"] == REF_SIZE) & (df["llc_ways"] == BASELINE_WAYS)]
    ipc = {}
    llc_mpki = {}
    for _, r in df.iterrows():
        wl = r["workload"]
        ipc[wl] = float(r["ipc"]) if pd.notna(r["ipc"]) else 0.0
        if pd.notna(r["llc_mpki"]):
            llc_mpki[wl] = float(r["llc_mpki"])
    return ipc, llc_mpki


def load_sweep():
    df = load_xlsx_sheet("Threshold sweep")
    out = {}
    pin_df = df[(df["pin_mode"] == "on")
                & (df["retirement_threshold"] == LLC_PINNING_THRESHOLD)
                & (df["error_rate"].isin(RATES))]
    for _, r in pin_df.iterrows():
        out.setdefault(("on", r["error_rate"]), {})[r["workload"]] = (
            float(r["ipc"]) if pd.notna(r["ipc"]) else 0.0
        )

    off_df = df[(df["pin_mode"] == "off")
                & (df["retirement_threshold"] == OFFLINE_THRESHOLD)
                & (df["error_rate"].isin(RATES))]
    for _, r in off_df.iterrows():
        out.setdefault(("off", r["error_rate"]), {})[r["workload"]] = (
            float(r["ipc"]) if pd.notna(r["ipc"]) else 0.0
        )
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

    # SPEC group then GAP group, each by descending no-error LLC MPKI.
    workloads = sorted(
        baseline.keys(),
        key=lambda w: (SUITES.index(suite_of(w)),
                       -baseline_llc_mpki.get(w, -1.0), short_name(w))
    )
    n_spec = sum(1 for w in workloads if suite_of(w) == "SPEC")
    wls_by_suite = {s: [w for w in workloads if suite_of(w) == s] for s in SUITES}

    # Per-workload normalized IPC. A panicked run is recorded as IPC 0 (it is
    # counted in the geomean, collapsing it); completed runs are normalized to
    # the no-error 2MB baseline.
    rows = []
    norm = {(pin, rate): {} for pin in PIN_MODES for rate in RATES}
    for rate in RATES:
        for wl in workloads:
            ref_ipc = baseline.get(wl, 0.0)
            for pin in PIN_MODES:
                ipc = sweep[(pin, rate)].get(wl, 0.0)
                norm[(pin, rate)][wl] = ipc / ref_ipc if ref_ipc > 0 else 0.0
            rows.append({
                "suite": suite_of(wl),
                "rate": rate,
                "mtbce": MTBCE_LABEL[rate],
                "workload": wl,
                "short": short_name(wl),
                "baseline_llc_mpki": baseline_llc_mpki.get(wl, ""),
                "baseline_ipc_no_error_2mb": ref_ipc,
                "conventional_page_offline_ipc": sweep[("off", rate)].get(wl, 0.0),
                "llc_pinning_ipc": sweep[("on", rate)].get(wl, 0.0),
                "norm_conventional_page_offline": norm[("off", rate)][wl],
                "norm_llc_pinning": norm[("on", rate)][wl],
            })

    # GMEAN per (suite, pin, rate), zeros (panics) included.
    gm = {}
    for rate in RATES:
        for pin in PIN_MODES:
            for s in SUITES:
                gm[(s, pin, rate)] = gmean(
                    [norm[(pin, rate)][w] for w in wls_by_suite[s]],
                    include_zeros=True)
        for s in SUITES:
            rows.append({
                "suite": s, "rate": rate, "mtbce": MTBCE_LABEL[rate],
                "workload": f"{s}_GMEAN", "short": "gmean",
                "baseline_llc_mpki": "", "baseline_ipc_no_error_2mb": "",
                "conventional_page_offline_ipc": "", "llc_pinning_ipc": "",
                "norm_conventional_page_offline": gm[(s, "off", rate)],
                "norm_llc_pinning": gm[(s, "on", rate)],
            })
    pd.DataFrame(rows).to_csv(OUTPUT_CSV, index=False)

    fig, (ax_left, ax_right) = plt.subplots(
        1, 2, figsize=(7.48, 2.05), sharey=True,
        gridspec_kw={"width_ratios": [1.15, 1.9], "wspace": 0.18}
    )

    # ---- Left: GMEAN per rate, 4 bars (SPEC off/on, GAP off/on) ----
    rate_x = np.arange(len(RATES), dtype=float)
    # method-major order: both Offline bars first, then both Pinning bars, so
    # warm (offline) and cool (pinning) colors are grouped, not interleaved.
    combos = [(s, pin) for pin in PIN_MODES for s in SUITES]
    bw = 0.19
    for i, (s, pin) in enumerate(combos):
        offset = (i - (len(combos) - 1) / 2) * bw
        ys = [gm[(s, pin, rate)] for rate in RATES]
        ax_left.bar(
            rate_x + offset, ys, bw,
            color=BAR_COLOR[(pin, s)],
            edgecolor=EDGE, linewidth=0.4, zorder=3,
        )
    ax_left.axhline(1.0, color="gray", linestyle=":", linewidth=0.7, zorder=1)
    ax_left.set_xticks(rate_x)
    ax_left.set_xticklabels([MTBCE_LABEL[rate] for rate in RATES])
    ax_left.set_xlabel(r"CE Rate ($\times 10^{5}$ errors/hour)", labelpad=1.5)
    ax_left.set_ylabel("Normalized IPC")
    ax_left.set_xlim(rate_x[0] - 0.55, rate_x[-1] + 0.55)

    # ---- Right: per-workload at TARGET_RATE + per-suite GMEAN ----
    target_labels = ([short_name(w) for w in workloads]
                     + [f"{s} GM" for s in SUITES])
    target_x = np.arange(len(target_labels), dtype=float)
    target_off = ([norm[("off", TARGET_RATE)][w] for w in workloads]
                  + [gm[(s, "off", TARGET_RATE)] for s in SUITES])
    target_on = ([norm[("on", TARGET_RATE)][w] for w in workloads]
                 + [gm[(s, "on", TARGET_RATE)] for s in SUITES])
    target_bar_w = 0.40

    gm_start = float(len(workloads))
    ax_right.axvspan(gm_start - 0.5, target_x[-1] + 0.5, color="#eef2f8",
                     zorder=0, linewidth=0)
    ax_right.axvline(gm_start - 0.5, color="#666666", linestyle="--",
                     linewidth=0.65, alpha=0.75, zorder=1)
    if 0 < n_spec < len(workloads):
        ax_right.axvline(n_spec - 0.5, color="#b0b0b0", linestyle="--",
                         linewidth=0.5, zorder=1)
    pos_suite = [suite_of(w) for w in workloads] + SUITES
    off_colors = [BAR_COLOR[("off", s)] for s in pos_suite]
    on_colors = [BAR_COLOR[("on", s)] for s in pos_suite]
    ax_right.bar(target_x - target_bar_w / 2, target_off, target_bar_w,
                 color=off_colors, edgecolor=EDGE, linewidth=0.4, zorder=3)
    ax_right.bar(target_x + target_bar_w / 2, target_on, target_bar_w,
                 color=on_colors, edgecolor=EDGE, linewidth=0.4, zorder=3)
    ax_right.axhline(1.0, color="gray", linestyle=":", linewidth=0.7, zorder=1)
    ax_right.set_xticks(target_x)
    ax_right.set_xticklabels(target_labels, rotation=40, ha="right",
                             rotation_mode="anchor")
    for tick in ax_right.get_xticklabels():
        if tick.get_text().endswith("GM"):
            tick.set_fontweight("bold")
    ax_right.tick_params(axis="x", labelsize=5.4)
    ax_right.set_xlabel("")
    ax_right.set_ylabel("Normalized IPC")
    ax_right.tick_params(axis="y", labelleft=True)
    ax_right.set_xlim(target_x[0] - 0.55, target_x[-1] + 0.55)

    y_top = max(
        max((max(norm[(p, r)].values()) for p in PIN_MODES for r in RATES)),
        max(gm.values()),
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
            Patch(facecolor=BAR_COLOR[("off", "SPEC")], edgecolor=EDGE,
                  linewidth=0.45, label="Page Offline (SPEC)"),
            Patch(facecolor=BAR_COLOR[("off", "GAP")], edgecolor=EDGE,
                  linewidth=0.45, label="Page Offline (GAP)"),
            Patch(facecolor=BAR_COLOR[("on", "SPEC")], edgecolor=EDGE,
                  linewidth=0.45, label="LLC Pinning (SPEC)"),
            Patch(facecolor=BAR_COLOR[("on", "GAP")], edgecolor=EDGE,
                  linewidth=0.45, label="LLC Pinning (GAP)"),
        ],
        loc="upper center",
        bbox_to_anchor=(0.5, 1.03), ncol=4, frameon=True,
        fancybox=False, framealpha=1.0, facecolor="white",
        edgecolor="black", handlelength=1.4, columnspacing=1.0,
        handletextpad=0.4, fontsize=6.2,
    )
    legend.get_frame().set_linewidth(0.55)
    fig.subplots_adjust(left=0.065, right=0.977, bottom=0.30, top=0.84,
                        wspace=0.18)
    fig.text(0.30, 0.005, "(a) Geomean IPC", ha="center", va="baseline",
             fontsize=rcParams["axes.titlesize"])
    fig.text(0.74, 0.005,
             r"(b) IPC at CE Rate = $10^{8}$ errors/hour",
             ha="center", va="baseline", fontsize=rcParams["axes.titlesize"])
    plt.savefig(OUTPUT_PNG, dpi=400, bbox_inches="tight",
                facecolor="white", edgecolor="none")
    plt.savefig(OUTPUT_PDF, bbox_inches="tight",
                facecolor="white", edgecolor="none")
    plt.close()

    n_gap = len(workloads) - n_spec
    print(f"Workloads: {len(workloads)} (SPEC={n_spec}, GAP={n_gap})")
    for s in SUITES:
        print(f"\n-- {s} --")
        print("Rate    offline  pinning  gain")
        for rate in RATES:
            g_off = gm[(s, "off", rate)]
            g_on = gm[(s, "on", rate)]
            gain_pct = (g_on / g_off - 1.0) * 100 if g_off > 0 else float("inf")
            gtxt = f"{gain_pct:+6.1f}%" if g_off > 0 else "   inf"
            print(f"{rate:>6}  {g_off:7.4f}  {g_on:7.4f}  {gtxt}")
    print(f"CSV: {OUTPUT_CSV}")
    print(f"PNG: {OUTPUT_PNG}")
    print(f"PDF: {OUTPUT_PDF}")


if __name__ == "__main__":
    main()
