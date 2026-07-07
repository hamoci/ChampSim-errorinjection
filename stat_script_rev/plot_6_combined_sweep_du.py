#!/usr/bin/env python3
"""Parse and plot IPC from experiment 6 combined sweep (du test)."""

import os
import re
import sys
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib
matplotlib.use('Agg')

RESULT_DIR = os.path.join(os.path.dirname(__file__), "..",
                          "results", "ett_evaluation", "6_combined_sweep_du_test")

# Parse filename: comb_e{entries}_t{threshold}_w{ways}_{rate}_du_sh_trace.txt
FNAME_RE = re.compile(r"comb_e(\d+)_t(\d+)_w(\d+)_(1e-\d+)_du_sh_trace\.txt$")
IPC_RE = re.compile(r"cumulative IPC:\s+([\d.]+)")


def parse_results():
    rows = []
    for fname in os.listdir(RESULT_DIR):
        m = FNAME_RE.match(fname)
        if not m:
            continue
        entries, threshold, ways, rate = int(m[1]), int(m[2]), int(m[3]), m[4]
        path = os.path.join(RESULT_DIR, fname)
        with open(path) as f:
            text = f.read()
        # Get last IPC (Simulation complete line)
        ipcs = IPC_RE.findall(text)
        if not ipcs:
            continue
        ipc = float(ipcs[-1])
        rows.append({"ett_entries": entries, "threshold": threshold,
                      "max_ways": ways, "error_rate": rate, "ipc": ipc})
    return pd.DataFrame(rows)


def plot_heatmaps(df):
    """For each error rate: heatmap grid of threshold x max_ways, one subplot per ett_entries."""
    rates = sorted(df["error_rate"].unique(), key=lambda x: float(x))
    entries_list = sorted(df["ett_entries"].unique())

    for rate in rates:
        dfr = df[df["error_rate"] == rate]
        fig, axes = plt.subplots(1, len(entries_list), figsize=(5 * len(entries_list), 4),
                                 sharey=True)
        if len(entries_list) == 1:
            axes = [axes]

        vmin, vmax = dfr["ipc"].min(), dfr["ipc"].max()

        for ax, ent in zip(axes, entries_list):
            sub = dfr[dfr["ett_entries"] == ent]
            pivot = sub.pivot_table(index="threshold", columns="max_ways", values="ipc")
            pivot = pivot.sort_index(ascending=False)

            im = ax.imshow(pivot.values, aspect="auto", cmap="RdYlGn",
                           vmin=vmin, vmax=vmax)
            ax.set_xticks(range(len(pivot.columns)))
            ax.set_xticklabels(pivot.columns)
            ax.set_yticks(range(len(pivot.index)))
            ax.set_yticklabels(pivot.index)
            ax.set_xlabel("max_error_ways")
            if ax == axes[0]:
                ax.set_ylabel("retirement_threshold")
            ax.set_title(f"ETT entries={ent}")

            for i in range(len(pivot.index)):
                for j in range(len(pivot.columns)):
                    ax.text(j, i, f"{pivot.values[i, j]:.3f}",
                            ha="center", va="center", fontsize=9,
                            color="black")

        fig.suptitle(f"IPC — Error Rate {rate} (du trace)", fontsize=14, y=1.02)
        fig.colorbar(im, ax=axes, shrink=0.8, label="IPC")
        plt.tight_layout()
        out = os.path.join(RESULT_DIR, f"ipc_heatmap_{rate}.png")
        fig.savefig(out, dpi=150, bbox_inches="tight")
        print(f"Saved: {out}")
        plt.close(fig)


def plot_grouped_bars(df):
    """For each error rate: grouped bar chart — x=ett_entries, groups=threshold, subgroups=max_ways."""
    rates = sorted(df["error_rate"].unique(), key=lambda x: float(x))
    entries_list = sorted(df["ett_entries"].unique())
    thresholds = sorted(df["threshold"].unique())
    ways_list = sorted(df["max_ways"].unique())

    for rate in rates:
        dfr = df[df["error_rate"] == rate]
        fig, ax = plt.subplots(figsize=(12, 5))

        n_groups = len(entries_list)
        n_bars = len(thresholds) * len(ways_list)
        bar_width = 0.8 / n_bars
        x_base = range(n_groups)

        colors = plt.cm.tab10.colors
        ci = 0
        for ti, t in enumerate(thresholds):
            for wi, w in enumerate(ways_list):
                offsets = [x + (ci - n_bars / 2 + 0.5) * bar_width for x in x_base]
                vals = []
                for e in entries_list:
                    row = dfr[(dfr["ett_entries"] == e) & (dfr["threshold"] == t) & (dfr["max_ways"] == w)]
                    vals.append(row["ipc"].values[0] if len(row) else 0)
                ax.bar(offsets, vals, bar_width, label=f"t={t}, w={w}", color=colors[ci % 10])
                ci += 1

        ax.set_xticks(range(n_groups))
        ax.set_xticklabels([f"e={e}" for e in entries_list])
        ax.set_xlabel("ETT entries")
        ax.set_ylabel("IPC")
        ax.set_title(f"IPC Comparison — Error Rate {rate} (du trace)")
        ax.legend(bbox_to_anchor=(1.02, 1), loc="upper left", fontsize=7, title="threshold, ways")
        plt.tight_layout()
        out = os.path.join(RESULT_DIR, f"ipc_bars_{rate}.png")
        fig.savefig(out, dpi=150, bbox_inches="tight")
        print(f"Saved: {out}")
        plt.close(fig)


if __name__ == "__main__":
    df = parse_results()
    if df.empty:
        print("No results found!")
        sys.exit(1)

    print(f"Parsed {len(df)} results")
    csv_path = os.path.join(RESULT_DIR, "ipc_summary.csv")
    df.to_csv(csv_path, index=False)
    print(f"Saved: {csv_path}")

    plot_heatmaps(df)
    plot_grouped_bars(df)
