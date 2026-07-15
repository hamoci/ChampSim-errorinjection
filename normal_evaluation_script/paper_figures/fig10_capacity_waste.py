#!/usr/bin/env python3
"""
Fig 10: DRAM capacity waste from page offlining, across MTBCE sweep.

Source: raw_data.xlsx, sheet "Threshold sweep"
  - pin_mode = on,  threshold = 32 (LLC Pinning baseline)
  - pin_mode = off, threshold = 2  (Conventional Page Offline)
Output: single-panel line chart, mean migrated pages vs MTBCE.
"""

import os

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib import rcParams
from matplotlib.ticker import NullLocator, FixedLocator

from common_normal import load_xlsx_sheet, suite_of

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

OUTPUT_CSV = os.path.join(SCRIPT_DIR, "fig10_capacity_waste.csv")
OUTPUT_PNG = os.path.join(SCRIPT_DIR, "fig10_capacity_waste.png")
OUTPUT_PDF = os.path.join(SCRIPT_DIR, "fig10_capacity_waste.pdf")

RATES = ["1e-5", "1e-6", "1e-7", "1e-8"]
LLC_PINNING_THRESHOLD = 32
OFFLINE_THRESHOLD = 2
PAGE_SIZE_BYTES = 2 * 1024 * 1024
PIN_MODES = ["off", "on"]
SUITES = ["SPEC", "GAP"]
# method = hue (blue pinning / orange offline); suite = lightness (SPEC dark,
# GAP light).
BAR_COLOR = {
    ("off", "SPEC"): "#E5487E", ("off", "GAP"): "#F4A6C2",
    ("on", "SPEC"): "#2E6FDB", ("on", "GAP"): "#9FBEF0",
}

COLOR_PIN = "#2E6FDB"
COLOR_OFFLINE = "#E5487E"


def load_sweep():
    df = load_xlsx_sheet("Threshold sweep")
    out = {}

    pin_df = df[(df["pin_mode"] == "on")
                & (df["retirement_threshold"] == LLC_PINNING_THRESHOLD)]
    for _, r in pin_df.iterrows():
        rate = r["error_rate"]
        if rate not in RATES:
            continue
        completed = pd.notna(r["ipc"])
        retired = int(r["pages_retired"]) if pd.notna(r["pages_retired"]) else 0
        out.setdefault(("on", rate), {})[r["workload"]] = (retired, completed)

    off_df = df[(df["pin_mode"] == "off")
                & (df["retirement_threshold"] == OFFLINE_THRESHOLD)]
    for _, r in off_df.iterrows():
        rate = r["error_rate"]
        if rate not in RATES:
            continue
        completed = pd.notna(r["ipc"])
        retired = int(r["pages_retired"]) if pd.notna(r["pages_retired"]) else 0
        out.setdefault(("off", rate), {})[r["workload"]] = (retired, completed)

    return out


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
    sweep = load_sweep()
    page_mb = PAGE_SIZE_BYTES / (1024 * 1024)

    all_wls = set()
    for wlmap in sweep.values():
        all_wls |= set(wlmap.keys())
    wls_by_suite = {s: sorted(w for w in all_wls if suite_of(w) == s)
                    for s in SUITES}

    # Mean migrated pages per series, over the workloads where THAT series
    # completed (panicked runs excluded — their page stats would be garbage).
    # Each series is independent, so e.g. GAP pinning at 1e-8 still shows even
    # though GAP page-offline panicked for every workload at that rate.
    rows = []
    # pages[(suite, pin)] = list over RATES
    pages = {(s, pin): [] for s in SUITES for pin in PIN_MODES}
    counts = {(s, pin): [] for s in SUITES for pin in PIN_MODES}
    sweep_by_pin = {"off": None, "on": None}
    for r in RATES:
        sweep_by_pin["off"] = sweep.get(("off", r), {})
        sweep_by_pin["on"] = sweep.get(("on", r), {})
        for s in SUITES:
            per_wl = {}
            for pin in PIN_MODES:
                done = [w for w in wls_by_suite[s]
                        if sweep_by_pin[pin].get(w, (0, False))[1]]
                counts[(s, pin)].append(len(done))
                pages[(s, pin)].append(
                    float(np.mean([sweep_by_pin[pin][w][0] for w in done]))
                    if done else np.nan)
                for w in done:
                    per_wl.setdefault(w, {})[pin] = sweep_by_pin[pin][w][0]
            for w in wls_by_suite[s]:
                if w in per_wl:
                    rows.append({
                        "suite": s, "rate": r, "workload": w,
                        "pin_off_pages_retired": per_wl[w].get("off", np.nan),
                        "pin_on_pages_retired": per_wl[w].get("on", np.nan),
                    })

    pd.DataFrame(rows).to_csv(OUTPUT_CSV, index=False)

    fig, ax = plt.subplots(figsize=(3.74, 1.975))

    x_idx = np.arange(len(RATES), dtype=float)
    # method-major order: both Offline bars first, then both Pinning bars, so
    # warm (offline) and cool (pinning) colors are grouped, not interleaved.
    combos = [(s, pin) for pin in PIN_MODES for s in SUITES]
    bar_w = 0.2
    finite_max = 1.0
    for i, (s, pin) in enumerate(combos):
        offset = (i - (len(combos) - 1) / 2) * bar_w
        ys = np.array(pages[(s, pin)], dtype=float)
        ax.bar(
            x_idx + offset, ys, bar_w,
            color=BAR_COLOR[(pin, s)],
            edgecolor="black", linewidth=0.4, zorder=3,
        )
        good = ys[np.isfinite(ys)]
        if good.size:
            finite_max = max(finite_max, float(good.max()))

    ax.set_xticks(x_idx)
    ax.set_xticklabels(["1", "10", "100", "1000"])
    ax.set_xlim(x_idx[0] - 0.55, x_idx[-1] + 0.55)
    ax.set_xlabel(r"CE Rate ($\times 10^{5}$ errors/hour)")

    ax.set_yscale("symlog", linthresh=1.0, linscale=0.4)
    ax.set_ylim(0, finite_max * 12.0)
    ax.set_ylabel("Migrated pages")
    ax.yaxis.set_major_locator(FixedLocator([1, 10, 100, 1000, 10000, 100000]))
    ax.yaxis.set_minor_locator(NullLocator())
    ax.yaxis.grid(True, linestyle=":", linewidth=0.5, alpha=0.6,
                  which="both")
    ax.set_axisbelow(True)

    from matplotlib.patches import Patch
    handles = [
        Patch(facecolor=BAR_COLOR[("off", "SPEC")], edgecolor="black",
              linewidth=0.4, label="Offline (SPEC)"),
        Patch(facecolor=BAR_COLOR[("off", "GAP")], edgecolor="black",
              linewidth=0.4, label="Offline (GAP)"),
        Patch(facecolor=BAR_COLOR[("on", "SPEC")], edgecolor="black",
              linewidth=0.4, label="Pinning (SPEC)"),
        Patch(facecolor=BAR_COLOR[("on", "GAP")], edgecolor="black",
              linewidth=0.4, label="Pinning (GAP)"),
    ]
    leg = ax.legend(handles=handles, loc="upper center",
                    bbox_to_anchor=(0.5, 1.26), ncol=2, handlelength=1.1,
                    handletextpad=0.4, columnspacing=0.9, borderpad=0.3,
                    borderaxespad=0.0, frameon=True, fancybox=False,
                    framealpha=1.0, fontsize=6.0)
    leg.get_frame().set_facecolor("white")
    leg.get_frame().set_edgecolor("black")
    leg.get_frame().set_linewidth(0.4)

    for spine in ax.spines.values():
        spine.set_visible(True)
        spine.set_linewidth(0.7)
        spine.set_color("black")

    plt.tight_layout(pad=0.3)
    plt.savefig(OUTPUT_PNG, dpi=400, bbox_inches="tight",
                facecolor="white", edgecolor="none")
    plt.savefig(OUTPUT_PDF, bbox_inches="tight",
                facecolor="white", edgecolor="none")
    plt.close()

    print(f"Page size: {page_mb:.1f} MB")
    for s in SUITES:
        print(f"\n-- {s} --")
        print(f"{'Rate':>6}  {'Off(pg)':>11}  {'On(pg)':>10}  "
              f"{'Reduce%':>8}  {'n_off':>5} {'n_on':>5}")
        for i, r in enumerate(RATES):
            a = pages[(s, "off")][i]
            b = pages[(s, "on")][i]
            red = (f"{(1 - b/a) * 100:.1f}%"
                   if np.isfinite(a) and np.isfinite(b) and a > 0 else "—")
            af = f"{a:.2f}" if np.isfinite(a) else "panic"
            bf = f"{b:.2f}" if np.isfinite(b) else "panic"
            print(f"{r:>6}  {af:>11}  {bf:>10}  {red:>8}  "
                  f"{counts[(s, 'off')][i]:>5} {counts[(s, 'on')][i]:>5}")
    print(f"CSV: {OUTPUT_CSV}")
    print(f"PNG: {OUTPUT_PNG}")
    print(f"PDF: {OUTPUT_PDF}")


if __name__ == "__main__":
    main()
