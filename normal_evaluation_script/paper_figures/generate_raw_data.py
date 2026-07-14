#!/usr/bin/env python3
"""
Generate raw_data.xlsx from results/normal_evaluation/ .txt files.

Output: raw_data.xlsx with three sheets:
  - "Threshold sweep"       — 2_retirement_threshold/ (pin_on and pin_off,
                              thresholds 2/4/8/16/32, rates 1e-5..1e-8)
  - "Max error way sweep"   — 6_llc_way_sweep/ filtered to llc_size=2MB
                              (pin_on, threshold=32, max_error_way 1/2/4/8,
                              rates 1e-5..1e-8)
  - "Way sweep in No error" — 7_no_error_way_sweep/ (llc_size 2MB/4MB,
                              llc_ways 8..16)
"""

import os
import re
from dataclasses import dataclass
from typing import Optional

from openpyxl import Workbook

from common_normal import extract_workload, suite_of

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
RESULTS_ROOT = os.path.join(SCRIPT_DIR, "results")
# GAP-suite results live under the repo's canonical results tree, not the
# paper_figures copy. We read SPEC from RESULTS_ROOT and GAP from whichever
# of (paper_figures/results, repo results) actually has the *_gap dir.
REPO_RESULTS = os.path.normpath(
    os.path.join(SCRIPT_DIR, "..", "..", "results", "normal_evaluation"))
OUTPUT_XLSX = os.path.join(SCRIPT_DIR, "raw_data.xlsx")


# Non-SPEC suites live in per-suite suffixed dirs (results tree convention):
# _gap (19 GAP traces), _xsbench / _llama / _redis (added real-world workloads).
SUITE_SUFFIXES = ("_gap", "_xsbench", "_llama", "_redis")


def resolve_sources(base_name, gap_name=None):
    """Return existing result dirs for an experiment: the SPEC dir (snapshot)
    plus each per-suite dir <base_name><suffix> (first location that exists,
    preferring the paper_figures snapshot over the repo results tree)."""
    dirs = []
    spec = os.path.join(RESULTS_ROOT, base_name)
    if os.path.isdir(spec):
        dirs.append(spec)
    for suffix in SUITE_SUFFIXES:
        name = base_name + suffix
        for cand in (os.path.join(RESULTS_ROOT, name),
                     os.path.join(REPO_RESULTS, name)):
            if os.path.isdir(cand):
                dirs.append(cand)
                break
    return dirs


def iter_result_files(dirs):
    """Yield (dirpath, filename) for every result dir, sorted by name."""
    for src in dirs:
        for fname in sorted(os.listdir(src)):
            yield src, fname

RE_IPC = re.compile(
    r"CPU 0 cumulative IPC:\s+([\d.]+)\s+instructions:\s*(\d+)\s+cycles:\s*(\d+)"
)
RE_LLC_MISS = re.compile(
    r"cpu0->LLC TOTAL\s+ACCESS:\s+(\d+)\s+HIT:\s+(\d+)\s+MISS:\s+(\d+)"
)
RE_TOTAL_KNOWN_ERR = re.compile(r"Total Known Error Addresses:\s+(\d+)")
RE_PINNED = re.compile(r"Pinned in Error Way:\s+(\d+)\s+\(([\d.]+)%\)")
RE_TOTAL_ERRORS = re.compile(r"Total DRAM Error Events:\s+(\d+)")
RE_PAGES_RETIRED = re.compile(r"Pages Retired:\s+(\d+)")
RE_BASELINE_PAGE_RETIRED = re.compile(r"Baseline Page Retirements:\s+(\d+)")
RE_PIN_OFF_RETIRED = re.compile(
    r"Retired \(page offline\):\s+(\d+)\s+\(([\d.]+)%\)"
)
RE_PIN_OFF_LIVE = re.compile(r"Live \(still tracked\):\s+(\d+)")


@dataclass
class Metrics:
    ipc: Optional[float] = None
    instructions: Optional[int] = None
    llc_miss: Optional[int] = None
    total_known_errors: Optional[int] = None
    pinned_count: Optional[int] = None
    total_dram_errors: Optional[int] = None
    pages_retired: Optional[int] = None
    baseline_page_retirements: Optional[int] = None
    pin_off_retired_count: Optional[int] = None
    pin_off_live_count: Optional[int] = None


def _set_int(obj, attr, regex, txt):
    match = regex.search(txt)
    if match:
        setattr(obj, attr, int(match.group(1)))


def extract_metrics(path: str) -> Metrics:
    try:
        with open(path, "r") as f:
            txt = f.read()
    except Exception:
        return Metrics()

    m = Metrics()

    match = RE_IPC.search(txt)
    if match:
        m.ipc = float(match.group(1))
        m.instructions = int(match.group(2))

    llc_match = RE_LLC_MISS.search(txt)
    if llc_match:
        m.llc_miss = int(llc_match.group(3))

    _set_int(m, "total_known_errors", RE_TOTAL_KNOWN_ERR, txt)
    pinned_match = RE_PINNED.search(txt)
    if pinned_match:
        m.pinned_count = int(pinned_match.group(1))

    _set_int(m, "total_dram_errors", RE_TOTAL_ERRORS, txt)
    _set_int(m, "pages_retired", RE_PAGES_RETIRED, txt)

    baseline_retire_matches = RE_BASELINE_PAGE_RETIRED.findall(txt)
    if baseline_retire_matches:
        m.baseline_page_retirements = int(baseline_retire_matches[-1])

    pin_off_match = RE_PIN_OFF_RETIRED.search(txt)
    if pin_off_match:
        m.pin_off_retired_count = int(pin_off_match.group(1))
    _set_int(m, "pin_off_live_count", RE_PIN_OFF_LIVE, txt)

    return m

DEFAULT_PIN_ON_MAX_WAY = 8

RE_RETIRE = re.compile(
    r"^retire_(?P<mode>on|off)_(?P<threshold>\d+)_(?P<rate>1e-\d+)_"
    r"(?P<trace>.+)\.txt$"
)
RE_SWEEP = re.compile(
    r"^sweep_(?P<llc_size>\d+MB)_w(?P<max_ways>\d+)_(?P<rate>1e-\d+)_"
    r"(?P<trace>.+)\.txt$"
)
RE_NOERR = re.compile(
    r"^noerr_(?P<llc_size>\d+MB)_w(?P<ways>\d+)_(?P<trace>.+)\.txt$"
)

THRESHOLD_HEADER = [
    "workload", "pin_mode", "error_rate", "retirement_threshold",
    "max_error_way", "ipc", "llc_mpki", "total_error_events",
    "pages_retired", "live_error_lines", "pinned_lines",
    "total_error_lines", "protected_lines", "protected_lines_pct",
    "suite", "completed",
]
MAX_WAY_HEADER = THRESHOLD_HEADER
NOERR_HEADER = ["workload", "llc_size", "llc_ways", "ipc", "llc_mpki",
                "suite", "completed"]

ERROR_RATE_ORDER = {"1e-5": 0, "1e-6": 1, "1e-7": 2, "1e-8": 3}
PIN_MODE_ORDER = {"off": 0, "on": 1}


def llc_mpki(m):
    if (m.llc_miss is None or m.instructions is None
            or m.instructions <= 0):
        return None
    return m.llc_miss / m.instructions * 1000.0


def threshold_row(m, workload, pin_mode, rate, threshold):
    # A run that produced no final IPC line did not complete (it panicked or
    # was truncated). Per the figure convention its IPC is treated as 0 in the
    # IPC geomean, while its page/coverage stats are dropped (NaN) so they
    # never pollute the page-count means.
    completed = m.ipc is not None
    suite = suite_of(workload)
    if pin_mode == "on":
        if m.ipc is None:
            return [workload, pin_mode, rate, threshold,
                    DEFAULT_PIN_ON_MAX_WAY, None, None, None, None, None, None,
                    None, None, None, suite, completed]
        pages = m.pages_retired
        live = m.total_known_errors
        pinned = m.pinned_count
        total_events = m.total_dram_errors
        if total_events is not None and live is not None:
            retired = max(0, total_events - live)
            total_lines = live + retired
            protected = (pinned + retired) if pinned is not None else retired
            pct = (100.0 * protected / total_lines) if total_lines > 0 else 0
        else:
            total_lines = None
            protected = None
            pct = None
        max_way = DEFAULT_PIN_ON_MAX_WAY
    else:
        pages = m.baseline_page_retirements
        live = m.pin_off_live_count
        pinned = None
        retired = m.pin_off_retired_count
        if live is not None and retired is not None:
            total_lines = live + retired
            total_events = total_lines
            protected = retired
            pct = (100.0 * protected / total_lines) if total_lines > 0 else 0
        else:
            total_lines = None
            total_events = None
            protected = None
            pct = None
        max_way = None

    return [
        workload, pin_mode, rate, threshold, max_way,
        m.ipc, llc_mpki(m), total_events, pages, live, pinned,
        total_lines, protected, pct, suite, completed,
    ]


# Canonical sweep points. 64/256 result files exist from one-off extreme-value
# tests and are deliberately excluded from the sheet.
THRESHOLD_SWEEP_POINTS = {2, 4, 8, 16, 32}


def collect_threshold_sweep():
    dirs = resolve_sources("2_retirement_threshold")
    rows = []
    for src, fname in iter_result_files(dirs):
        match = RE_RETIRE.match(fname)
        if not match:
            continue
        pin_mode = match.group("mode")
        threshold = int(match.group("threshold"))
        if threshold not in THRESHOLD_SWEEP_POINTS:
            continue
        rate = match.group("rate")
        workload = extract_workload(match.group("trace"))
        m = extract_metrics(os.path.join(src, fname))
        rows.append(threshold_row(m, workload, pin_mode, rate, threshold))
    rows.sort(key=lambda r: (
        PIN_MODE_ORDER.get(r[1], 99), r[0],
        ERROR_RATE_ORDER.get(r[2], 99), r[3],
    ))
    return rows


def collect_max_error_way_sweep():
    dirs = resolve_sources("6_llc_way_sweep")
    rows = []
    for src, fname in iter_result_files(dirs):
        match = RE_SWEEP.match(fname)
        if not match:
            continue
        if match.group("llc_size") != "2MB":
            continue
        max_way = int(match.group("max_ways"))
        rate = match.group("rate")
        workload = extract_workload(match.group("trace"))
        m = extract_metrics(os.path.join(src, fname))
        row = threshold_row(m, workload, "on", rate, 32)
        row[4] = max_way
        rows.append(row)
    rows.sort(key=lambda r: (
        r[4], r[0], ERROR_RATE_ORDER.get(r[2], 99),
    ))
    return rows


def collect_noerr_way_sweep():
    dirs = resolve_sources("7_no_error_way_sweep")
    rows = []
    for src, fname in iter_result_files(dirs):
        match = RE_NOERR.match(fname)
        if not match:
            continue
        llc_size = match.group("llc_size")
        ways = int(match.group("ways"))
        workload = extract_workload(match.group("trace"))
        m = extract_metrics(os.path.join(src, fname))
        rows.append([workload, llc_size, ways, m.ipc, llc_mpki(m),
                     suite_of(workload), m.ipc is not None])
    rows.sort(key=lambda r: (r[1], r[0], r[2]))
    return rows


# ── Multicore sheet (4-core SPEC mixes, results/multicore/1_error_rate_sweep) ──
# One row per (mix, scheme, cpu); mix-level metrics (weighted_speedup, sum_ipc,
# retirement totals) are repeated on each of the mix's four rows for easy
# pivoting. norm_ipc is against the same mix's noerr run, per cpu.
MULTICORE_DIR = os.path.join(REPO_RESULTS, "..", "multicore", "1_error_rate_sweep")

# CARE runs are still in flight; flip this to include care/care_scrub once done.
MULTICORE_SCHEMES = ("noerr",
                     "off_1e-6", "off_1e-7", "off_1e-8",
                     "pin_1e-6", "pin_1e-7", "pin_1e-8")

MULTICORE_MIXES = {
    "M1": ["605.mcf_s", "649.fotonik3d_s", "602.gcc_s", "603.bwaves_s"],
    "M2": ["605.mcf_s", "649.fotonik3d_s", "602.gcc_s", "620.omnetpp_s"],
    "M3": ["605.mcf_s", "649.fotonik3d_s", "603.bwaves_s", "620.omnetpp_s"],
    "M4": ["605.mcf_s", "602.gcc_s", "603.bwaves_s", "620.omnetpp_s"],
    "C1": ["623.xalancbmk_s", "628.pop2_s", "654.roms_s", "621.wrf_s"],
    "C2": ["623.xalancbmk_s", "628.pop2_s", "654.roms_s", "607.cactuBSSN_s"],
    "C3": ["623.xalancbmk_s", "628.pop2_s", "621.wrf_s", "607.cactuBSSN_s"],
    "C4": ["623.xalancbmk_s", "654.roms_s", "621.wrf_s", "607.cactuBSSN_s"],
    "H1": ["605.mcf_s", "649.fotonik3d_s", "623.xalancbmk_s", "628.pop2_s"],
    "H2": ["602.gcc_s", "620.omnetpp_s", "621.wrf_s", "654.roms_s"],
}
MULTICORE_MIX_ORDER = ["M1", "M2", "M3", "M4", "C1", "C2", "C3", "C4", "H1", "H2"]
MULTICORE_NUM_CPUS = 4

RE_MC_CPU_IPC = re.compile(
    r"^CPU (?P<cpu>\d) cumulative IPC:\s+(?P<ipc>[\d.]+)\s+instructions:\s*(?P<instr>\d+)")
RE_MC_COMPLETE = re.compile(r"^Simulation complete CPU (?P<cpu>\d)")
RE_MC_PERCPU_ERR = re.compile(
    r"\[ERROR\]\s+CPU (?P<cpu>\d): absorbed=(?P<absorbed>\d+) first=\d+ added=\d+ "
    r"known=\d+ retired=(?P<retired>\d+) baseline_retired=(?P<bretired>\d+)")

MULTICORE_HEADER = [
    "mix", "scheme", "pin_mode", "error_rate", "cpu", "workload",
    "ipc", "norm_ipc", "weighted_speedup", "sum_ipc",
    "total_error_events", "pages_retired", "baseline_page_retirements",
    "err_absorbed_cpu", "err_retired_cpu", "completed",
]


def parse_multicore_run(path):
    """Last-match per-CPU IPC (ROI block), completion, and error stats."""
    run = {"ipc": {}, "complete": set(), "absorbed": {}, "retired_cpu": {},
           "total_errors": None, "pages_retired": None, "baseline_retired": None}
    try:
        with open(path, errors="replace") as f:
            for line in f:
                m = RE_MC_CPU_IPC.match(line)
                if m:
                    run["ipc"][int(m.group("cpu"))] = float(m.group("ipc"))
                    continue
                m = RE_MC_COMPLETE.match(line)
                if m:
                    run["complete"].add(int(m.group("cpu")))
                    continue
                m = RE_MC_PERCPU_ERR.search(line)
                if m:
                    c = int(m.group("cpu"))
                    run["absorbed"][c] = int(m.group("absorbed"))
                    run["retired_cpu"][c] = (int(m.group("retired"))
                                             + int(m.group("bretired")))
                    continue
                for key, rx in (("total_errors", RE_TOTAL_ERRORS),
                                ("pages_retired", RE_PAGES_RETIRED)):
                    m2 = rx.search(line)
                    if m2:
                        run[key] = int(m2.group(1))
                        break
                else:
                    m2 = RE_BASELINE_PAGE_RETIRED.search(line)
                    if m2:
                        run["baseline_retired"] = int(m2.group(1))
    except OSError:
        pass
    return run


def collect_multicore():
    base = os.path.normpath(MULTICORE_DIR)
    if not os.path.isdir(base):
        return []
    rows = []
    for mix in MULTICORE_MIX_ORDER:
        runs = {}
        for scheme in MULTICORE_SCHEMES:
            path = os.path.join(base, f"champsim_4core_8mb_{scheme}_{mix}.txt")
            if os.path.isfile(path):
                runs[scheme] = parse_multicore_run(path)
        noerr = runs.get("noerr")
        for scheme in MULTICORE_SCHEMES:
            run = runs.get(scheme)
            if run is None:
                continue
            rate = "" if scheme == "noerr" else scheme.split("_")[1]
            pin_mode = ("none" if scheme == "noerr"
                        else "off" if scheme.startswith("off") else "on")
            completed = len(run["complete"]) == MULTICORE_NUM_CPUS
            norms = []
            for c in range(MULTICORE_NUM_CPUS):
                ipc = run["ipc"].get(c)
                base_ipc = noerr["ipc"].get(c) if noerr else None
                norms.append(ipc / base_ipc if (ipc and base_ipc) else None)
            full = all(n is not None for n in norms)
            weighted = sum(norms) if full else None
            sum_ipc = (sum(run["ipc"].values())
                       if len(run["ipc"]) == MULTICORE_NUM_CPUS else None)
            for c in range(MULTICORE_NUM_CPUS):
                rows.append([
                    mix, scheme, pin_mode, rate, c,
                    MULTICORE_MIXES[mix][c],
                    run["ipc"].get(c), norms[c], weighted, sum_ipc,
                    run["total_errors"], run["pages_retired"],
                    run["baseline_retired"],
                    run["absorbed"].get(c), run["retired_cpu"].get(c),
                    completed,
                ])
    return rows


def write_sheet(wb, name, header, data_rows):
    ws = wb.create_sheet(title=name)
    ws.append(header)
    for row in data_rows:
        ws.append(row)


def main():
    wb = Workbook()
    wb.remove(wb.active)

    threshold_rows = collect_threshold_sweep()
    write_sheet(wb, "Threshold sweep", THRESHOLD_HEADER, threshold_rows)
    print(f"  Threshold sweep:       {len(threshold_rows)} rows")

    max_way_rows = collect_max_error_way_sweep()
    write_sheet(wb, "Max error way sweep", MAX_WAY_HEADER, max_way_rows)
    print(f"  Max error way sweep:   {len(max_way_rows)} rows")

    noerr_rows = collect_noerr_way_sweep()
    write_sheet(wb, "Way sweep in No error", NOERR_HEADER, noerr_rows)
    print(f"  Way sweep in No error: {len(noerr_rows)} rows")

    multicore_rows = collect_multicore()
    if multicore_rows:
        write_sheet(wb, "Multicore", MULTICORE_HEADER, multicore_rows)
        print(f"  Multicore:             {len(multicore_rows)} rows")

    wb.save(OUTPUT_XLSX)
    print(f"\nXLSX: {OUTPUT_XLSX}")


if __name__ == "__main__":
    main()
