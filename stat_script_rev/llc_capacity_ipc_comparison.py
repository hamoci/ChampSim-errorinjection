#!/usr/bin/env python3
"""LLC capacity (2/4/8MB) IPC comparison split by suite (SPEC/GAP)."""

import os
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

from common_real_final import load_records, extract_ipc

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
OUT_CSV = os.path.join(SCRIPT_DIR, "llc_capacity_ipc_comparison.csv")
OUT_PNG = os.path.join(SCRIPT_DIR, "llc_capacity_ipc_comparison.png")

LLC_SIZES = [2, 4, 8]
PAGES = ["4kb", "2mb"]
PINNING = [False, True]
ERROR_RATES = ["1e-6", "1e-7", "1e-8", "1e-9"]
SUITES = ["SPEC", "GAP"]


def gmean(values):
    vals = [v for v in values if v and v > 0]
    if not vals:
        return None
    return float(np.exp(np.mean(np.log(vals))))


def main():
    recs = [r for r in load_records() if (r.error_rate in ERROR_RATES or r.error_rate is None) and r.llc_mb in LLC_SIZES]

    # Collect workload-level IPC (error runs)
    bucket = {}
    baseline_bucket = {s: {p: [] for p in PAGES} for s in SUITES}
    for r in recs:
        if r.suite not in SUITES:
            continue
        ipc = extract_ipc(r.path)
        if ipc is None:
            continue
        if r.error_rate is None and r.page in PAGES:
            baseline_bucket[r.suite][r.page].append(ipc)
            continue
        key = (r.suite, r.llc_mb, r.page, r.pinning, r.error_rate)
        bucket.setdefault(key, []).append(ipc)

    # Build summary table (GMEAN over workloads)
    rows = []
    for suite in SUITES:
        for llc in LLC_SIZES:
            for page in PAGES:
                for pin in PINNING:
                    for er in ERROR_RATES:
                        key = (suite, llc, page, pin, er)
                        rows.append({
                            "Suite": suite,
                            "LLC_MB": llc,
                            "Page": page,
                            "Pinning": "cache_pinning" if pin else "no_cache_pinning",
                            "MTBCE": er,
                            "IPC_GMEAN": gmean(bucket.get(key, [])),
                            "Samples": len(bucket.get(key, [])),
                        })

    df = pd.DataFrame(rows)
    baseline_gmean = {
        (suite, page): gmean(vals)
        for suite, page_map in baseline_bucket.items()
        for page, vals in page_map.items()
    }
    df["Baseline_GMEAN"] = df.apply(lambda r: baseline_gmean.get((r["Suite"], r["Page"])), axis=1)
    df.to_csv(OUT_CSV, index=False)

    # 2x2 subplots: rows=page size, cols=pinning, with SPEC/GAP in same panel
    fig, axes = plt.subplots(2, 2, figsize=(12, 6.5), sharex=False)
    colors = {
        "1e-6": "#1f77b4",
        "1e-7": "#2ca02c",
        "1e-8": "#ff7f0e",
        "1e-9": "#d62728",
    }
    gap_colors = {
        "1e-6": "#8dbce0",
        "1e-7": "#95d09a",
        "1e-8": "#ffc48d",
        "1e-9": "#ee9aa0",
    }

    bar_width = 0.09

    for i, page in enumerate(PAGES):
        for j, pin in enumerate(PINNING):
            ax = axes[i, j]
            x = np.arange(len(LLC_SIZES))
            slot = 0

            for suite in SUITES:
                for er in ERROR_RATES:
                    ys = []
                    for llc in LLC_SIZES:
                        row = df[
                            (df.Suite == suite)
                            & (df.LLC_MB == llc)
                            & (df.Page == page)
                            & (df.Pinning == ("cache_pinning" if pin else "no_cache_pinning"))
                            & (df.MTBCE == er)
                        ]
                        val = None if row.empty else row.iloc[0]["IPC_GMEAN"]
                        ys.append(val)

                    ys_arr = np.array([np.nan if v is None else v for v in ys], dtype=float)
                    ax.bar(
                        x + (slot - 3.5) * bar_width,
                        ys_arr,
                        width=bar_width,
                        label=f"{suite} {er}",
                        color=colors[er] if suite == "SPEC" else gap_colors[er],
                        edgecolor="black",
                        linewidth=0.3,
                    )
                    slot += 1

            ax.set_title(f"{page.upper()} / {'Pin' if pin else 'NoPin'}", fontsize=9, fontweight='bold')
            ax.set_xlabel("LLC Size (MB)", fontsize=8)
            ax.set_ylabel("IPC (GMEAN)", fontsize=8)
            ax.set_xticks(x)
            ax.set_xticklabels(LLC_SIZES)
            ax.tick_params(axis='both', labelsize=7)
            ax.grid(True, linestyle='--', alpha=0.5, linewidth=0.5)

    handles, labels = axes[0, 0].get_legend_handles_labels()
    dedup = dict(zip(labels, handles))
    fig.legend(dedup.values(), dedup.keys(), loc='upper center', ncol=8, fontsize=7, framealpha=0.9)
    plt.tight_layout(rect=[0, 0, 1, 0.94])
    plt.savefig(OUT_PNG, dpi=300, bbox_inches='tight', facecolor='white', edgecolor='none')
    plt.close()

    print(f"CSV saved: {OUT_CSV}")
    print(f"PNG saved: {OUT_PNG}")


if __name__ == "__main__":
    main()
