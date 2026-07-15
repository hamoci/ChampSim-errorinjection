#!/usr/bin/env python3
"""
Fig 12c: Absolute UE-vulnerable line count at page-offline threshold 256.

At threshold 256, page retirement essentially never fires, so all protection
comes from LLC pinning. The snapshot "protected %" saturates (~0 vs ~100), so
we report the *absolute number of UE-vulnerable cache lines* instead — faulty
(CE-bearing) lines still served from faulty DRAM, each one a latent UE under
SEC-DED if a second bit error lands.

  Pin ON  : UE-vulnerable = In Normal Way (unprotected) + Not in LLC (DRAM exposed)
  Pin OFF : UE-vulnerable = Live (still tracked)   [retired pages are remapped/safe]

Source: results/normal_evaluation/2_retirement_threshold/
        retire_{on,off}_256_1e-8_<trace>.txt
Output: fig12c_ue_vulnerable_lines_thr256.{csv,png,pdf}
"""

import os
import re

import numpy as np
import matplotlib.pyplot as plt
from matplotlib import rcParams
from matplotlib.patches import Patch

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CHAMPSIM_DIR = os.path.dirname(os.path.dirname(SCRIPT_DIR))
DATA_DIR = os.path.join(CHAMPSIM_DIR, "results", "normal_evaluation",
                        "2_retirement_threshold")

OUTPUT_CSV = os.path.join(SCRIPT_DIR, "fig12c_ue_vulnerable_lines_thr256.csv")
OUTPUT_PNG = os.path.join(SCRIPT_DIR, "fig12c_ue_vulnerable_lines_thr256.png")
OUTPUT_PDF = os.path.join(SCRIPT_DIR, "fig12c_ue_vulnerable_lines_thr256.pdf")

RATE = "1e-8"
THR = "256"
TRACES = [
    "602.gcc_s-1850B", "603.bwaves_s-2931B", "605.mcf_s-994B",
    "607.cactuBSSN_s-2421B", "620.omnetpp_s-141B", "621.wrf_s-6673B",
    "623.xalancbmk_s-592B", "628.pop2_s-17B", "649.fotonik3d_s-10881B",
    "654.roms_s-1007B",
]

RE_TOTAL_KNOWN = re.compile(r"Total Known Error Addresses:\s+(\d+)")
RE_NOT_IN_LLC = re.compile(r"Not in LLC \(DRAM exposed\):\s+(\d+)")
RE_IN_NORMAL = re.compile(r"In Normal Way \(unprotected\):\s+(\d+)")
RE_LIVE = re.compile(r"Live \(still tracked\):\s+(\d+)")
RE_COMPLETE = re.compile(r"Simulation complete")

COLOR_ON = "#2E6FDB"
COLOR_OFF = "#E5487E"
EDGE = "black"
FLOOR = 0.6  # log-scale placeholder height for a true 0


def setup_style():
    rcParams.update({
        "font.family": "sans-serif",
        "font.sans-serif": ["Helvetica", "Arial", "DejaVu Sans"],
        "font.size": 7, "axes.linewidth": 0.7,
        "axes.labelsize": 7.5, "xtick.labelsize": 6.6, "ytick.labelsize": 7,
        "legend.fontsize": 7, "pdf.fonttype": 42, "ps.fonttype": 42,
    })


def short(trace):
    m = re.match(r"^\d+\.([A-Za-z0-9]+)", trace)
    return m.group(1) if m else trace


def read(path):
    try:
        with open(path, "r", errors="replace") as f:
            return f.read()
    except OSError:
        return None


def exposed_counts(trace):
    on_txt = read(os.path.join(DATA_DIR, f"retire_on_{THR}_{RATE}_{trace}.txt"))
    off_txt = read(os.path.join(DATA_DIR, f"retire_off_{THR}_{RATE}_{trace}.txt"))
    on_exp = off_exp = None
    if on_txt and RE_COMPLETE.search(on_txt):
        nil = RE_NOT_IN_LLC.search(on_txt)
        nin = RE_IN_NORMAL.search(on_txt)
        if nil and nin:
            on_exp = int(nil.group(1)) + int(nin.group(1))
    if off_txt and RE_COMPLETE.search(off_txt):
        live = RE_LIVE.search(off_txt)
        if live:
            off_exp = int(live.group(1))
    return on_exp, off_exp


def main():
    setup_style()
    labels, on_vals, off_vals = [], [], []
    rows = [("workload", "pin_on_ue_lines", "pin_off_ue_lines", "reduction_x")]
    for tr in TRACES:
        on_exp, off_exp = exposed_counts(tr)
        if on_exp is None or off_exp is None:
            print(f"WARN: missing/incomplete data for {tr} "
                  f"(on={on_exp}, off={off_exp})")
            continue
        labels.append(short(tr))
        on_vals.append(on_exp)
        off_vals.append(off_exp)
        red = (off_exp / on_exp) if on_exp > 0 else float("inf")
        rows.append((short(tr), on_exp, off_exp,
                     f"{red:.0f}" if red != float("inf") else "inf"))

    on_sum, off_sum = sum(on_vals), sum(off_vals)
    rows.append(("TOTAL", on_sum, off_sum,
                 f"{off_sum/on_sum:.1f}" if on_sum > 0 else "inf"))

    with open(OUTPUT_CSV, "w") as f:
        for r in rows:
            f.write(",".join(str(x) for x in r) + "\n")

    # ---- figure: grouped bars, log y, per-workload + TOTAL ----
    plot_labels = labels + ["TOTAL"]
    on_plot = on_vals + [on_sum]
    off_plot = off_vals + [off_sum]

    fig, ax = plt.subplots(figsize=(7.0, 2.2))
    x = np.arange(len(plot_labels), dtype=float)
    bw = 0.38

    def heights(vals):
        return [v if v > 0 else FLOOR for v in vals]

    ax.bar(x - bw / 2, heights(off_plot), bw, color=COLOR_OFF, edgecolor=EDGE,
           linewidth=0.5, zorder=3, label="LLC Pinning OFF")
    ax.bar(x + bw / 2, heights(on_plot), bw, color=COLOR_ON, edgecolor=EDGE,
           linewidth=0.5, zorder=3, label="LLC Pinning ON")

    # annotate exact counts (esp. zeros) above pin-ON bars
    for xv, v in zip(x + bw / 2, on_plot):
        ax.text(xv, heights([v])[0] * 1.15, str(v), ha="center", va="bottom",
                fontsize=5.2, color=COLOR_ON, rotation=90)

    ax.axvline(len(labels) - 0.5, color="#888888", linewidth=0.6,
               linestyle=":", zorder=1)
    ax.set_yscale("log")
    ax.set_ylim(FLOOR, max(off_plot) * 3)
    ax.set_ylabel("UE-vulnerable lines\n(faulty data on DRAM)", labelpad=2)
    ax.set_xticks(x)
    ax.set_xticklabels(plot_labels, rotation=30, ha="right",
                       rotation_mode="anchor")
    ax.set_xlim(x[0] - 0.6, x[-1] + 0.6)
    ax.yaxis.grid(True, which="both", linestyle=":", linewidth=0.45, alpha=0.5)
    ax.set_axisbelow(True)
    for spine in ax.spines.values():
        spine.set_linewidth(0.7)
        spine.set_color("black")

    ax.set_title(f"Page Offline Threshold {THR}  (CE rate {RATE})",
                 fontsize=8, pad=3)
    ax.legend(loc="upper right", ncol=2, frameon=True, fancybox=False,
              framealpha=1.0, facecolor="white", edgecolor="black",
              handlelength=1.3, handletextpad=0.5, borderpad=0.35,
              columnspacing=1.0).get_frame().set_linewidth(0.5)

    fig.subplots_adjust(left=0.11, right=0.99, bottom=0.24, top=0.88)
    plt.savefig(OUTPUT_PNG, dpi=400, bbox_inches="tight",
                facecolor="white", edgecolor="none")
    plt.savefig(OUTPUT_PDF, bbox_inches="tight",
                facecolor="white", edgecolor="none")
    plt.close()

    print(f"\n{'workload':>12} {'pin ON':>8} {'pin OFF':>8} {'reduction':>10}")
    for r in rows[1:]:
        print(f"{r[0]:>12} {str(r[1]):>8} {str(r[2]):>8} {str(r[3])+'x':>10}")
    print(f"\nCSV: {OUTPUT_CSV}\nPNG: {OUTPUT_PNG}\nPDF: {OUTPUT_PDF}")


if __name__ == "__main__":
    main()
