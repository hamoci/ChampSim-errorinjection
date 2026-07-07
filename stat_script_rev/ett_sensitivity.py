#!/usr/bin/env python3
"""Parse ETT sensitivity results (2_ett_sensitivity) and output IPC + ETT stats."""

import os
import re
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
BASE_DIR = os.path.dirname(SCRIPT_DIR)
RESULTS_DIR = os.path.join(BASE_DIR, "results/ett_evaluation/2_ett_sensitivity")

# Filename pattern:
#   ett_sens_entries_{N}_{BER}_{trace}.txt
#   ett_sens_retire_{N}_{BER}_{trace}.txt
#   ett_sens_retire_off_{N}_{BER}_{trace}.txt
FILE_RE = re.compile(
    r"^ett_sens_(?P<category>entries|retire|retire_off)_(?P<param>\d+)_(?P<ber>1e-\d+)_(?P<trace>.+)\.txt$"
)

WORKLOAD_RE = re.compile(r"^(\d+\.\w+)")

# Regex patterns for extracting metrics
IPC_RE = re.compile(r"CPU 0 cumulative IPC:\s+([\d.eE+\-]+)")
ETT_ENTRIES_RE = re.compile(r"ETT Entries:\s+(\d+)")
RETIREMENT_THRESHOLD_RE = re.compile(r"Retirement Threshold:\s+(\d+)")
ETT_EVICTIONS_RE = re.compile(r"ETT Evictions:\s+(\d+)")
PAGE_RETIREMENTS_RE = re.compile(r"Page Retirements.*?:\s+(\d+)")
TOTAL_ERRORS_RE = re.compile(r"Total DRAM Error Events:\s+(\d+)")
FIRST_ERROR_RE = re.compile(r"First Error \(per page\):\s+(\d+)")
ADDED_ERROR_RE = re.compile(r"Additional Errors:\s+(\d+)")
ALREADY_KNOWN_RE = re.compile(r"Already Known \(bloom hit\):\s+(\d+)")
ERROR_WAY_HITS_RE = re.compile(r"Error Way Hits:\s+(\d+)")
ERROR_WAY_FILLS_RE = re.compile(r"Error Way Fills.*?:\s+(\d+)")
ERROR_WAY_EVICTIONS_RE = re.compile(r"Error Way Evictions.*?:\s+(\d+)")
ALLOC_ERROR_WAYS_RE = re.compile(r"Allocated Error Ways per Set:\s+(\d+)")
# ETT Eviction Invalidation (second occurrence of "Cache Lines Invalidated")
ETT_EVICT_INVAL_RE = re.compile(r"\[ETT Eviction Invalidation Detail\].*?Cache Lines Invalidated:\s+(\d+)", re.DOTALL)


def extract_metrics(path):
    """Extract all relevant metrics from a result file."""
    try:
        with open(path, "r") as f:
            txt = f.read()
    except Exception:
        return None

    def _search(regex, default=None):
        m = regex.search(txt)
        return m.group(1) if m else default

    ipc = _search(IPC_RE)
    if ipc is None:
        return None

    return {
        "ipc": float(ipc),
        "ett_entries": _int(_search(ETT_ENTRIES_RE)),
        "retirement_threshold": _int(_search(RETIREMENT_THRESHOLD_RE)),
        "ett_evictions": _int(_search(ETT_EVICTIONS_RE)),
        "page_retirements": _int(_search(PAGE_RETIREMENTS_RE)),
        "total_errors": _int(_search(TOTAL_ERRORS_RE)),
        "first_errors": _int(_search(FIRST_ERROR_RE)),
        "added_errors": _int(_search(ADDED_ERROR_RE)),
        "already_known": _int(_search(ALREADY_KNOWN_RE)),
        "error_way_hits": _int(_search(ERROR_WAY_HITS_RE)),
        "error_way_fills": _int(_search(ERROR_WAY_FILLS_RE)),
        "error_way_evictions": _int(_search(ERROR_WAY_EVICTIONS_RE)),
        "alloc_error_ways": _int(_search(ALLOC_ERROR_WAYS_RE)),
        "ett_evict_inval_lines": _int(_search(ETT_EVICT_INVAL_RE)),
    }


def _int(val):
    return int(val) if val is not None else None


def gmean(values):
    vals = [v for v in values if v and v > 0]
    if not vals:
        return 0.0
    return float(np.exp(np.mean(np.log(vals))))


def load_all():
    """Load all results and return a DataFrame."""
    rows = []
    if not os.path.isdir(RESULTS_DIR):
        print(f"Results directory not found: {RESULTS_DIR}")
        return pd.DataFrame()

    for fname in sorted(os.listdir(RESULTS_DIR)):
        m = FILE_RE.match(fname)
        if not m:
            continue

        category = m.group("category")
        param = int(m.group("param"))
        ber = m.group("ber")
        trace = m.group("trace")

        wm = WORKLOAD_RE.match(trace)
        workload = wm.group(1) if wm else trace

        path = os.path.join(RESULTS_DIR, fname)
        metrics = extract_metrics(path)
        if metrics is None:
            continue

        rows.append({
            "category": category,
            "param": param,
            "ber": ber,
            "trace": trace,
            "workload": workload,
            **metrics,
        })

    return pd.DataFrame(rows)


def plot_entries_ipc(df):
    """Plot IPC vs ETT entries for each BER."""
    entries_df = df[df["category"] == "entries"]
    if entries_df.empty:
        print("No 'entries' data found.")
        return

    bers = sorted(entries_df["ber"].unique(), key=lambda x: float(x))
    entry_values = sorted(entries_df["param"].unique())
    workloads = sorted(entries_df["workload"].unique())

    # --- Per-BER plot: IPC by workload grouped by entry count ---
    for ber in bers:
        sub = entries_df[entries_df["ber"] == ber]
        pivot = sub.pivot_table(index="workload", columns="param", values="ipc", aggfunc="first")
        pivot = pivot.reindex(columns=entry_values)

        # Append gmean row
        gmean_row = {}
        for col in pivot.columns:
            vals = pivot[col].dropna().values
            gmean_row[col] = gmean(vals) if len(vals) > 0 else np.nan
        pivot.loc["Gmean"] = gmean_row

        # Save CSV
        csv_path = os.path.join(SCRIPT_DIR, f"ett_entries_ipc_{ber}.csv")
        pivot.to_csv(csv_path)
        print(f"CSV saved: {csv_path}")

        # Plot
        fig, ax = plt.subplots(figsize=(14, 4))
        x = np.arange(len(pivot.index))
        n_bars = len(entry_values)
        width = 0.8 / n_bars
        colors = plt.cm.Blues(np.linspace(0.3, 0.9, n_bars))

        for i, ent in enumerate(entry_values):
            if ent in pivot.columns:
                vals = pivot[ent].values
                ax.bar(x + i * width, vals, width, label=f"{ent} entries",
                       color=colors[i], edgecolor="black", linewidth=0.3)

        ax.set_ylabel("IPC", fontsize=9)
        ax.set_title(f"ETT Entries Sensitivity — BER={ber}", fontsize=10)
        ax.set_xticks(x + width * (n_bars - 1) / 2)
        ax.set_xticklabels(pivot.index, rotation=45, ha="right", fontsize=7)
        ax.legend(fontsize=6, ncol=n_bars, loc="upper right")
        ax.yaxis.grid(True, linestyle="--", alpha=0.5, linewidth=0.5)
        ax.set_axisbelow(True)
        plt.tight_layout(pad=0.3)

        png_path = os.path.join(SCRIPT_DIR, f"ett_entries_ipc_{ber}.png")
        plt.savefig(png_path, dpi=300, bbox_inches="tight", facecolor="white")
        plt.close()
        print(f"PNG saved: {png_path}")

    # --- Summary: ETT evictions + invalidated lines ---
    summary_rows = []
    for ber in bers:
        for ent in entry_values:
            sub = entries_df[(entries_df["ber"] == ber) & (entries_df["param"] == ent)]
            if sub.empty:
                continue
            summary_rows.append({
                "ber": ber,
                "entries": ent,
                "ipc_gmean": gmean(sub["ipc"].dropna().values),
                "avg_ett_evictions": sub["ett_evictions"].mean(),
                "avg_page_retirements": sub["page_retirements"].mean(),
                "avg_total_errors": sub["total_errors"].mean(),
                "avg_error_way_hits": sub["error_way_hits"].mean(),
                "avg_error_way_fills": sub["error_way_fills"].mean(),
                "avg_error_way_evictions": sub["error_way_evictions"].mean(),
                "avg_ett_evict_inval_lines": sub["ett_evict_inval_lines"].mean(),
                "avg_already_known": sub["already_known"].mean(),
            })

    summary_df = pd.DataFrame(summary_rows)
    csv_path = os.path.join(SCRIPT_DIR, "ett_entries_summary.csv")
    summary_df.to_csv(csv_path, index=False)
    print(f"Summary CSV saved: {csv_path}")


def plot_retire_ipc(df):
    """Plot IPC vs retirement threshold for each BER (pinning on vs off)."""
    retire_on = df[df["category"] == "retire"]
    retire_off = df[df["category"] == "retire_off"]

    if retire_on.empty and retire_off.empty:
        print("No 'retire' data found.")
        return

    bers = sorted(set(retire_on["ber"].unique()) | set(retire_off["ber"].unique()),
                  key=lambda x: float(x))

    for ber in bers:
        sub_on = retire_on[retire_on["ber"] == ber]
        sub_off = retire_off[retire_off["ber"] == ber]

        thresholds_on = sorted(sub_on["param"].unique()) if not sub_on.empty else []
        thresholds_off = sorted(sub_off["param"].unique()) if not sub_off.empty else []
        all_thresholds = sorted(set(thresholds_on) | set(thresholds_off))
        workloads = sorted(set(sub_on["workload"].unique()) | set(sub_off["workload"].unique()))

        # Build pivot for pinning ON
        rows = []
        for w in workloads:
            row = {"workload": w}
            for t in all_thresholds:
                val_on = sub_on[(sub_on["workload"] == w) & (sub_on["param"] == t)]
                val_off = sub_off[(sub_off["workload"] == w) & (sub_off["param"] == t)]
                row[f"pin_on_{t}"] = val_on["ipc"].values[0] if not val_on.empty else np.nan
                row[f"pin_off_{t}"] = val_off["ipc"].values[0] if not val_off.empty else np.nan
            rows.append(row)

        pivot = pd.DataFrame(rows).set_index("workload")

        # Gmean
        gmean_row = {}
        for col in pivot.columns:
            vals = pivot[col].dropna().values
            gmean_row[col] = gmean(vals) if len(vals) > 0 else np.nan
        pivot.loc["Gmean"] = gmean_row

        csv_path = os.path.join(SCRIPT_DIR, f"ett_retire_ipc_{ber}.csv")
        pivot.to_csv(csv_path)
        print(f"CSV saved: {csv_path}")

        # Plot
        fig, ax = plt.subplots(figsize=(14, 4))
        x = np.arange(len(pivot.index))
        n_groups = len(all_thresholds)
        total_bars = n_groups * 2  # on + off
        width = 0.8 / max(total_bars, 1)

        colors_on = plt.cm.Blues(np.linspace(0.4, 0.9, n_groups))
        colors_off = plt.cm.Reds(np.linspace(0.4, 0.9, n_groups))

        idx = 0
        for i, t in enumerate(all_thresholds):
            col_on = f"pin_on_{t}"
            col_off = f"pin_off_{t}"
            if col_on in pivot.columns:
                ax.bar(x + idx * width, pivot[col_on].values, width,
                       label=f"Pin ON, thr={t}", color=colors_on[i],
                       edgecolor="black", linewidth=0.3)
                idx += 1
            if col_off in pivot.columns:
                ax.bar(x + idx * width, pivot[col_off].values, width,
                       label=f"Pin OFF, thr={t}", color=colors_off[i],
                       edgecolor="black", linewidth=0.3)
                idx += 1

        ax.set_ylabel("IPC", fontsize=9)
        ax.set_title(f"Retirement Threshold Sensitivity — BER={ber}", fontsize=10)
        ax.set_xticks(x + width * (total_bars - 1) / 2)
        ax.set_xticklabels(pivot.index, rotation=45, ha="right", fontsize=7)
        ax.legend(fontsize=5, ncol=4, loc="upper right")
        ax.yaxis.grid(True, linestyle="--", alpha=0.5, linewidth=0.5)
        ax.set_axisbelow(True)
        plt.tight_layout(pad=0.3)

        png_path = os.path.join(SCRIPT_DIR, f"ett_retire_ipc_{ber}.png")
        plt.savefig(png_path, dpi=300, bbox_inches="tight", facecolor="white")
        plt.close()
        print(f"PNG saved: {png_path}")


def main():
    df = load_all()
    if df.empty:
        print("No data loaded.")
        return

    print(f"Loaded {len(df)} records")
    print(f"  Categories: {df['category'].value_counts().to_dict()}")
    print(f"  BERs: {sorted(df['ber'].unique())}")
    print()

    plot_entries_ipc(df)
    print()
    plot_retire_ipc(df)


if __name__ == "__main__":
    main()
