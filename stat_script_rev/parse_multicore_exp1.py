#!/usr/bin/env python3
"""Parse multicore Exp 1 (error rate sweep) results.

Input : results/multicore/1_error_rate_sweep/
        champsim_4core_8mb_{noerr|off_RATE|pin_RATE}_{MIX}.txt
Output: multicore_exp1_percpu.csv   — one row per (mix, scheme, rate, cpu)
        multicore_exp1_summary.csv  — one row per (mix, scheme, rate)
        console: weighted-speedup pivot (mix x scheme)

Metrics
- Per-CPU IPC comes from the LAST "CPU n cumulative IPC" match: ChampSim
  prints two stat blocks (full-run, then ROI where every CPU is measured
  over its own --simulation-instructions window); the ROI block is last.
- weighted_speedup = sum_i( IPC_i^scheme / IPC_i^noerr ), noerr of the SAME
  mix as the alone-reference (max 4.0). norm_throughput = sum IPC ratio.
- Per-CPU error attribution comes from the [ERROR] "CPU n: absorbed=..."
  lines added in commit 707259c.
"""

import argparse
import csv
import os
import re
import sys
from math import exp, log

MIXES = {
    "M1": ["mcf", "fotonik3d", "gcc", "bwaves"],
    "M2": ["mcf", "fotonik3d", "gcc", "omnetpp"],
    "M3": ["mcf", "fotonik3d", "bwaves", "omnetpp"],
    "M4": ["mcf", "gcc", "bwaves", "omnetpp"],
    "C1": ["xalancbmk", "pop2", "roms", "wrf"],
    "C2": ["xalancbmk", "pop2", "roms", "cactuBSSN"],
    "C3": ["xalancbmk", "pop2", "wrf", "cactuBSSN"],
    "C4": ["xalancbmk", "roms", "wrf", "cactuBSSN"],
    "H1": ["mcf", "fotonik3d", "xalancbmk", "pop2"],
    "H2": ["gcc", "omnetpp", "wrf", "roms"],
}
MIX_ORDER = ["M1", "M2", "M3", "M4", "C1", "C2", "C3", "C4", "H1", "H2"]
SCHEME_ORDER = ["noerr", "off_1e-6", "off_1e-7", "off_1e-8",
                "pin_1e-6", "pin_1e-7", "pin_1e-8"]
NUM_CPUS = 4

RE_FNAME = re.compile(
    r"^champsim_4core_8mb_(?P<scheme>noerr|off_1e-\d|pin_1e-\d)_(?P<mix>[MCH]\d)\.txt$")
RE_CPU_IPC = re.compile(
    r"^CPU (?P<cpu>\d) cumulative IPC:\s+(?P<ipc>[\d.]+)\s+instructions:\s*(?P<instr>\d+)\s+cycles:\s*(?P<cycles>\d+)")
RE_COMPLETE = re.compile(r"^Simulation complete CPU (?P<cpu>\d).*\(Simulation time:\s*(?P<h>\d+) hr (?P<m>\d+) min (?P<s>\d+) sec\)")
RE_PERCPU_ERR = re.compile(
    r"\[ERROR\]\s+CPU (?P<cpu>\d): absorbed=(?P<absorbed>\d+) first=(?P<first>\d+) added=(?P<added>\d+) known=(?P<known>\d+) retired=(?P<retired>\d+) baseline_retired=(?P<bretired>\d+)")
RE_TOTAL_ERR = re.compile(r"Total DRAM Error Events:\s+(\d+)")
RE_PAGES_RETIRED = re.compile(r"Pages Retired:\s+(\d+)")
RE_BASELINE_RETIRED = re.compile(r"Baseline Page Retirements:\s+(\d+)")
RE_OFF_RETIRED = re.compile(r"Retired \(page offline\):\s+(\d+)\s+\(([\d.]+)%\)")
RE_OFF_LIVE = re.compile(r"Live \(still tracked\):\s+(\d+)")
RE_LLC = re.compile(
    r"^cpu(?P<cpu>\d)->LLC TOTAL\s+ACCESS:\s+(?P<access>\d+)\s+HIT:\s+(?P<hit>\d+)\s+MISS:\s+(?P<miss>\d+)")


def parse_file(path):
    """Return dict of last-match metrics for one result file."""
    d = {
        "cpu_ipc": {}, "cpu_instr": {}, "cpu_cycles": {},
        "cpu_err": {}, "cpu_llc": {},
        "complete_cpus": set(), "sim_seconds": None,
        "total_errors": None, "pages_retired": None,
        "baseline_retired": None, "off_retired": None,
        "off_retired_pct": None, "off_live": None,
    }
    with open(path, errors="replace") as f:
        for line in f:
            m = RE_CPU_IPC.match(line)
            if m:
                c = int(m.group("cpu"))
                d["cpu_ipc"][c] = float(m.group("ipc"))
                d["cpu_instr"][c] = int(m.group("instr"))
                d["cpu_cycles"][c] = int(m.group("cycles"))
                continue
            m = RE_COMPLETE.match(line)
            if m:
                d["complete_cpus"].add(int(m.group("cpu")))
                secs = int(m.group("h")) * 3600 + int(m.group("m")) * 60 + int(m.group("s"))
                d["sim_seconds"] = max(d["sim_seconds"] or 0, secs)
                continue
            m = RE_PERCPU_ERR.search(line)
            if m:
                d["cpu_err"][int(m.group("cpu"))] = {
                    k: int(m.group(k)) for k in
                    ("absorbed", "first", "added", "known", "retired", "bretired")}
                continue
            m = RE_LLC.match(line)
            if m:
                d["cpu_llc"][int(m.group("cpu"))] = (
                    int(m.group("access")), int(m.group("hit")), int(m.group("miss")))
                continue
            for key, rx in (("total_errors", RE_TOTAL_ERR),
                            ("pages_retired", RE_PAGES_RETIRED),
                            ("baseline_retired", RE_BASELINE_RETIRED),
                            ("off_live", RE_OFF_LIVE)):
                m = rx.search(line)
                if m:
                    d[key] = int(m.group(1))
                    break
            else:
                m = RE_OFF_RETIRED.search(line)
                if m:
                    d["off_retired"] = int(m.group(1))
                    d["off_retired_pct"] = float(m.group(2))
    return d


def gmean(vals):
    vals = [v for v in vals if v is not None and v > 0]
    if not vals:
        return None
    return exp(sum(log(v) for v in vals) / len(vals))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--results", default=os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "..",
        "results", "multicore", "1_error_rate_sweep"))
    ap.add_argument("--out-prefix", default=os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "multicore_exp1"))
    args = ap.parse_args()

    results_dir = os.path.abspath(args.results)
    if not os.path.isdir(results_dir):
        sys.exit(f"results dir not found: {results_dir}")

    runs = {}  # (mix, scheme) -> parsed
    for fname in sorted(os.listdir(results_dir)):
        m = RE_FNAME.match(fname)
        if not m:
            continue
        runs[(m.group("mix"), m.group("scheme"))] = parse_file(
            os.path.join(results_dir, fname))

    if not runs:
        sys.exit(f"no result files matched in {results_dir}")

    percpu_rows, summary_rows = [], []
    for mix in MIX_ORDER:
        noerr = runs.get((mix, "noerr"))
        for scheme in SCHEME_ORDER:
            r = runs.get((mix, scheme))
            if r is None:
                continue
            rate = "" if scheme == "noerr" else scheme.split("_")[1]
            pin_mode = ("none" if scheme == "noerr"
                        else "off" if scheme.startswith("off") else "on")
            complete = len(r["complete_cpus"]) == NUM_CPUS

            norms = []
            for c in range(NUM_CPUS):
                ipc = r["cpu_ipc"].get(c)
                instr = r["cpu_instr"].get(c)
                llc = r["cpu_llc"].get(c)
                err = r["cpu_err"].get(c, {})
                base_ipc = noerr["cpu_ipc"].get(c) if noerr else None
                norm = (ipc / base_ipc) if (ipc and base_ipc) else None
                if norm is not None:
                    norms.append(norm)
                mpki = (llc[2] / (instr / 1000.0)) if (llc and instr) else None
                percpu_rows.append({
                    "mix": mix, "scheme": scheme, "pin_mode": pin_mode,
                    "error_rate": rate, "cpu": c,
                    "workload": MIXES[mix][c],
                    "ipc": ipc, "norm_ipc_vs_noerr": norm,
                    "instructions": instr, "cycles": r["cpu_cycles"].get(c),
                    "llc_mpki": mpki,
                    "err_absorbed": err.get("absorbed"),
                    "err_first": err.get("first"), "err_added": err.get("added"),
                    "err_known": err.get("known"), "err_retired": err.get("retired"),
                    "err_baseline_retired": err.get("bretired"),
                    "completed": complete,
                })

            sum_ipc = (sum(r["cpu_ipc"].values())
                       if len(r["cpu_ipc"]) == NUM_CPUS else None)
            noerr_sum = (sum(noerr["cpu_ipc"].values())
                         if noerr and len(noerr["cpu_ipc"]) == NUM_CPUS else None)
            summary_rows.append({
                "mix": mix, "scheme": scheme, "pin_mode": pin_mode,
                "error_rate": rate,
                "sum_ipc": sum_ipc,
                "weighted_speedup": (sum(norms) if len(norms) == NUM_CPUS else None),
                "gmean_norm_ipc": (gmean(norms) if len(norms) == NUM_CPUS else None),
                "norm_throughput": (sum_ipc / noerr_sum
                                    if sum_ipc and noerr_sum else None),
                "total_errors": r["total_errors"],
                "pages_retired": r["pages_retired"],
                "baseline_retired": r["baseline_retired"],
                "off_retired_lines": r["off_retired"],
                "off_retired_pct": r["off_retired_pct"],
                "off_live_lines": r["off_live"],
                "sim_seconds": r["sim_seconds"],
                "completed": len(r["complete_cpus"]) == NUM_CPUS,
            })

    for suffix, rows in (("percpu", percpu_rows), ("summary", summary_rows)):
        path = f"{args.out_prefix}_{suffix}.csv"
        with open(path, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            w.writeheader()
            w.writerows(rows)
        print(f"wrote {path} ({len(rows)} rows)")

    # Console pivot: weighted speedup (mix x scheme)
    print(f"\nWeighted speedup (sum of per-CPU IPC / noerr IPC, max {NUM_CPUS}.0)")
    hdr = ["mix"] + [s for s in SCHEME_ORDER if s != "noerr"]
    print("  " + "".join(f"{h:>11}" for h in hdr))
    by_key = {(row["mix"], row["scheme"]): row for row in summary_rows}
    for mix in MIX_ORDER:
        if not any((mix, s) in by_key for s in SCHEME_ORDER):
            continue
        cells = [f"{mix:>5}"]
        for s in hdr[1:]:
            row = by_key.get((mix, s))
            if row is None:
                cells.append(f"{'-':>11}")
            elif row["weighted_speedup"] is None:
                cells.append(f"{'inc':>11}")
            else:
                flag = "" if row["completed"] else "*"
                cells.append(f"{row['weighted_speedup']:>10.3f}{flag or ' '}")
        print("  " + "".join(cells))
    print("  (*: incomplete run — not all CPUs reached Simulation complete)")


if __name__ == "__main__":
    main()
