#!/usr/bin/env python3
"""RBMPKI + IPC parsing for real_final_spec results."""

import os
import re
import csv
import numpy as np
import matplotlib.pyplot as plt

from common_real_final import load_records

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
OUT_CSV = os.path.join(SCRIPT_DIR, "baseline_workloads_rbmpki_ipc.csv")
OUT_BY_NAME = os.path.join(SCRIPT_DIR, "baseline_rbmpki_all_by_name.png")
OUT_RANK = os.path.join(SCRIPT_DIR, "baseline_rbmpki_all_ranking.png")
OUT_CAT = os.path.join(SCRIPT_DIR, "baseline_rbmpki_category_comparison.png")


def parse_metrics(path):
    txt = open(path, "r").read()
    ipc = None
    m = re.search(r'CPU 0 cumulative IPC:\s+([\d.]+)', txt)
    if m:
        ipc = float(m.group(1))

    instr_m = re.search(r'CPU 0 cumulative IPC:.*?instructions:\s*(\d+)', txt)
    rb_matches = re.findall(r'^\s*ROW_BUFFER_MISS:\s*(\d+)', txt, re.MULTILINE)
    rbmpki = None
    if instr_m and rb_matches:
        instr = int(instr_m.group(1))
        total_rb = sum(int(x) for x in rb_matches)
        rbmpki = (total_rb / instr) * 1000 if instr > 0 else None
    return ipc, rbmpki


def main():
    # baseline only (error_rate is None)
    recs = [r for r in load_records() if r.error_rate is None]
    rows = []
    for r in recs:
        ipc, rb = parse_metrics(r.path)
        if ipc is None:
            continue
        rows.append({
            "Category": "SPEC",
            "Workload": r.workload,
            "Page_Size": r.page.upper(),
            "IPC": ipc,
            "RBMPKI": rb if rb is not None else np.nan,
        })

    if not rows:
        print("No baseline records found")
        return

    with open(OUT_CSV, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["Category", "Workload", "Page_Size", "IPC", "RBMPKI", "Memory_Intensity"])
        w.writeheader()
        for row in sorted(rows, key=lambda x: (x["Workload"], x["Page_Size"])):
            rb = row["RBMPKI"]
            if np.isnan(rb):
                mi = "Unknown"
            elif rb > 10:
                mi = "High"
            elif rb > 5:
                mi = "Medium"
            else:
                mi = "Low"
            w.writerow({**row, "IPC": f"{row['IPC']:.4f}", "RBMPKI": "N/A" if np.isnan(rb) else f"{rb:.4f}", "Memory_Intensity": mi})

    # by-name chart
    valid = [r for r in rows if not np.isnan(r["RBMPKI"]) and r["Page_Size"] == "4KB"]
    names = [r["Workload"] for r in sorted(valid, key=lambda x: x["Workload"])]
    vals = [r["RBMPKI"] for r in sorted(valid, key=lambda x: x["Workload"])]

    plt.figure(figsize=(12, 3.2))
    plt.bar(np.arange(len(names)), vals, color="#E74C3C", alpha=0.85, edgecolor="black", linewidth=0.3)
    plt.xticks(np.arange(len(names)), names, rotation=45, ha="right", fontsize=6)
    plt.ylabel("RBMPKI", fontsize=8)
    plt.grid(axis='y', linestyle='--', alpha=0.5, linewidth=0.5)
    plt.tight_layout(pad=0.3)
    plt.savefig(OUT_BY_NAME, dpi=300, bbox_inches='tight', facecolor='white', edgecolor='none')
    plt.close()

    # ranking chart
    ranked = sorted(zip(names, vals), key=lambda x: x[1], reverse=True)
    r_names = [x[0] for x in ranked]
    r_vals = [x[1] for x in ranked]
    plt.figure(figsize=(12, 3.2))
    plt.bar(np.arange(len(r_names)), r_vals, color="#4A90E2", alpha=0.85, edgecolor="black", linewidth=0.3)
    plt.xticks(np.arange(len(r_names)), r_names, rotation=45, ha="right", fontsize=6)
    plt.ylabel("RBMPKI", fontsize=8)
    plt.grid(axis='y', linestyle='--', alpha=0.5, linewidth=0.5)
    plt.tight_layout(pad=0.3)
    plt.savefig(OUT_RANK, dpi=300, bbox_inches='tight', facecolor='white', edgecolor='none')
    plt.close()

    # category chart (SPEC only in this dataset)
    avg = float(np.mean(r_vals)) if r_vals else 0.0
    plt.figure(figsize=(4.5, 3))
    plt.bar(["SPEC"], [avg], color="#2ECC71", alpha=0.85, edgecolor="black", linewidth=0.8)
    plt.ylabel("Average RBMPKI", fontsize=8)
    plt.grid(axis='y', linestyle='--', alpha=0.5, linewidth=0.5)
    plt.tight_layout(pad=0.3)
    plt.savefig(OUT_CAT, dpi=300, bbox_inches='tight', facecolor='white', edgecolor='none')
    plt.close()

    print(f"CSV saved: {OUT_CSV}")
    print(f"PNG saved: {OUT_BY_NAME}")
    print(f"PNG saved: {OUT_RANK}")
    print(f"PNG saved: {OUT_CAT}")


if __name__ == "__main__":
    main()
