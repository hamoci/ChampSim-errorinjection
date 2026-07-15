#!/usr/bin/env python3
"""
Fig 14: Pinning ON (1/2/4/8-way) vs Pinning OFF (threshold=32) — protected lines.

Same plot as Fig 13 (2MB LLC, CE rate = 1e-8), with one extra coverage point
per workload (and GMEAN) drawn for the pinning-OFF baseline at retirement
threshold 32. Lets us compare: pinning + retirement vs retirement alone.

  Bars (left axis)     — Normalized IPC vs no-error baseline (pinning ON).
  Way markers (right)  — Protected Error Lines (%), from
                         Max error way sweep / protected_lines_pct
  Pin-OFF marker (red) — Protected Error Lines (%) for pinning OFF, from
                         Threshold sweep (off, threshold=32) / protected_lines_pct

Source: raw_data.xlsx
  - sheet "Max error way sweep"   (error_rate = 1e-8, max_error_way ∈ {1,2,4,8})
  - sheet "Way sweep in No error" (llc_size = 2MB, llc_ways = 16) — baseline
  - sheet "Threshold sweep"       (pin_mode = off, threshold = 32,
                                   error_rate = 1e-8)
Output: fig14_pinning_off_compare_2MB_1e-8.{csv,png,pdf}
"""

import os

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib import rcParams
from matplotlib.ticker import FormatStrFormatter, MultipleLocator
from matplotlib.patches import Patch
from matplotlib.lines import Line2D

from common_normal import load_xlsx_sheet, gmean, suite_of

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

OUTPUT_CSV = os.path.join(SCRIPT_DIR, "fig14_pinning_off_compare_2MB_1e-8.csv")
OUTPUT_PNG = os.path.join(SCRIPT_DIR, "fig14_pinning_off_compare_2MB_1e-8.png")
OUTPUT_PDF = os.path.join(SCRIPT_DIR, "fig14_pinning_off_compare_2MB_1e-8.pdf")

TARGET_SIZE = "2MB"
TARGET_RATE = "1e-8"
BASELINE_WAYS = 16
PIN_OFF_THRESH = 32
WAYS = [1, 2, 4, 8]
SUITES = ["SPEC", "GAP"]

WAY_COLOR = {
    1: "#c6dbef",
    2: "#6baed6",
    4: "#3182bd",
    8: "#08519c",
}
MARKER_COLOR = "#222222"
WAY_MARKER = {1: "o", 2: "s", 4: "^", 8: "D"}

PIN_OFF_COLOR = "#d62728"
PIN_OFF_MARKER = "*"


def short_workload_label(workload):
    label = workload.split(".", 1)[1] if "." in workload else workload
    return label[:-2] if label.endswith("_s") else label


def load_baseline_2mb():
    df = load_xlsx_sheet("Way sweep in No error")
    df = df[(df["llc_size"] == TARGET_SIZE) & (df["llc_ways"] == BASELINE_WAYS)]
    out = {}
    mpki = {}
    for _, r in df.iterrows():
        wl = r["workload"]
        out[wl] = float(r["ipc"]) if pd.notna(r["ipc"]) else 0.0
        if pd.notna(r["llc_mpki"]):
            mpki[wl] = float(r["llc_mpki"])
    return out, mpki


def load_pin_off_coverage():
    df = load_xlsx_sheet("Threshold sweep")
    df = df[(df["pin_mode"] == "off")
            & (df["retirement_threshold"] == PIN_OFF_THRESH)
            & (df["error_rate"] == TARGET_RATE)]
    out = {}
    for _, r in df.iterrows():
        if pd.notna(r["protected_lines_pct"]):
            out[r["workload"]] = float(r["protected_lines_pct"])
    return out


def setup_style():
    rcParams.update({
        "font.family": "sans-serif",
        "font.sans-serif": ["Helvetica", "Arial", "DejaVu Sans"],
        "font.size": 10,
        "axes.linewidth": 0.8,
        "axes.labelsize": 10.5,
        "axes.titlesize": 10.5,
        "xtick.labelsize": 10,
        "ytick.labelsize": 10,
        "legend.fontsize": 9,
        "pdf.fonttype": 42,
        "ps.fonttype": 42,
    })


def main():
    setup_style()
    sweep_df = load_xlsx_sheet("Max error way sweep")
    sweep_df = sweep_df[(sweep_df["error_rate"] == TARGET_RATE)
                        & (sweep_df["max_error_way"].isin(WAYS))]
    if sweep_df.empty:
        raise SystemExit(
            f"No sweep records found for rate={TARGET_RATE}, ways={WAYS}")
    baseline, baseline_llc_mpki = load_baseline_2mb()
    pin_off_cov = load_pin_off_coverage()

    data = {w: {} for w in WAYS}
    all_wls = set()
    for _, r in sweep_df.iterrows():
        way = int(r["max_error_way"])
        wl = r["workload"]
        data[way][wl] = r
        all_wls.add(wl)
    # SPEC group then GAP group, each ordered by descending no-error MPKI.
    workloads = sorted(
        all_wls,
        key=lambda w: (SUITES.index(suite_of(w)),
                       -baseline_llc_mpki.get(w, -1.0), short_workload_label(w))
    )
    n_spec = sum(1 for w in workloads if suite_of(w) == "SPEC")

    labels = ([short_workload_label(w) for w in workloads]
              + [f"{s} GMEAN" for s in SUITES])
    rows = []
    norm_by_way = {w: [] for w in WAYS}
    cov_by_way = {w: [] for w in WAYS}
    pin_off_cov_list = []
    gm_ipc = {w: {s: [] for s in SUITES} for w in WAYS}
    gm_cov = {w: {s: [] for s in SUITES} for w in WAYS}
    gm_pin_off = {s: [] for s in SUITES}

    for wl in workloads:
        suite = suite_of(wl)
        ref_ipc = baseline.get(wl, 0.0)
        for way in WAYS:
            r = data[way].get(wl)
            present = r is not None
            completed = present and bool(r["completed"])
            if present:
                raw_ipc = float(r["ipc"]) if pd.notna(r["ipc"]) else 0.0
                cov = (float(r["protected_lines_pct"])
                       if pd.notna(r["protected_lines_pct"]) else float("nan"))
            else:
                raw_ipc, cov = 0.0, float("nan")
            norm_ipc = (raw_ipc / ref_ipc) if (completed and ref_ipc > 0) else 0.0
            norm_by_way[way].append(norm_ipc)
            cov_by_way[way].append(cov)
            if present and (not completed or ref_ipc > 0):
                gm_ipc[way][suite].append(norm_ipc)
                if cov == cov:
                    gm_cov[way][suite].append(cov)
            rows.append({
                "suite": suite,
                "llc_size": TARGET_SIZE,
                "error_rate": TARGET_RATE,
                "workload": wl,
                "max_ways": way,
                "completed": completed,
                "ipc_pin_on": raw_ipc,
                "ref_ipc_no_error_same_workload_size": ref_ipc,
                "norm_ipc": norm_ipc,
                "protected_error_lines_pct": cov,
                "pin_off_protected_lines_pct": pin_off_cov.get(wl, float("nan")),
            })
        po = pin_off_cov.get(wl, float("nan"))
        pin_off_cov_list.append(po)
        if po == po:
            gm_pin_off[suite].append(po)

    for way in WAYS:
        for s in SUITES:
            ipc_gm = gmean(gm_ipc[way][s], include_zeros=True)
            cov_mean = (float(np.mean(gm_cov[way][s]))
                        if gm_cov[way][s] else float("nan"))
            norm_by_way[way].append(ipc_gm)
            cov_by_way[way].append(cov_mean)
            rows.append({
                "suite": s,
                "llc_size": TARGET_SIZE,
                "error_rate": TARGET_RATE,
                "workload": f"{s}_GMEAN",
                "max_ways": way,
                "completed": None,
                "ipc_pin_on": None,
                "ref_ipc_no_error_same_workload_size": None,
                "norm_ipc": ipc_gm,
                "protected_error_lines_pct": cov_mean,
                "pin_off_protected_lines_pct": None,
            })
    for s in SUITES:
        po_gm = (float(np.mean(gm_pin_off[s])) if gm_pin_off[s] else float("nan"))
        pin_off_cov_list.append(po_gm)
        rows.append({
            "suite": s,
            "llc_size": TARGET_SIZE,
            "error_rate": TARGET_RATE,
            "workload": f"{s}_GMEAN",
            "max_ways": "pin_off_thr32",
            "completed": None,
            "ipc_pin_on": None,
            "ref_ipc_no_error_same_workload_size": None,
            "norm_ipc": None,
            "protected_error_lines_pct": None,
            "pin_off_protected_lines_pct": po_gm,
        })

    pd.DataFrame(rows).to_csv(OUTPUT_CSV, index=False)

    fig, ax_bar = plt.subplots(figsize=(7.48, 2.05))
    ax_line = ax_bar.twinx()

    x_vals = np.arange(len(labels), dtype=float)
    bar_w = 0.17
    offsets = {w: (i - (len(WAYS) - 1) / 2) * bar_w
               for i, w in enumerate(WAYS)}

    for way in WAYS:
        xs = x_vals + offsets[way]
        ax_bar.bar(
            xs, norm_by_way[way], width=bar_w,
            color=WAY_COLOR[way], edgecolor="black", linewidth=0.45,
            zorder=2,
        )

    for wl_idx in range(len(labels)):
        wl_xs = []
        wl_ys = []
        for way in WAYS:
            xv = x_vals[wl_idx] + offsets[way]
            yv = cov_by_way[way][wl_idx]
            if yv == yv:
                wl_xs.append(xv)
                wl_ys.append(yv)
        if len(wl_xs) >= 2:
            ax_line.plot(
                wl_xs, wl_ys,
                linestyle=":", linewidth=0.9, color=MARKER_COLOR, alpha=0.75,
                zorder=4,
            )

    for way in WAYS:
        xs = x_vals + offsets[way]
        marker_ys = cov_by_way[way]
        valid = [(x, y) for x, y in zip(xs, marker_ys) if y == y]
        if valid:
            ax_line.plot(
                [x for x, _ in valid], [y for _, y in valid],
                linestyle="none", marker=WAY_MARKER[way], markersize=3.2,
                markerfacecolor=MARKER_COLOR,
                markeredgecolor="white", markeredgewidth=0.4,
                zorder=5,
            )

    pin_off_xs = []
    pin_off_ys = []
    for xv, yv in zip(x_vals, pin_off_cov_list):
        if yv == yv:
            pin_off_xs.append(xv)
            pin_off_ys.append(yv)
    if pin_off_xs:
        ax_line.plot(
            pin_off_xs, pin_off_ys,
            linestyle="none", marker=PIN_OFF_MARKER, markersize=6.0,
            markerfacecolor=PIN_OFF_COLOR,
            markeredgecolor="black", markeredgewidth=0.4,
            zorder=6,
        )

    all_ipc = [v for way in WAYS for v in norm_by_way[way] if v > 0]
    y_lo = max(0.0, min(all_ipc) - 0.02) if all_ipc else 0.0
    ax_bar.set_ylim(y_lo, 1.01)
    ax_bar.yaxis.set_major_locator(MultipleLocator(0.05))
    ax_bar.yaxis.set_major_formatter(FormatStrFormatter("%.2f"))
    ax_bar.yaxis.grid(True, linestyle=":", linewidth=0.45, alpha=0.45)
    ax_bar.set_axisbelow(True)
    ax_bar.set_ylabel("Normalized IPC", fontsize=8.8, labelpad=1.5)
    ax_bar.set_xticks(x_vals)
    ax_bar.set_xticklabels(labels, rotation=40, ha="right", rotation_mode="anchor")
    ax_bar.tick_params(axis="x", labelsize=6.0, pad=1.0, width=0.75)
    ax_bar.tick_params(axis="y", labelsize=8.2, pad=1.5, width=0.75)
    for tick in ax_bar.get_xticklabels():
        if tick.get_text().endswith("GMEAN"):
            tick.set_fontweight("bold")
    ax_bar.set_xlim(x_vals[0] - 0.55, x_vals[-1] + 0.55)

    # Divider before the GMEAN columns, and between SPEC and GAP workloads.
    ax_bar.axvline(len(workloads) - 0.5, color="#808080", linewidth=0.55,
                   linestyle=":", zorder=1)
    if 0 < n_spec < len(workloads):
        ax_bar.axvline(n_spec - 0.5, color="#b0b0b0", linewidth=0.5,
                       linestyle="--", zorder=1)

    ax_line.set_ylim(0, 102)
    ax_line.yaxis.set_major_formatter(FormatStrFormatter("%.0f"))
    ax_line.set_ylabel("Protected Lines (%)", fontsize=8.8, labelpad=1.5)
    ax_line.tick_params(axis="y", labelsize=8.2, pad=1.5, width=0.75)
    ax_line.grid(False)

    for ax in (ax_bar, ax_line):
        for spine in ax.spines.values():
            spine.set_linewidth(0.75)
            spine.set_color("black")

    bar_handles = [
        Patch(facecolor=WAY_COLOR[w], edgecolor="black", linewidth=0.45,
              label=f"{w}-way")
        for w in WAYS
    ]
    marker_handles = [
        Line2D([0], [0], linestyle="none", marker=WAY_MARKER[w],
               markersize=4.0, markerfacecolor=MARKER_COLOR,
               markeredgecolor="white", markeredgewidth=0.4,
               label=f"{w}-way")
        for w in WAYS
    ]
    pin_off_handle = Line2D(
        [0], [0], linestyle="none", marker=PIN_OFF_MARKER, markersize=6.0,
        markerfacecolor=PIN_OFF_COLOR, markeredgecolor="black",
        markeredgewidth=0.4, label="Conventional page offline",
    )
    interleaved = []
    for b, m in zip(bar_handles, marker_handles):
        interleaved.append(b)
        interleaved.append(m)
    interleaved.append(pin_off_handle)
    leg = fig.legend(
        handles=interleaved,
        loc="upper center", bbox_to_anchor=(0.5, 1.06),
        ncol=len(WAYS) + 1, handlelength=1.2, columnspacing=1.2,
        borderpad=0.35, handletextpad=0.4, labelspacing=0.45,
        frameon=True, fancybox=False, framealpha=1.0, fontsize=7.4,
    )
    leg.get_frame().set_facecolor("white")
    leg.get_frame().set_edgecolor("black")
    leg.get_frame().set_linewidth(0.45)

    plt.tight_layout(rect=(0, 0, 1, 0.88))
    plt.savefig(OUTPUT_PNG, dpi=400, bbox_inches="tight",
                facecolor="white", edgecolor="none")
    plt.savefig(OUTPUT_PDF, bbox_inches="tight",
                facecolor="white", edgecolor="none")
    plt.close()

    n_gap = len(workloads) - n_spec
    print(f"Workloads: {len(workloads)} (SPEC={n_spec}, GAP={n_gap})")
    print(f"-- LLC={TARGET_SIZE}  rate={TARGET_RATE} --")
    gm_idx = {s: len(workloads) + i for i, s in enumerate(SUITES)}
    print(f"{'ways':>5}  " + "  ".join(
        f"{s+' IPC':>10}  {s+' cov%':>10}" for s in SUITES))
    for w in WAYS:
        cells = [f"{norm_by_way[w][gm_idx[s]]:>10.4f}  "
                 f"{cov_by_way[w][gm_idx[s]]:>10.2f}" for s in SUITES]
        print(f"{w:>5}  " + "  ".join(cells))
    for s in SUITES:
        print(f"PinOFF (thr=32) {s} mean cov% = "
              f"{pin_off_cov_list[gm_idx[s]]:.2f}")
    print(f"\nCSV: {OUTPUT_CSV}")
    print(f"PNG: {OUTPUT_PNG}")
    print(f"PDF: {OUTPUT_PDF}")


if __name__ == "__main__":
    main()
