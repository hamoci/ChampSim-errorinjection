#!/usr/bin/env python3
"""Pin vs Not-Pin average IPC comparison with zero-fill for missing runs."""

import os
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt

from common_real_final import load_records, extract_ipc

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_CSV = os.path.join(SCRIPT_DIR, "llc_pin_notpin_avg_ipc_comparison.csv")
OUTPUT_PNG = os.path.join(SCRIPT_DIR, "llc_pin_notpin_avg_ipc_comparison.png")
OUTPUT_DEGRADATION_CSV = os.path.join(SCRIPT_DIR, "llc_pin_notpin_avg_degradation_summary.csv")
ERROR_RATES = ["1e-6", "1e-7", "1e-8", "1e-9"]
PAGES = ["4kb", "2mb"]
SUITES = ["SPEC", "GAP"]
LLC_MB = 2


def zero_filled_mean(values_by_workload, expected_workloads):
    if not expected_workloads:
        return None
    vals = [values_by_workload.get(w, 0.0) for w in expected_workloads]
    return float(np.mean(vals))


def degradation_pct(baseline, value):
    if baseline is None or baseline <= 0 or value is None:
        return None
    return (baseline - value) / baseline * 100.0


def delta_pct(baseline, value):
    if baseline is None or baseline <= 0 or value is None:
        return None
    return (value / baseline - 1.0) * 100.0


def collect(ipc_by, pinning: bool):
    out = {p: {e: {} for e in ERROR_RATES} for p in PAGES}
    for (w, p, e, pin), v in ipc_by.items():
        if pin == pinning and e in ERROR_RATES and p in PAGES and v is not None:
            out[p][e][w] = v
    return out


def main():
    recs = [r for r in load_records() if r.llc_mb == LLC_MB and (r.error_rate in ERROR_RATES or r.error_rate is None)]

    ipc_by = {}
    baseline = {s: {p: {} for p in PAGES} for s in SUITES}
    expected = {s: {p: set() for p in PAGES} for s in SUITES}
    for r in recs:
        if r.suite not in SUITES:
            continue
        ipc = extract_ipc(r.path)
        if ipc is None:
            continue
        workload_key = r.workload
        if r.page in PAGES:
            expected[r.suite][r.page].add(workload_key)
        if r.error_rate is None and r.page in PAGES:
            baseline[r.suite][r.page][workload_key] = ipc
            continue
        ipc_by[(r.suite, workload_key, r.page, r.error_rate, r.pinning)] = ipc

    all_rows = []
    suite_frames = {}
    for suite in SUITES:
        suite_ipc_by = {}
        for (s, w, p, e, pin), v in ipc_by.items():
            if s == suite:
                suite_ipc_by[(w, p, e, pin)] = v

        pin = collect(suite_ipc_by, True)
        notpin = collect(suite_ipc_by, False)

        rows = []
        for e in ERROR_RATES:
            rows.append({
                "Suite": suite,
                "MTBCE": e,
                "Baseline_4KB": zero_filled_mean(baseline[suite]["4kb"], expected[suite]["4kb"]),
                "Baseline_2MB": zero_filled_mean(baseline[suite]["2mb"], expected[suite]["2mb"]),
                "Pin_4KB": zero_filled_mean(pin["4kb"][e], expected[suite]["4kb"]),
                "Pin_2MB": zero_filled_mean(pin["2mb"][e], expected[suite]["2mb"]),
                "NotPin_4KB": zero_filled_mean(notpin["4kb"][e], expected[suite]["4kb"]),
                "NotPin_2MB": zero_filled_mean(notpin["2mb"][e], expected[suite]["2mb"]),
            })

        df = pd.DataFrame(rows)
        suite_frames[suite] = df
        all_rows.extend(rows)

    out_df = pd.DataFrame(all_rows)
    out_df.to_csv(OUTPUT_CSV, index=False)

    # Baseline 대비 성능 저하율 요약 (Pin / NotPin, 1e-6~1e-9 평균)
    degr_rows = []
    for suite in SUITES:
        sub = out_df[out_df["Suite"] == suite].set_index("MTBCE").reindex(ERROR_RATES)
        for page in PAGES:
            base_col = f"Baseline_{page.upper()}"
            pin_col = f"Pin_{page.upper()}"
            notpin_col = f"NotPin_{page.upper()}"

            pin_degr = [degradation_pct(sub.loc[e, base_col], sub.loc[e, pin_col]) for e in ERROR_RATES]
            notpin_degr = [degradation_pct(sub.loc[e, base_col], sub.loc[e, notpin_col]) for e in ERROR_RATES]

            pin_vals = [v for v in pin_degr if v is not None]
            notpin_vals = [v for v in notpin_degr if v is not None]

            degr_rows.append({
                "Suite": suite,
                "Page": page.upper(),
                "Type": "Pin",
                "Avg_Degradation_Pct": float(np.mean(pin_vals)) if pin_vals else None,
                "Degradation_1e-6_Pct": pin_degr[0],
                "Degradation_1e-7_Pct": pin_degr[1],
                "Degradation_1e-8_Pct": pin_degr[2],
                "Degradation_1e-9_Pct": pin_degr[3],
            })
            degr_rows.append({
                "Suite": suite,
                "Page": page.upper(),
                "Type": "NotPin",
                "Avg_Degradation_Pct": float(np.mean(notpin_vals)) if notpin_vals else None,
                "Degradation_1e-6_Pct": notpin_degr[0],
                "Degradation_1e-7_Pct": notpin_degr[1],
                "Degradation_1e-8_Pct": notpin_degr[2],
                "Degradation_1e-9_Pct": notpin_degr[3],
            })

    degr_df = pd.DataFrame(degr_rows)
    degr_df.to_csv(OUTPUT_DEGRADATION_CSV, index=False)

    x = np.arange(len(ERROR_RATES))
    bw = 0.14
    fig, axes = plt.subplots(2, 1, figsize=(10, 5.0), sharex=True)
    axes = np.array(axes).reshape(-1)

    for idx, suite in enumerate(SUITES):
        ax = axes[idx]
        df = suite_frames.get(suite, pd.DataFrame())
        if df.empty:
            ax.set_title(f"{suite} (no data)", fontsize=9, fontweight="bold")
            continue

        b4 = df["Baseline_4KB"].to_numpy(dtype=float)
        n4 = df["NotPin_4KB"].to_numpy(dtype=float)
        p4 = df["Pin_4KB"].to_numpy(dtype=float)
        b2 = df["Baseline_2MB"].to_numpy(dtype=float)
        n2 = df["NotPin_2MB"].to_numpy(dtype=float)
        p2 = df["Pin_2MB"].to_numpy(dtype=float)

        ax.bar(x - 2.5*bw, b4, bw, label="Baseline 4KB", color="#9E9E9E", edgecolor="black", linewidth=0.3, alpha=0.9)
        ax.bar(x - 1.5*bw, n4, bw, label="NotPin 4KB", color="#922B21", edgecolor="black", linewidth=0.3)
        ax.bar(x - 0.5*bw, p4, bw, label="Pin 4KB", color="#F1948A", edgecolor="black", linewidth=0.3)
        ax.bar(x + 0.5*bw, b2, bw, label="Baseline 2MB", color="#BDBDBD", edgecolor="black", linewidth=0.3, alpha=0.9)
        ax.bar(x + 1.5*bw, n2, bw, label="NotPin 2MB", color="#1A5276", edgecolor="black", linewidth=0.3)
        ax.bar(x + 2.5*bw, p2, bw, label="Pin 2MB", color="#7FB3D5", edgecolor="black", linewidth=0.3)

        # Annotate each non-baseline bar with baseline-relative delta (%).
        for i in range(len(x)):
            labels = [
                (x[i] - 1.5 * bw, n4[i], delta_pct(b4[i], n4[i])),
                (x[i] - 0.5 * bw, p4[i], delta_pct(b4[i], p4[i])),
                (x[i] + 1.5 * bw, n2[i], delta_pct(b2[i], n2[i])),
                (x[i] + 2.5 * bw, p2[i], delta_pct(b2[i], p2[i])),
            ]
            for xpos, ypos, d in labels:
                if np.isnan(ypos) or d is None or np.isnan(d):
                    continue
                ax.text(
                    xpos,
                    ypos + max(0.003, abs(ypos) * 0.02),
                    f"{d:+.1f}%",
                    ha="center",
                    va="bottom",
                    fontsize=5,
                )

        ax.set_ylabel("IPC", fontsize=8)
        ax.set_title(f"{suite} (LLC 2MB)", fontsize=9, fontweight="bold")
        ax.tick_params(axis='y', labelsize=6)
        ax.yaxis.grid(True, linestyle='--', alpha=0.5, linewidth=0.5)
        ax.set_axisbelow(True)
        ax.set_xticks(x)
        ax.set_xticklabels(ERROR_RATES, fontsize=7)
        ax.tick_params(axis='x', labelbottom=True)

    handles, labels = axes[0].get_legend_handles_labels()
    fig.legend(handles, labels, loc='upper center', ncol=3, fontsize=7, framealpha=0.9, bbox_to_anchor=(0.5, 1.01))
    plt.tight_layout(rect=[0, 0, 1, 0.95], pad=0.5)
    plt.savefig(OUTPUT_PNG, dpi=300, bbox_inches='tight', facecolor='white', edgecolor='none')
    plt.close()

    print(f"CSV saved: {OUTPUT_CSV}")
    print(f"CSV saved: {OUTPUT_DEGRADATION_CSV}")
    print(f"PNG saved: {OUTPUT_PNG}")


if __name__ == "__main__":
    main()
