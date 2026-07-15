#!/usr/bin/env python3
"""Common parsing utilities for normal_evaluation results."""

import os
import re
from dataclasses import dataclass
from typing import List, Optional

import numpy as np

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
BASE_DIR = os.path.dirname(SCRIPT_DIR)
RESULTS_DIR = os.path.join(BASE_DIR, "results", "normal_evaluation")

DIR_LLC_WAY_SWEEP = os.path.join(RESULTS_DIR, "6_llc_way_sweep")
DIR_NO_ERROR_WAY_SWEEP = os.path.join(RESULTS_DIR, "7_no_error_way_sweep")

# sweep_{2MB|4MB|8MB}_w{1|2|4|8}_{1e-5|...}_{trace}.txt
RE_SWEEP = re.compile(
    r"^sweep_(?P<llc_size>\d+MB)_w(?P<max_ways>\d+)_(?P<rate>1e-\d+)_(?P<trace>.+)\.txt$"
)

# noerr_{2MB|4MB}_w{8..16}_{trace}.txt
RE_NOERR_SWEEP = re.compile(
    r"^noerr_(?P<llc_size>\d+MB)_w(?P<ways>\d+)_(?P<trace>.+)\.txt$"
)

# ── Metric regexes ──
RE_IPC = re.compile(r"CPU 0 cumulative IPC:\s+([\d.]+)\s+instructions:\s*(\d+)\s+cycles:\s*(\d+)")
RE_ERR_WAY_HITS = re.compile(r"Error Way Hits:\s+(\d+)")
RE_ERR_WAY_FILLS = re.compile(r"Error Way Fills.*?:\s+(\d+)")
RE_ERR_WAY_HIT_RATE = re.compile(r"Error Way Hit Rate:\s+([\d.]+)%")
RE_ERR_WAY_EVICTIONS = re.compile(r"Error Way Evictions.*?:\s+(\d+)")
RE_ERR_WAY_USED = re.compile(r"Used Slots:\s+(\d+)\s+\(([\d.]+)%\)")
RE_ERR_WAY_ALLOC = re.compile(r"Allocated Error Ways per Set:\s+(\d+)")
RE_ERR_WAY_MAX = re.compile(r"Max Error Ways per Set:\s+(\d+)")
RE_TOTAL_KNOWN_ERR = re.compile(r"Total Known Error Addresses:\s+(\d+)")
RE_PINNED = re.compile(r"Pinned in Error Way:\s+(\d+)\s+\(([\d.]+)%\)")
RE_NOT_IN_LLC = re.compile(r"Not in LLC \(DRAM exposed\):\s+(\d+)")

RE_RETIRE_THRESH = re.compile(r"Retirement Threshold:\s+(\d+)")
RE_TOTAL_ERRORS = re.compile(r"Total DRAM Error Events:\s+(\d+)")
RE_PAGES_RETIRED = re.compile(r"Pages Retired:\s+(\d+)")
RE_BASELINE_PAGE_RETIRED = re.compile(r"Baseline Page Retirements:\s+(\d+)")

RE_PIN_OFF_RETIRED = re.compile(
    r"Retired \(page offline\):\s+(\d+)\s+\(([\d.]+)%\)"
)
RE_PIN_OFF_LIVE = re.compile(r"Live \(still tracked\):\s+(\d+)")

RE_ROW_BUFFER_MISS = re.compile(r"ROW_BUFFER_MISS:\s+(\d+)")

RE_LLC_MISS = re.compile(r"cpu0->LLC TOTAL\s+ACCESS:\s+(\d+)\s+HIT:\s+(\d+)\s+MISS:\s+(\d+)")

WORKLOAD_RE = re.compile(r"^(\d+\.\w+)")

LLC_SIZES = ["2MB", "4MB", "8MB"]
MAX_WAYS = [1, 2, 4, 8]
ERROR_RATES = ["1e-5", "1e-6", "1e-7", "1e-8"]


@dataclass
class Metrics:
    ipc: Optional[float] = None
    instructions: Optional[int] = None
    cycles: Optional[int] = None
    # Error way
    err_way_alloc: Optional[int] = None
    err_way_max: Optional[int] = None
    err_way_hits: Optional[int] = None
    err_way_fills: Optional[int] = None
    err_way_hit_rate: Optional[float] = None
    err_way_evictions: Optional[int] = None
    err_way_used: Optional[int] = None
    err_way_used_pct: Optional[float] = None
    # Protection
    total_known_errors: Optional[int] = None
    pinned_count: Optional[int] = None
    pinned_pct: Optional[float] = None
    not_in_llc: Optional[int] = None
    # Error recording
    total_dram_errors: Optional[int] = None
    pages_retired: Optional[int] = None
    baseline_page_retirements: Optional[int] = None
    # Pin-off baseline coverage
    pin_off_retired_count: Optional[int] = None
    pin_off_retired_pct: Optional[float] = None
    pin_off_live_count: Optional[int] = None
    # DRAM
    rbmpki: Optional[float] = None
    # LLC
    llc_access: Optional[int] = None
    llc_hit: Optional[int] = None
    llc_miss: Optional[int] = None
    llc_miss_rate: Optional[float] = None


def extract_workload(trace: str) -> str:
    m = WORKLOAD_RE.match(trace)
    return m.group(1) if m else trace


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
        m.cycles = int(match.group(3))

    _set_int(m, "err_way_alloc", RE_ERR_WAY_ALLOC, txt)
    _set_int(m, "err_way_max", RE_ERR_WAY_MAX, txt)
    _set_int(m, "err_way_hits", RE_ERR_WAY_HITS, txt)
    _set_int(m, "err_way_fills", RE_ERR_WAY_FILLS, txt)
    _set_float(m, "err_way_hit_rate", RE_ERR_WAY_HIT_RATE, txt)
    _set_int(m, "err_way_evictions", RE_ERR_WAY_EVICTIONS, txt)
    match = RE_ERR_WAY_USED.search(txt)
    if match:
        m.err_way_used = int(match.group(1))
        m.err_way_used_pct = float(match.group(2))

    _set_int(m, "total_known_errors", RE_TOTAL_KNOWN_ERR, txt)
    match = RE_PINNED.search(txt)
    if match:
        m.pinned_count = int(match.group(1))
        m.pinned_pct = float(match.group(2))
    _set_int(m, "not_in_llc", RE_NOT_IN_LLC, txt)

    _set_int(m, "total_dram_errors", RE_TOTAL_ERRORS, txt)
    _set_int(m, "pages_retired", RE_PAGES_RETIRED, txt)

    baseline_retire_matches = RE_BASELINE_PAGE_RETIRED.findall(txt)
    if baseline_retire_matches:
        m.baseline_page_retirements = int(baseline_retire_matches[-1])

    match = RE_PIN_OFF_RETIRED.search(txt)
    if match:
        m.pin_off_retired_count = int(match.group(1))
        m.pin_off_retired_pct = float(match.group(2))
    _set_int(m, "pin_off_live_count", RE_PIN_OFF_LIVE, txt)

    # RBMPKI
    if m.instructions and m.instructions > 0:
        rb_misses = sum(int(x) for x in RE_ROW_BUFFER_MISS.findall(txt))
        if rb_misses > 0:
            m.rbmpki = (rb_misses / m.instructions) * 1000

    # LLC stats
    llc_match = RE_LLC_MISS.search(txt)
    if llc_match:
        m.llc_access = int(llc_match.group(1))
        m.llc_hit = int(llc_match.group(2))
        m.llc_miss = int(llc_match.group(3))
        if m.llc_access > 0:
            m.llc_miss_rate = m.llc_miss / m.llc_access * 100

    return m


def _set_int(obj, attr, regex, txt):
    match = regex.search(txt)
    if match:
        setattr(obj, attr, int(match.group(1)))


def _set_float(obj, attr, regex, txt):
    match = regex.search(txt)
    if match:
        setattr(obj, attr, float(match.group(1)))


def load_llc_way_sweep(result_dir: str = DIR_LLC_WAY_SWEEP) -> List[dict]:
    """Load 6_llc_way_sweep results."""
    records = []
    if not os.path.isdir(result_dir):
        return records
    for fname in sorted(os.listdir(result_dir)):
        match = RE_SWEEP.match(fname)
        if not match:
            continue
        path = os.path.join(result_dir, fname)
        metrics = extract_metrics(path)
        records.append({
            "llc_size": match.group("llc_size"),
            "max_ways": int(match.group("max_ways")),
            "error_rate": match.group("rate"),
            "trace": match.group("trace"),
            "workload": extract_workload(match.group("trace")),
            "metrics": metrics,
        })
    return records


def load_no_error_way_sweep(result_dir: str = DIR_NO_ERROR_WAY_SWEEP) -> List[dict]:
    """Load 7_no_error_way_sweep results (LLC way sweep without errors)."""
    records = []
    if not os.path.isdir(result_dir):
        return records
    for fname in sorted(os.listdir(result_dir)):
        match = RE_NOERR_SWEEP.match(fname)
        if not match:
            continue
        path = os.path.join(result_dir, fname)
        metrics = extract_metrics(path)
        records.append({
            "llc_size": match.group("llc_size"),
            "ways": int(match.group("ways")),
            "trace": match.group("trace"),
            "workload": extract_workload(match.group("trace")),
            "metrics": metrics,
        })
    return records


def gmean(values):
    vals = [v for v in values if v is not None and v > 0]
    if not vals:
        return 0.0
    return float(np.exp(np.mean(np.log(vals))))


_XLSX_PATH = os.path.join(SCRIPT_DIR, "paper_figures", "raw_data.xlsx")
_xlsx_cache = {}


def load_xlsx_sheet(sheet_name: str, xlsx_path: str = _XLSX_PATH):
    import pandas as pd
    key = (xlsx_path, sheet_name)
    if key in _xlsx_cache:
        return _xlsx_cache[key].copy()
    if not os.path.isfile(xlsx_path):
        raise SystemExit(f"xlsx not found: {xlsx_path}")
    df = pd.read_excel(xlsx_path, sheet_name=sheet_name, header=0,
                       engine="openpyxl")
    if "error_rate" in df.columns and df["error_rate"].dtype != object:
        df["error_rate"] = df["error_rate"].apply(
            lambda v: f"1e-{int(round(-np.log10(float(v))))}"
            if v is not None and not (isinstance(v, float) and np.isnan(v))
            else v
        )
    _xlsx_cache[key] = df
    return df.copy()
