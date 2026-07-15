#!/usr/bin/env python3
"""Parse 3_error_way_capacity results into a self-contained XLSX.

Input  : results/normal_evaluation/3_error_way_capacity/
         errway_{max_ways}w_{rate}_{trace}.txt
Output : parse_3_error_way_capacity.{csv,xlsx}

This experiment sweeps the LLC Max Error Ways per Set ({1, 2, 4, 8}) at
4 error rates (1e-5 .. 1e-8). Retirement threshold is fixed at 32 and
pin_mode is always 'on'. Schema matches parse_2_retirement_threshold for
easy side-by-side comparison.
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
                           "3_error_way_capacity")
OUTPUT_CSV = os.path.join(SCRIPT_DIR, "parse_3_error_way_capacity.csv")
OUTPUT_XLSX = os.path.join(SCRIPT_DIR, "parse_3_error_way_capacity.xlsx")

if NORMAL_SCRIPT_DIR not in sys.path:
    sys.path.insert(0, NORMAL_SCRIPT_DIR)
from common_normal import extract_workload  # noqa: E402

RE_NAME = re.compile(
    r"^errway_(?P<ways>\d+)w_(?P<rate>1e-\d+)_(?P<trace>.+)\.txt$"
)

RE_IPC = re.compile(
    r"CPU 0 cumulative IPC:\s+([\d.]+)\s+instructions:\s*(\d+)\s+cycles:\s*(\d+)"
)
RE_LLC = re.compile(
    r"cpu0->LLC TOTAL\s+ACCESS:\s+(\d+)\s+HIT:\s+(\d+)\s+MISS:\s+(\d+)"
)
RE_TOTAL_KNOWN = re.compile(r"\[LLC\]\s+Total Known Error Addresses:\s+(\d+)")
RE_PINNED = re.compile(r"Pinned in Error Way:\s+(\d+)\s+\(([\d.]+)%\)")
RE_TOTAL_DRAM_EVENTS = re.compile(r"Total DRAM Error Events:\s+(\d+)")
RE_PAGES_RETIRED = re.compile(r"\[ERROR\]\s+Pages Retired:\s+(\d+)")
RE_THRESH = re.compile(r"\[ERROR\]\s+Retirement Threshold:\s+(\d+)")
RE_MAX_ERROR_WAYS = re.compile(r"Max Error Ways per Set:\s+(\d+)")


def _last_int(regex, txt):
    matches = regex.findall(txt)
    if not matches:
        return None
    val = matches[-1]
    if isinstance(val, tuple):
        val = val[0]
    return int(val)


def _last_match(regex, txt):
    matches = list(regex.finditer(txt))
    return matches[-1] if matches else None


def parse_file(path, ways_from_name, rate, trace):
    try:
        with open(path, "r") as f:
            txt = f.read()
    except Exception as e:
        print(f"WARN read failed {path}: {e}", file=sys.stderr)
        return None

    row = {
        "workload": extract_workload(trace),
        "pin_mode": "on",
        "error_rate": rate,
        "retirement_threshold": _last_int(RE_THRESH, txt),
        "max_error_way": _last_int(RE_MAX_ERROR_WAYS, txt),
        "ipc": None,
        "llc_mpki": None,
        "total_error_events": None,
        "pages_retired": None,
        "live_error_lines": None,
        "pinned_lines": None,
        "total_error_lines": None,
        "protected_lines": None,
        "protected_lines_pct": None,
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

    events = _last_int(RE_TOTAL_DRAM_EVENTS, txt)
    live = _last_int(RE_TOTAL_KNOWN, txt)
    pm = _last_match(RE_PINNED, txt)
    pinned = int(pm.group(1)) if pm else None
    row["total_error_events"] = events
    row["pages_retired"] = _last_int(RE_PAGES_RETIRED, txt)
    row["live_error_lines"] = live
    row["pinned_lines"] = pinned
    if events is not None and live is not None and pinned is not None:
        retired_lines_est = max(events - live, 0)
        total = live + retired_lines_est
        protected = pinned + retired_lines_est
        row["total_error_lines"] = total
        row["protected_lines"] = protected
        if total > 0:
            row["protected_lines_pct"] = 100.0 * protected / total

    # Cross-check filename-encoded ways matches file content.
    if row["max_error_way"] is not None and \
            int(ways_from_name) != row["max_error_way"]:
        print(f"WARN ways mismatch in {path}: filename={ways_from_name}, "
              f"file={row['max_error_way']}", file=sys.stderr)

    return row


COLUMN_DOCS = [
    ("workload",
     "SPEC CPU2017 트레이스 이름 (예: 605.mcf_s)."),
    ("pin_mode",
     "이 실험에서는 항상 'on' (LLC error-way pinning 활성화). "
     "다른 실험과의 스키마 호환을 위해 컬럼 유지."),
    ("error_rate",
     "DRAM cell 단위로 설정된 uncorrectable bit-error rate "
     "(1e-5 = 가장 높음, 1e-8 = 가장 낮음)."),
    ("retirement_threshold",
     "한 페이지에 누적된 에러 이벤트 수가 이 값에 도달하면 페이지를 "
     "offline 시킴. 이 실험에서는 32로 고정."),
    ("max_error_way",
     "에러 라인 pinning을 위해 LLC set당 예약할 수 있는 최대 way 수. "
     "이 실험에서 스윕하는 변수: {1, 2, 4, 8}."),
    ("ipc",
     "시뮬레이션 종료 시점 CPU 0 누적 IPC (instructions per cycle)."),
    ("llc_mpki",
     "1000개 instruction당 LLC miss 수 (메모리 계층의 부하 지표)."),
    ("total_error_events",
     "측정 구간 동안 주입된 전체 DRAM 에러 이벤트 수 "
     "(같은 cache line에 여러 번 떨어지면 중복 카운트됨)."),
    ("pages_retired",
     "retirement_threshold에 도달해 offline된 고유 DRAM 페이지 수."),
    ("live_error_lines",
     "현재 LLC에서 아직 트래킹 중인 (retire되지 않은 페이지에 속한) "
     "에러 cache line 수. 원시 입력값 — 'Total Known Error Addresses'"
     "에서 파싱 (pin_on에서는 이 필드가 live만 카운트함 — retire된 "
     "페이지의 라인은 이미 제거됨)."),
    ("pinned_lines",
     "LLC error way에 고정(pin)되어 있는 에러 cache line 수. "
     "원시 입력값 — 'Pinned in Error Way'에서 파싱."),
    ("total_error_lines",
     "최소 1번 이상 에러를 겪은 unique LLC cache line의 누적 합계 "
     "(이후 retire된 페이지에 속한 라인도 포함).\n"
     "  total_error_lines = live_error_lines + retired_lines_est\n"
     "    여기서 retired_lines_est = max(total_error_events - "
     "live_error_lines, 0)\n"
     "  (파일이 retire된 라인을 더 이상 트래킹하지 않아 역산함. "
     "그래서 total_error_lines == total_error_events.)"),
    ("protected_lines",
     "total_error_lines 중 보호된 라인 수 (잘못된 데이터가 CPU에 노출되지 "
     "않는 라인).\n"
     "  protected_lines = pinned_lines + retired_lines_est"),
    ("protected_lines_pct",
     "'Protected Lines (%)' 플롯의 기본 y축 지표.\n"
     "  protected_lines_pct = protected_lines / total_error_lines * 100"),
]


def write_xlsx(df):
    with pd.ExcelWriter(OUTPUT_XLSX, engine="openpyxl") as w:
        df.to_excel(w, sheet_name="data", index=False)
        readme = pd.DataFrame(COLUMN_DOCS, columns=["column", "description"])
        readme.to_excel(w, sheet_name="README", index=False)

        wb = w.book
        ws = wb["data"]
        ws.freeze_panes = "A2"
        widths = {
            "workload": 18, "pin_mode": 9, "error_rate": 10,
            "retirement_threshold": 20, "max_error_way": 14,
            "ipc": 8, "llc_mpki": 10,
            "total_error_events": 18, "pages_retired": 14,
            "live_error_lines": 16, "pinned_lines": 13,
            "total_error_lines": 18, "protected_lines": 16,
            "protected_lines_pct": 20,
        }
        for col_idx, col_name in enumerate(df.columns, start=1):
            letter = ws.cell(row=1, column=col_idx).column_letter
            ws.column_dimensions[letter].width = widths.get(col_name, 14)

        ws_r = wb["README"]
        ws_r.column_dimensions["A"].width = 22
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
            m.group("ways"), m.group("rate"), m.group("trace"),
        )
        if row is not None:
            rows.append(row)

    df = pd.DataFrame(rows)
    df.sort_values(
        by=["max_error_way", "workload", "error_rate"],
        inplace=True,
    )
    df.reset_index(drop=True, inplace=True)

    df.to_csv(OUTPUT_CSV, index=False)
    write_xlsx(df)

    print(f"Parsed {len(df)} rows (skipped {skipped} non-matching files)")
    print(f"  unique max_error_way: {sorted(df['max_error_way'].dropna().unique().tolist())}")
    print(f"  unique error_rate:    {sorted(df['error_rate'].unique())}")
    print(f"  unique threshold:     {sorted(df['retirement_threshold'].dropna().unique().tolist())}")
    print(f"  workloads: {len(df['workload'].unique())}")
    print(f"CSV : {OUTPUT_CSV}")
    print(f"XLSX: {OUTPUT_XLSX}")


if __name__ == "__main__":
    main()
