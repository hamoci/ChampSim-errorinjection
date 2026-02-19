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
    for r in recs:
        ipc = extract_ipc(r.path)
        if ipc is None:
            continue
        data.setdefault(r.workload, {})[r.page] = ipc

    workloads = sorted([w for w, v in data.items() if "4kb" in v and "2mb" in v])
    ipc4 = [data[w]["4kb"] for w in workloads]
    ipc2 = [data[w]["2mb"] for w in workloads]

    df = pd.DataFrame({"Workload": workloads, "4KB_IPC": ipc4, "2MB_IPC": ipc2})
    df.to_csv(OUTPUT_CSV, index=False)

    if not workloads:
        print("No baseline workload pairs found")
        return

    g4, g2 = gmean(ipc4), gmean(ipc2)
    w2 = workloads + ["GMEAN"]
    y4 = ipc4 + [g4]
    y2 = ipc2 + [g2]

    x = np.arange(len(w2))
    width = 0.38
    fig, ax = plt.subplots(figsize=(10, 2.8))
    ax.bar(x - width / 2, y4, width, label="4KB Page", color="#EE5A6F", edgecolor="black", linewidth=0.3)
    ax.bar(x + width / 2, y2, width, label="2MB Page", color="#4A90E2", edgecolor="black", linewidth=0.3)

    for i in range(len(w2)):
        pct = (y2[i] / y4[i] - 1) * 100 if y4[i] > 0 else 0
        ax.text(x[i], max(y4[i], y2[i]) * 1.02, f"{pct:+.0f}%", ha="center", va="bottom", fontsize=5)

    ax.set_ylabel("IPC", fontsize=8)
    ax.set_xticks(x)
    ax.set_xticklabels(w2, rotation=45, ha="right", fontsize=5)
    ax.tick_params(axis="y", labelsize=6)
    ax.yaxis.grid(True, linestyle="--", alpha=0.5, linewidth=0.5)
    ax.set_axisbelow(True)
    ax.legend(loc="upper right", fontsize=6)
    plt.tight_layout(pad=0.3)
    plt.savefig(OUTPUT_PNG, dpi=300, bbox_inches="tight", facecolor="white", edgecolor="none")
    plt.close()

    print(f"CSV saved: {OUTPUT_CSV}")
    print(f"PNG saved: {OUTPUT_PNG}")


if __name__ == "__main__":
    main()
