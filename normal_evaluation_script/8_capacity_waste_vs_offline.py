#!/usr/bin/env python3
"""
DRAM capacity waste from page offlining, across MTBCE sweep.

Source:
  - results/normal_evaluation/1_error_rate_sweep/pin_on_{rate}_<trace>.txt
  - results/normal_evaluation/2_retirement_threshold/retire_off_2_{rate}_<trace>.txt
    (Conventional Page Offline baseline, retirement threshold = 2)
Output: single-panel line chart, mean wasted DRAM capacity (MB) vs MTBCE.

Motivation: Conventional Page Offline retires every page after its 2nd correctable
error (threshold 2), so wasted capacity scales with error count. LLC Pinning
only retires a page after its inline PDE + EPT slots overflow (≥6 errors/page
by default, threshold 32 in these runs), so the same DRAM error stream wastes
far less capacity.

Per-workload metric: pages_retired * page_size. Panicked pin_off runs at the
harshest rate (IPC collapses before the error counter is flushed) are excluded
from both series to keep the comparison on the same workload set.
Style matches 6_pinning_vs_offline.py.
"""

import os
import re
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib import rcParams
from matplotlib.ticker import NullLocator

from common_normal import extract_workload

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
BASE_DIR = os.path.dirname(SCRIPT_DIR)
SWEEP_DIR = os.path.join(BASE_DIR, "results", "normal_evaluation", "1_error_rate_sweep")
OFFLINE_DIR = os.path.join(BASE_DIR, "results", "normal_evaluation", "2_retirement_threshold")

OUTPUT_CSV = os.path.join(SCRIPT_DIR, "fig8_capacity_waste.csv")
OUTPUT_PNG = os.path.join(SCRIPT_DIR, "fig8_capacity_waste.png")
OUTPUT_PDF = os.path.join(SCRIPT_DIR, "fig8_capacity_waste.pdf")

RE_PIN_ON = re.compile(r"^pin_on_(?P<rate>1e-\d+)_(?P<trace>.+)\.txt$")
RE_OFFLINE = re.compile(r"^retire_off_2_(?P<rate>1e-\d+)_(?P<trace>.+)\.txt$")
RE_IPC = re.compile(r"CPU 0 cumulative IPC:\s+([\d.]+)\s+instructions:")
RE_PAGE_SIZE = re.compile(r"Page size:\s+(\d+)")
RE_PIN_OFF_RETIRED = re.compile(r"Baseline Page Retirements:\s+(\d+)")
RE_PIN_ON_RETIRED = re.compile(r"Pages Retired:\s+(\d+)")

RATES = ["1e-5", "1e-6", "1e-7", "1e-8"]  # benign → harsh

# Style matches fig6.
COLOR_PIN = "#5e7ac4"
COLOR_OFFLINE = "#f3be7a"
COLOR_FILL = "#f3be7a"
COLOR_UPPER = "#606060"


def parse_run(path, mode):
    """Return (retired_pages, page_size, completed?) — completed means the ROI
    IPC line is present (the simulator did not panic out)."""
    try:
        with open(path, "r") as f:
            txt = f.read()
    except Exception:
        return None, None, False

    # Grab the last IPC line (ROI section prints cumulative IPC). Presence of a
    # numeric match means the run reached the ROI end and reported results.
    ipc_matches = RE_IPC.findall(txt)
    completed = len(ipc_matches) > 0

    ps_m = RE_PAGE_SIZE.search(txt)
    page_size = int(ps_m.group(1)) if ps_m else None

    if mode == "off":
        matches = RE_PIN_OFF_RETIRED.findall(txt)
    else:
        matches = RE_PIN_ON_RETIRED.findall(txt)
    retired = int(matches[-1]) if matches else 0

    return retired, page_size, completed


def load_sweep():
    # out[(mode, rate)] = {workload: (retired, page_size, completed)}
    out = {}
    page_size_seen = None
    if not os.path.isdir(SWEEP_DIR):
        raise SystemExit(f"Sweep dir not found: {SWEEP_DIR}")
    if not os.path.isdir(OFFLINE_DIR):
        raise SystemExit(f"Offline dir not found: {OFFLINE_DIR}")

    for fname in sorted(os.listdir(SWEEP_DIR)):
        m = RE_PIN_ON.match(fname)
        if not m:
            continue
        rate = m.group("rate")
        retired, page_size, completed = parse_run(
            os.path.join(SWEEP_DIR, fname), "on")
        if page_size and page_size_seen is None:
            page_size_seen = page_size
        wl = extract_workload(m.group("trace"))
        out.setdefault(("on", rate), {})[wl] = (retired, page_size, completed)

    for fname in sorted(os.listdir(OFFLINE_DIR)):
        m = RE_OFFLINE.match(fname)
        if not m:
            continue
        rate = m.group("rate")
        retired, page_size, completed = parse_run(
            os.path.join(OFFLINE_DIR, fname), "off")
        if page_size and page_size_seen is None:
            page_size_seen = page_size
        wl = extract_workload(m.group("trace"))
        out.setdefault(("off", rate), {})[wl] = (retired, page_size, completed)

    return out, page_size_seen


def setup_style():
    rcParams.update({
        "font.family": "sans-serif",
        "font.sans-serif": ["Helvetica", "Arial", "DejaVu Sans"],
        "font.size": 9,
        "axes.linewidth": 0.7,
        "axes.labelsize": 9,
        "axes.titlesize": 9,
        "xtick.labelsize": 8,
        "ytick.labelsize": 8,
        "legend.fontsize": 8,
        "pdf.fonttype": 42,
        "ps.fonttype": 42,
    })


def main():
    setup_style()
    sweep, page_size = load_sweep()
    if page_size is None:
        raise SystemExit("Could not determine page size from logs.")
    page_mb = page_size / (1024 * 1024)

    # Workload universe: any workload seen in any run.
    all_wls = set()
    for key, wlmap in sweep.items():
        all_wls |= set(wlmap.keys())
    all_wls = sorted(all_wls)

    rows = []
    waste_off_mb = []
    waste_on_mb = []
    panic_counts = []
    for r in RATES:
        off = sweep.get(("off", r), {})
        on = sweep.get(("on", r), {})

        # Only workloads that completed in BOTH modes — apples to apples.
        shared = [w for w in all_wls
                  if off.get(w, (0, 0, False))[2]
                  and on.get(w, (0, 0, False))[2]]
        panics = sum(1 for w in all_wls if not off.get(w, (0, 0, False))[2])

        off_vals = [off[w][0] for w in shared]
        on_vals = [on[w][0] for w in shared]
        for w in shared:
            rows.append({
                "rate": r,
                "workload": w,
                "pin_off_pages_retired": off[w][0],
                "pin_on_pages_retired": on[w][0],
                "pin_off_waste_MB": off[w][0] * page_mb,
                "pin_on_waste_MB": on[w][0] * page_mb,
            })

        mean_off = float(np.mean(off_vals)) if off_vals else 0.0
        mean_on = float(np.mean(on_vals)) if on_vals else 0.0
        waste_off_mb.append(mean_off * page_mb)
        waste_on_mb.append(mean_on * page_mb)
        panic_counts.append(panics)

    pd.DataFrame(rows).to_csv(OUTPUT_CSV, index=False)

    # ── Plot ──
    fig, ax = plt.subplots(figsize=(3.74, 1.975))

    x_vals = np.array([float(r) for r in RATES])

    # Use symlog so exact zero (no retirements at benign rates) is rendered
    # faithfully alongside 5-order-of-magnitude waste at the harsh rate.
    off_plot = np.array(waste_off_mb)
    on_plot = np.array(waste_on_mb)
    ax.fill_between(x_vals, on_plot, off_plot,
                    color=COLOR_FILL, alpha=0.18, linewidth=0, zorder=1)

    # Baseline: Conventional Page Offline (dashed amber, open square).
    ax.plot(x_vals, off_plot,
            color=COLOR_OFFLINE, linewidth=1.6, linestyle="--",
            marker="s", markersize=7, markerfacecolor="white",
            markeredgecolor=COLOR_OFFLINE, markeredgewidth=1.4,
            label="Conventional Page Offline", zorder=3)

    # Proposed: LLC Pinning (solid blue, filled circle).
    ax.plot(x_vals, on_plot,
            color=COLOR_PIN, linewidth=2.0, linestyle="-",
            marker="o", markersize=7, markerfacecolor=COLOR_PIN,
            markeredgecolor="black", markeredgewidth=0.5,
            label="LLC Pinning", zorder=4)

    # Reduction annotation at the rightmost (harsh) point.
    if off_plot[-1] > 0 and on_plot[-1] > 0:
        ratio = off_plot[-1] / on_plot[-1]
        x_a = x_vals[-1]
        y_hi = off_plot[-1]
        y_lo = on_plot[-1]
        y_mid = np.sqrt(y_hi * y_lo)  # geometric midpoint for symlog axis
        ax.annotate("",
                    xy=(x_a, y_hi), xytext=(x_a, y_lo),
                    arrowprops=dict(arrowstyle="<->", color="black",
                                    lw=0.8, shrinkA=3, shrinkB=3))
        ax.text(x_a * 1.6, y_mid,
                f"×{ratio:.0f}",
                fontsize=8.5, fontweight="bold", color="black",
                ha="left", va="center",
                bbox=dict(boxstyle="round,pad=0.25", facecolor="white",
                          edgecolor="black", linewidth=0.4))

    # X axis: log, benign (1e-5) left → harsh (1e-8) right.
    ax.set_xscale("log")
    ax.set_xlim(x_vals[0] * 2.2, x_vals[-1] * 0.45)
    ax.set_xticks(x_vals)
    ax.set_xticklabels(["1", "10", "100", "1000"])
    ax.xaxis.set_minor_locator(NullLocator())
    ax.set_xlabel(r"CE Rate ($\times 10^{5}$ errors/hour)")

    # Y axis: symlog so zero retirements render at y=0 while harsh rates can
    # still stretch across orders of magnitude. Linear region below 1 MB.
    ax.set_yscale("symlog", linthresh=1.0, linscale=0.4)
    y_max = max(off_plot.max(), on_plot.max()) * 1.8
    ax.set_ylim(0, y_max)
    ax.set_ylabel("Wasted capacity (MB)")
    ax.yaxis.grid(True, linestyle=":", linewidth=0.5, alpha=0.6, which="both")
    ax.xaxis.grid(True, linestyle=":", linewidth=0.4, alpha=0.4, which="major")
    ax.set_axisbelow(True)

    leg = ax.legend(loc="upper left", handlelength=2.5,
                    borderpad=0.4, frameon=True, fancybox=False,
                    framealpha=1.0)
    leg.get_frame().set_facecolor("white")
    leg.get_frame().set_edgecolor("black")
    leg.get_frame().set_linewidth(0.4)

    for spine in ax.spines.values():
        spine.set_visible(True)
        spine.set_linewidth(0.7)
        spine.set_color("black")

    plt.tight_layout(pad=0.3)
    plt.savefig(OUTPUT_PNG, dpi=400,
                facecolor="white", edgecolor="none")
    plt.savefig(OUTPUT_PDF,
                facecolor="white", edgecolor="none")
    plt.close()

    print(f"Page size: {page_mb:.1f} MB")
    print(f"{'Rate':>6}  {'Off(MB)':>10}  {'On(MB)':>10}  {'Ratio':>6}  panics")
    for r, a, b, p in zip(RATES, waste_off_mb, waste_on_mb, panic_counts):
        ratio = f"{a/b:.1f}x" if b > 0 else "—"
        print(f"{r:>6}  {a:>10.2f}  {b:>10.2f}  {ratio:>6}  {p}")
    print(f"CSV: {OUTPUT_CSV}")
    print(f"PNG: {OUTPUT_PNG}")
    print(f"PDF: {OUTPUT_PDF}")


if __name__ == "__main__":
    main()
