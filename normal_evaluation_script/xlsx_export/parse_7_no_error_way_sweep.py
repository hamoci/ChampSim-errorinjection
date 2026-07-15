#!/usr/bin/env python3
"""Parse 7_no_error_way_sweep results into a self-contained XLSX.

Input  : results/normal_evaluation/7_no_error_way_sweep/
         noerr_{llc_size}_w{ways}_{trace}.txt
Output : parse_7_no_error_way_sweep.{csv,xlsx}

This experiment runs each workload with NO DRAM errors, sweeping LLC
capacity (associativity) at two sizes (2MB, 4MB) with ways {8..16}. It
provides the no-error reference baseline for capacity studies. Only IPC
and LLC MPKI are meaningful here.
"""

import os
import re
import sys

import pandas as pd
from openpyxl.styles import Alignment

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
NORMAL_SCRIPT_DIR = os.path.dirname(SCRIPT_DIR)
REPO_DIR = os.path.dirname(NORMAL_SCRIPT_DIR)
RESULTS_DIR = os.path.join(REPO_DIR, "results", "normal_evaluation",
                           "7_no_error_way_sweep")
OUTPUT_CSV = os.path.join(SCRIPT_DIR, "parse_7_no_error_way_sweep.csv")
OUTPUT_XLSX = os.path.join(SCRIPT_DIR, "parse_7_no_error_way_sweep.xlsx")

if NORMAL_SCRIPT_DIR not in sys.path:
    sys.path.insert(0, NORMAL_SCRIPT_DIR)
from common_normal import extract_workload  # noqa: E402

RE_NAME = re.compile(
    r"^noerr_(?P<llc_size>\d+MB)_w(?P<ways>\d+)_(?P<trace>.+)\.txt$"
)
RE_IPC = re.compile(
    r"CPU 0 cumulative IPC:\s+([\d.]+)\s+instructions:\s*(\d+)\s+cycles:\s*(\d+)"
)
RE_LLC = re.compile(
    r"cpu0->LLC TOTAL\s+ACCESS:\s+(\d+)\s+HIT:\s+(\d+)\s+MISS:\s+(\d+)"
)


def parse_file(path, llc_size, ways, trace):
    try:
        with open(path, "r") as f:
            txt = f.read()
    except Exception as e:
        print(f"WARN read failed {path}: {e}", file=sys.stderr)
        return None

    row = {
        "workload": extract_workload(trace),
        "llc_size": llc_size,
        "llc_ways": int(ways),
        "ipc": None,
        "llc_mpki": None,
    }
    m = RE_IPC.search(txt)
    instructions = None
    if m:
        row["ipc"] = float(m.group(1))
        instructions = int(m.group(2))
    m = RE_LLC.search(txt)
    if m and instructions and instructions > 0:
        llc_miss = int(m.group(3))
        row["llc_mpki"] = llc_miss / instructions * 1000.0
    return row


COLUMN_DOCS = [
    ("workload",
     "SPEC CPU2017 트레이스 이름 (예: 605.mcf_s)."),
    ("llc_size",
     "LLC 총 용량 (2MB 또는 4MB)."),
    ("llc_ways",
     "LLC associativity (set당 way 수). {8, 9, ..., 16} 범위에서 스윕."),
    ("ipc",
     "시뮬레이션 종료 시점 CPU 0 누적 IPC (에러 없는 베이스라인)."),
    ("llc_mpki",
     "1000개 instruction당 LLC miss 수 (에러 없는 베이스라인)."),
]


def write_xlsx(df):
    with pd.ExcelWriter(OUTPUT_XLSX, engine="openpyxl") as w:
        df.to_excel(w, sheet_name="data", index=False)
        readme = pd.DataFrame(COLUMN_DOCS, columns=["column", "description"])
        readme.to_excel(w, sheet_name="README", index=False)

        wb = w.book
        ws = wb["data"]
        ws.freeze_panes = "A2"
        widths = {"workload": 18, "llc_size": 10, "llc_ways": 10,
                  "ipc": 9, "llc_mpki": 11}
        for col_idx, col_name in enumerate(df.columns, start=1):
            letter = ws.cell(row=1, column=col_idx).column_letter
            ws.column_dimensions[letter].width = widths.get(col_name, 14)

        ws_r = wb["README"]
        ws_r.column_dimensions["A"].width = 14
        ws_r.column_dimensions["B"].width = 90
        for cell in ws_r["B"]:
            cell.alignment = Alignment(wrap_text=True, vertical="top")


def main():
    if not os.path.isdir(RESULTS_DIR):
        raise SystemExit(f"Results dir not found: {RESULTS_DIR}")

    rows = []
    skipped = 0
    for fname in sorted(os.listdir(RESULTS_DIR)):
        m = RE_NAME.match(fname)
        if not m:
            skipped += 1
            continue
        row = parse_file(
            os.path.join(RESULTS_DIR, fname),
            m.group("llc_size"), m.group("ways"), m.group("trace"),
        )
        if row is not None:
            rows.append(row)

    df = pd.DataFrame(rows)
    df.sort_values(by=["llc_size", "workload", "llc_ways"], inplace=True)
    df.reset_index(drop=True, inplace=True)
    df.to_csv(OUTPUT_CSV, index=False)
    write_xlsx(df)

    print(f"Parsed {len(df)} rows (skipped {skipped} non-matching files)")
    print(f"  llc_sizes: {sorted(df['llc_size'].unique())}")
    print(f"  llc_ways : {sorted(df['llc_ways'].unique())}")
    print(f"  workloads: {len(df['workload'].unique())}")
    print(f"CSV : {OUTPUT_CSV}")
    print(f"XLSX: {OUTPUT_XLSX}")


if __name__ == "__main__":
    main()
