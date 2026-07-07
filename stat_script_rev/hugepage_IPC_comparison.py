#!/usr/bin/env python3
"""4KB vs 2MB baseline IPC comparison (real_final_spec)."""

import os
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt

from common_real_final import load_records, extract_ipc

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_CSV = os.path.join(SCRIPT_DIR, "hugepage_IPC_comparison.csv")
OUTPUT_PNG = os.path.join(SCRIPT_DIR, "hugepage_IPC_comparison.png")


def gmean(values):
    vals = [v for v in values if v and v > 0]
    if not vals:
        return 0.0
    return float(np.exp(np.mean(np.log(vals))))


def main():
    recs = [r for r in load_records() if r.llc_mb == 2 and r.error_rate is None]

    data = {}
    spec_data = {}
    gap_data = {}
    for r in recs:
        ipc = extract_ipc(r.path)
        if ipc is None:
            continue
        data.setdefault(r.workload, {})[r.page] = ipc
        if r.suite == "SPEC":
            spec_data.setdefault(r.workload, {})[r.page] = ipc
        elif r.suite == "GAP":
            gap_data.setdefault(r.workload, {})[r.page] = ipc

    workloads = sorted([w for w, v in data.items() if "4kb" in v and "2mb" in v])
    ipc4 = [data[w]["4kb"] for w in workloads]
    ipc2 = [data[w]["2mb"] for w in workloads]

    df = pd.DataFrame({"Workload": workloads, "4KB_IPC": ipc4, "2MB_IPC": ipc2})
    df.to_csv(OUTPUT_CSV, index=False)

    if not workloads:
        print("No baseline workload pairs found")
        return

    spec_w = [w for w, v in spec_data.items() if "4kb" in v and "2mb" in v]
    gap_w = [w for w, v in gap_data.items() if "4kb" in v and "2mb" in v]
    spec4 = [spec_data[w]["4kb"] for w in sorted(spec_w)]
    spec2 = [spec_data[w]["2mb"] for w in sorted(spec_w)]
    gap4 = [gap_data[w]["4kb"] for w in sorted(gap_w)]
    gap2 = [gap_data[w]["2mb"] for w in sorted(gap_w)]

    gmean_labels = ["SPEC GMEAN", "GAP GMEAN", "TOTAL GMEAN"]
    g4 = [gmean(spec4), gmean(gap4), gmean(ipc4)]
    g2 = [gmean(spec2), gmean(gap2), gmean(ipc2)]

    w2 = workloads + gmean_labels

    x = np.arange(len(w2))
    x_main = np.arange(len(workloads))
    x_g = np.arange(len(workloads), len(w2))
    width = 0.38
    fig, ax = plt.subplots(figsize=(10, 2.8))
    ax.bar(x_main - width / 2, ipc4, width, label="4KB Page", color="#EE5A6F", edgecolor="black", linewidth=0.3)
    ax.bar(x_main + width / 2, ipc2, width, label="2MB Page", color="#4A90E2", edgecolor="black", linewidth=0.3)
    # Highlight GMEAN bars with thicker outlines for separation.
    ax.bar(x_g - width / 2, g4, width, color="#EE5A6F", edgecolor="black", linewidth=1.2)
    ax.bar(x_g + width / 2, g2, width, color="#4A90E2", edgecolor="black", linewidth=1.2)

    for i in range(len(w2)):
        y4i = ipc4[i] if i < len(workloads) else g4[i - len(workloads)]
        y2i = ipc2[i] if i < len(workloads) else g2[i - len(workloads)]
        pct = (y2i / y4i - 1) * 100 if y4i > 0 else 0
        ax.text(x[i], max(y4i, y2i) * 1.02, f"{pct:+.0f}%", ha="center", va="bottom", fontsize=5)

    ax.set_ylabel("IPC", fontsize=8)
    ax.set_xticks(x)
    ax.set_xticklabels(w2, rotation=45, ha="right", fontsize=5)
    ax.tick_params(axis="y", labelsize=6)
    ax.yaxis.grid(True, linestyle="--", alpha=0.5, linewidth=0.5)
    ax.set_axisbelow(True)
    ax.margins(x=0.01)
    ax.legend(loc="upper right", fontsize=6)
    plt.tight_layout(pad=0.15)
    plt.savefig(OUTPUT_PNG, dpi=300, bbox_inches="tight", pad_inches=0.05, facecolor="white", edgecolor="none")
    plt.close()

    print(f"CSV saved: {OUTPUT_CSV}")
    print(f"PNG saved: {OUTPUT_PNG}")


if __name__ == "__main__":
    main()
