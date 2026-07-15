#!/usr/bin/env python3
"""Parse 2_retirement_threshold results into a self-contained XLSX.

Input  : results/normal_evaluation/2_retirement_threshold/
         retire_{off|on}_{threshold}_{rate}_{trace}.txt
Output : parse_2_retirement_threshold.{csv,xlsx}
         (CSV mirrors the data sheet; XLSX adds a README sheet.)

Designed so a reader with no prior knowledge of the experiment can plot
"% of error cache lines protected" vs (workload, error_rate, threshold,
pin_mode) directly from these columns.
"""

import os
import re
import sys

import pandas as pd

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
NORMAL_SCRIPT_DIR = os.path.dirname(SCRIPT_DIR)
REPO_DIR = os.path.dirname(NORMAL_SCRIPT_DIR)
RESULTS_DIR = os.path.join(REPO_DIR, "results", "normal_evaluation",
                           "2_retirement_threshold")
OUTPUT_CSV = os.path.join(SCRIPT_DIR, "parse_2_retirement_threshold.csv")
OUTPUT_XLSX = os.path.join(SCRIPT_DIR, "parse_2_retirement_threshold.xlsx")

if NORMAL_SCRIPT_DIR not in sys.path:
    sys.path.insert(0, NORMAL_SCRIPT_DIR)
from common_normal import extract_workload  # noqa: E402

RE_NAME = re.compile(
    r"^retire_(?P<mode>off|on)_(?P<thresh>\d+)_(?P<rate>1e-\d+)_(?P<trace>.+)\.txt$"
)

RE_IPC = re.compile(
    r"CPU 0 cumulative IPC:\s+([\d.]+)\s+instructions:\s*(\d+)\s+cycles:\s*(\d+)"
)
RE_LLC = re.compile(
    r"cpu0->LLC TOTAL\s+ACCESS:\s+(\d+)\s+HIT:\s+(\d+)\s+MISS:\s+(\d+)"
)

# pin_off
RE_OFF_TOTAL_ERR_ACCESSES = re.compile(r"Total Error Accesses:\s+(\d+)")
RE_OFF_PAGES_RETIRED = re.compile(r"Baseline Page Retirements:\s+(\d+)")
RE_OFF_TOTAL_KNOWN = re.compile(r"\[LLC\]\s+Total Known Error Addresses:\s+(\d+)")
RE_OFF_RETIRED_LINES = re.compile(
    r"Retired \(page offline\):\s+(\d+)\s+\(([\d.]+)%\)"
)
RE_OFF_LIVE_LINES = re.compile(r"Live \(still tracked\):\s+(\d+)")

# pin_on
RE_ON_TOTAL_KNOWN = re.compile(r"\[LLC\]\s+Total Known Error Addresses:\s+(\d+)")
RE_ON_PINNED = re.compile(r"Pinned in Error Way:\s+(\d+)\s+\(([\d.]+)%\)")
RE_ON_TOTAL_DRAM_EVENTS = re.compile(r"Total DRAM Error Events:\s+(\d+)")
RE_ON_PAGES_RETIRED = re.compile(r"\[ERROR\]\s+Pages Retired:\s+(\d+)")
RE_ON_MAX_ERROR_WAYS = re.compile(r"Max Error Ways per Set:\s+(\d+)")


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


def parse_file(path, mode, thresh, rate, trace):
    try:
        with open(path, "r") as f:
            txt = f.read()
    except Exception as e:
        print(f"WARN read failed {path}: {e}", file=sys.stderr)
        return None

    row = {
        "workload": extract_workload(trace),
        "pin_mode": mode,
        "error_rate": rate,
        "retirement_threshold": int(thresh),
        "max_error_way": None,
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

    if mode == "off":
        row["total_error_events"] = _last_int(RE_OFF_TOTAL_ERR_ACCESSES, txt)
        row["pages_retired"] = _last_int(RE_OFF_PAGES_RETIRED, txt)
        m = _last_match(RE_OFF_RETIRED_LINES, txt)
        retired_lines = int(m.group(1)) if m else None
        live_lines = _last_int(RE_OFF_LIVE_LINES, txt)
        row["live_error_lines"] = live_lines
        # pinned_lines stays None (no pinning in off mode)
        if retired_lines is not None and live_lines is not None:
            total = retired_lines + live_lines
            row["total_error_lines"] = total
            row["protected_lines"] = retired_lines
            if total > 0:
                row["protected_lines_pct"] = 100.0 * retired_lines / total
    else:  # "on"
        row["max_error_way"] = _last_int(RE_ON_MAX_ERROR_WAYS, txt)
        events = _last_int(RE_ON_TOTAL_DRAM_EVENTS, txt)
        live = _last_int(RE_ON_TOTAL_KNOWN, txt)
        m = _last_match(RE_ON_PINNED, txt)
        pinned = int(m.group(1)) if m else None
        row["total_error_events"] = events
        row["pages_retired"] = _last_int(RE_ON_PAGES_RETIRED, txt)
        row["live_error_lines"] = live
        row["pinned_lines"] = pinned
        if events is not None and live is not None and pinned is not None:
            # Errors recorded but no longer tracked (= invalidated by page
            # retirement) are inferred as: events - live, clamped at 0.
            retired_lines_est = max(events - live, 0)
            total = live + retired_lines_est
            protected = pinned + retired_lines_est
            row["total_error_lines"] = total
            row["protected_lines"] = protected
            if total > 0:
                row["protected_lines_pct"] = 100.0 * protected / total

    return row


COLUMN_DOCS = [
    ("workload",
     "SPEC CPU2017 트레이스 이름 (예: 605.mcf_s). 실행한 워크로드 식별자."),
    ("pin_mode",
     "'off' = 페이지 retirement만 사용 (LLC pinning 없음). "
     "'on'  = LLC error-way pinning + 페이지 retirement."),
    ("error_rate",
     "DRAM cell 단위로 설정된 uncorrectable bit-error rate "
     "(1e-5 = 가장 높음, 1e-8 = 가장 낮음)."),
    ("retirement_threshold",
     "한 페이지에 누적된 에러 이벤트 수가 이 값에 도달하면 페이지를 "
     "offline 시킴 (retire)."),
    ("max_error_way",
     "pin_mode='on'일 때: 에러 라인 pinning을 위해 LLC set당 예약할 수 "
     "있는 최대 way 수 (error_way 할당이 늘어날 수 있는 상한). "
     "pin_mode='off'에서는 빈 값."),
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
     "에러 cache line 수. 원시 입력값 — 파일에서 직접 파싱. "
     "pin_off: 'Live (still tracked)'에서 추출. "
     "pin_on: 'Total Known Error Addresses'에서 추출 (pin_on에서는 이 "
     "필드가 live만 카운트함 — retire된 페이지의 라인은 이미 제거됨)."),
    ("pinned_lines",
     "LLC error way에 고정(pin)되어 있는 에러 cache line 수. "
     "원시 입력값 — 'Pinned in Error Way'에서 파싱. "
     "pin_mode='off'에서는 항상 빈 값 (pinning 개념 없음)."),
    ("total_error_lines",
     "최소 1번 이상 에러를 겪은 unique LLC cache line의 누적 합계 "
     "(이후 retire된 페이지에 속한 라인도 포함).\n"
     "  pin_off: total_error_lines = live_error_lines + retired_lines\n"
     "           (retired_lines는 'Retired (page offline)'에서 파싱)\n"
     "  pin_on:  total_error_lines = live_error_lines + retired_lines_est\n"
     "           여기서 retired_lines_est = max(total_error_events - "
     "live_error_lines, 0)\n"
     "  (pin_on은 파일이 retire된 라인을 더 이상 트래킹하지 않아 역산함. "
     "그래서 pin_on에서는 total_error_lines == total_error_events.)"),
    ("protected_lines",
     "total_error_lines 중 보호된 라인 수 (잘못된 데이터가 CPU에 노출되지 "
     "않는 라인).\n"
     "  pin_off: protected_lines = total_error_lines - live_error_lines\n"
     "           (= retired_lines; retirement만이 보호 수단)\n"
     "  pin_on:  protected_lines = pinned_lines + retired_lines_est"),
    ("protected_lines_pct",
     "'Protected Lines (%)' 플롯의 기본 y축 지표.\n"
     "  protected_lines_pct = protected_lines / total_error_lines * 100"),
]


def write_xlsx(df):
    with pd.ExcelWriter(OUTPUT_XLSX, engine="openpyxl") as w:
        df.to_excel(w, sheet_name="data", index=False)
        readme = pd.DataFrame(COLUMN_DOCS, columns=["column", "description"])
        readme.to_excel(w, sheet_name="README", index=False)

        # Light formatting: freeze header, widen columns.
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
        from openpyxl.styles import Alignment
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
            m.group("mode"), m.group("thresh"),
            m.group("rate"), m.group("trace"),
        )
        if row is not None:
            rows.append(row)

    df = pd.DataFrame(rows)
    df.sort_values(
        by=["pin_mode", "workload", "error_rate", "retirement_threshold"],
        inplace=True,
    )
    df.reset_index(drop=True, inplace=True)

    df.to_csv(OUTPUT_CSV, index=False)
    write_xlsx(df)

    print(f"Parsed {len(df)} rows (skipped {skipped} non-matching files)")
    print(f"  pin_off: {(df['pin_mode']=='off').sum()}")
    print(f"  pin_on : {(df['pin_mode']=='on').sum()}")
    print(f"CSV : {OUTPUT_CSV}")
    print(f"XLSX: {OUTPUT_XLSX}")


if __name__ == "__main__":
    main()
