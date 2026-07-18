#!/usr/bin/env python3
"""Compare multicore Exp1 uniform vs clustered fault injection.

Inputs : results/multicore/1_error_rate_sweep/           (uniform, incl. noerr baseline)
         results/multicore/1_error_rate_sweep_clustered/ (champsim_4core_8mb_{off,pin}_clu_{rate}_{MIX}.txt)
Outputs: stat_script_rev/multicore_clu_compare_summary.csv (one row per mix/scheme/rate/model)
         console markdown pivots (weighted speedup, retirements, spatial stats)

Weighted speedup uses the SAME-mix uniform noerr run as the alone-reference
for both models (noerr has no injection, so it is model-independent).
Reuses parse_file/MIXES from parse_multicore_exp1.py.
"""

import csv
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from parse_multicore_exp1 import parse_file, MIX_ORDER, gmean  # noqa: E402

BASE = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
UNI_DIR = os.path.join(BASE, "results", "multicore", "1_error_rate_sweep")
CLU_DIR = os.path.join(BASE, "results", "multicore", "1_error_rate_sweep_clustered")

RATES = ["1e-7", "1e-8"]
SCHEMES = ["off", "pin"]

RE_UNI = re.compile(r"^champsim_4core_8mb_(?P<scheme>off|pin)_(?P<rate>1e-\d)_(?P<mix>[MCH]\d)\.txt$")
RE_NOERR = re.compile(r"^champsim_4core_8mb_noerr_(?P<mix>[MCH]\d)\.txt$")
RE_CLU = re.compile(r"^champsim_4core_8mb_(?P<scheme>off|pin)_clu_(?P<rate>1e-\d)_(?P<mix>[MCH]\d)\.txt$")

# Clustered-only spatial stats
SPATIAL_RES = {
    "faults": re.compile(r"Faults Created:\s+(\d+) \(cell=(\d+) row=(\d+) bank=(\d+)\)"),
    "killed": re.compile(r"Faults Killed by Retirement:\s+(\d+)"),
    "manifests": re.compile(r"Manifestations \(injected CEs\):\s+(\d+)"),
    "retired_perm": re.compile(r"Retired Pages \(permanent\):\s+(\d+)"),
    "top1": re.compile(r"Top-1 Bank Share:\s+([\d.]+)%"),
    "distinct": re.compile(r"Distinct Lines / Rows / Banks:\s+(\d+) / (\d+) / (\d+)"),
    "per_line_max": re.compile(r"Errors per Line \(avg/max\):\s+[\d.]+ / (\d+)"),
    "per_row_max": re.compile(r"Errors per Row \(avg/max\):\s+[\d.]+ / (\d+)"),
    "any_widened": re.compile(r"Starved -> Any-Widened:\s+(\d+)"),
}


def parse_spatial(path):
    out = {}
    with open(path, errors="replace") as f:
        text = f.read()
    for key, rx in SPATIAL_RES.items():
        m = rx.search(text)
        if not m:
            continue
        out[key] = [float(g) if "." in g else int(g) for g in m.groups()] if len(m.groups()) > 1 \
            else (float(m.group(1)) if "." in m.group(1) else int(m.group(1)))
    return out


def collect(dirpath, fname_re, model):
    runs = {}
    if not os.path.isdir(dirpath):
        return runs
    for fname in sorted(os.listdir(dirpath)):
        m = fname_re.match(fname)
        if not m:
            continue
        path = os.path.join(dirpath, fname)
        d = parse_file(path)
        if len(d["complete_cpus"]) < 4:
            print(f"  [incomplete] {fname}", file=sys.stderr)
            continue
        key = (m.group("mix"), m.group("scheme"), m.group("rate"))
        d["model"] = model
        if model == "clustered":
            d["spatial"] = parse_spatial(path)
        runs[key] = d
    return runs


def main():
    noerr = {}
    for fname in sorted(os.listdir(UNI_DIR)):
        m = RE_NOERR.match(fname)
        if m:
            d = parse_file(os.path.join(UNI_DIR, fname))
            if len(d["complete_cpus"]) == 4:
                noerr[m.group("mix")] = d

    uni = collect(UNI_DIR, RE_UNI, "uniform")
    clu = collect(CLU_DIR, RE_CLU, "clustered")
    print(f"parsed: noerr={len(noerr)} uniform={len(uni)} clustered={len(clu)}", file=sys.stderr)

    rows = []
    for model, runs in (("uniform", uni), ("clustered", clu)):
        for (mix, scheme, rate), d in sorted(runs.items()):
            if rate not in RATES:
                continue
            base = noerr.get(mix)
            ws = None
            if base:
                ratios = [d["cpu_ipc"].get(c, 0) / base["cpu_ipc"][c]
                          for c in range(4) if base["cpu_ipc"].get(c)]
                ws = sum(ratios) if len(ratios) == 4 else None
            absorbed = [d["cpu_err"].get(c, {}).get("absorbed", 0) for c in range(4)]
            row = {
                "mix": mix, "scheme": scheme, "rate": rate, "model": model,
                "weighted_speedup": round(ws, 4) if ws else None,
                "total_errors": d.get("total_errors"),
                "pages_retired": d.get("pages_retired"),
                "baseline_retired": d.get("baseline_retired"),
                "absorbed_max_share": round(max(absorbed) / sum(absorbed), 3) if sum(absorbed) else None,
            }
            sp = d.get("spatial", {})
            if sp:
                faults = sp.get("faults")
                row.update({
                    "faults_total": faults[0] if faults else None,
                    "faults_killed": sp.get("killed"),
                    "manifests": sp.get("manifests"),
                    "retired_perm": sp.get("retired_perm"),
                    "top1_bank_pct": sp.get("top1"),
                    "distinct_lines": sp.get("distinct", [None]*3)[0],
                    "per_line_max": sp.get("per_line_max"),
                    "per_row_max": sp.get("per_row_max"),
                    "any_widened": sp.get("any_widened"),
                })
            rows.append(row)

    out_csv = os.path.join(os.path.dirname(os.path.abspath(__file__)), "multicore_clu_compare_summary.csv")
    fields = ["mix", "scheme", "rate", "model", "weighted_speedup", "total_errors",
              "pages_retired", "baseline_retired", "absorbed_max_share",
              "faults_total", "faults_killed", "manifests", "retired_perm",
              "top1_bank_pct", "distinct_lines", "per_line_max", "per_row_max", "any_widened"]
    with open(out_csv, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for r in rows:
            w.writerow(r)
    print(f"wrote {out_csv} ({len(rows)} rows)", file=sys.stderr)

    # Markdown pivot: weighted speedup uniform vs clustered
    for scheme in SCHEMES:
        for rate in RATES:
            print(f"\n### {scheme} @ {rate} — weighted speedup (uniform vs clustered, Δ)")
            print("| mix | uniform | clustered | Δ (clu−uni) |")
            print("|---|---|---|---|")
            deltas = []
            for mix in MIX_ORDER:
                u = next((r for r in rows if r["model"] == "uniform" and r["mix"] == mix
                          and r["scheme"] == scheme and r["rate"] == rate), None)
                c = next((r for r in rows if r["model"] == "clustered" and r["mix"] == mix
                          and r["scheme"] == scheme and r["rate"] == rate), None)
                uws = u["weighted_speedup"] if u else None
                cws = c["weighted_speedup"] if c else None
                dl = round(cws - uws, 4) if (uws and cws) else None
                if dl is not None:
                    deltas.append(dl)
                print(f"| {mix} | {uws or '—'} | {cws or '—'} | {dl if dl is not None else '—'} |")
            if deltas:
                print(f"| **avg** | | | **{round(sum(deltas)/len(deltas), 4)}** |")


if __name__ == "__main__":
    main()
