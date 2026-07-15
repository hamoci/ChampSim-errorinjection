#!/usr/bin/env python3
"""Common parsing utilities for ETT evaluation results."""

import os
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
BASE_DIR = os.path.dirname(SCRIPT_DIR)
RESULTS_DIR = os.path.join(BASE_DIR, "results", "ett_evaluation")

# ── Result directories ──
DIR_ERR_SWEEP = os.path.join(RESULTS_DIR, "1_error_rate_sweep")
DIR_ETT_SENS = os.path.join(RESULTS_DIR, "2_ett_sensitivity")
DIR_ERRWAY_CAP = os.path.join(RESULTS_DIR, "3_error_way_capacity")
DIR_LLC_BASELINE = os.path.join(RESULTS_DIR, "4_llc_size_baseline")

# ── File-name patterns ──
# 1_error_rate_sweep: ett_err_sweep_pinning_{on|off}_{rate}_{trace}.txt
RE_ERR_SWEEP = re.compile(
    r"^ett_err_sweep_pinning_(?P<pin>on|off)_(?P<rate>1e-\d+)_(?P<trace>.+)\.txt$"
)
# 2_ett_sensitivity (entries): ett_sens_entries_{n}_{rate}_{trace}.txt
RE_ETT_ENTRIES = re.compile(
    r"^ett_sens_entries_(?P<entries>\d+)_(?P<rate>1e-\d+)_(?P<trace>.+)\.txt$"
)
# 2_ett_sensitivity (retire ON): ett_sens_retire_{thresh}_{rate}_{trace}.txt
RE_RETIRE_ON = re.compile(
    r"^ett_sens_retire_(?P<thresh>\d+)_(?P<rate>1e-\d+)_(?P<trace>.+)\.txt$"
)
# 2_ett_sensitivity (retire OFF): ett_sens_retire_off_{thresh}_{rate}_{trace}.txt
RE_RETIRE_OFF = re.compile(
    r"^ett_sens_retire_off_(?P<thresh>\d+)_(?P<rate>1e-\d+)_(?P<trace>.+)\.txt$"
)
# 3_error_way_capacity: ett_errway_{n}ways_{rate}_{trace}.txt
RE_ERRWAY = re.compile(
    r"^ett_errway_(?P<ways>\d+)ways_(?P<rate>1e-\d+)_(?P<trace>.+)\.txt$"
)
# 4_llc_size_baseline: ett_llc_baseline_{size}_{trace}.txt
RE_LLC_BASELINE = re.compile(
    r"^ett_llc_baseline_(?P<size>\d+MB)_(?P<trace>.+)\.txt$"
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

RE_ETT_ENTRIES_CFG = re.compile(r"ETT Entries:\s+(\d+)")
RE_ETT_BLOOM_M = re.compile(r"Bloom Filter Size \(m\):\s+(\d+)")
RE_ETT_RETIRE_THRESH = re.compile(r"Retirement Threshold:\s+(\d+)")
RE_ETT_TOTAL_ERRORS = re.compile(r"Total DRAM Error Events:\s+(\d+)")
RE_ETT_NEW_RECORDINGS = re.compile(r"New Error Recordings:\s+(\d+)")
RE_ETT_FIRST_ERROR = re.compile(r"First Error \(per page\):\s+(\d+)")
RE_ETT_ADDITIONAL = re.compile(r"Additional Errors:\s+(\d+)")
RE_ETT_RETIREMENTS = re.compile(r"Page Retirements.*?:\s+(\d+)")
RE_ETT_ALREADY_KNOWN = re.compile(r"Already Known \(bloom hit\):\s+(\d+)")
RE_ETT_ACTIVE_PAGES = re.compile(r"Active Pages \(tracked\):\s+(\d+)")
RE_ETT_SINGLE_ERR = re.compile(r"Single-error pages:\s+(\d+)")
RE_ETT_MULTI_ERR = re.compile(r"Multi-error pages:\s+(\d+)")
RE_ETT_USED = re.compile(r"ETT Entries Used:\s+(\d+)\s*/\s*(\d+)")
RE_ETT_EVICTIONS = re.compile(r"ETT Evictions:\s+(\d+)")
RE_BF_AVG_OCC = re.compile(r"\[Snapshot.*?\]\s*\n\s*Valid Entries:\s+\d+\s*\n\s*Avg Occupancy:\s+([\d.]+)%")
RE_BF_FP_RATE = re.compile(r"\[Snapshot.*?\]\s*\n.*?Est\. FP Rate:\s+([\d.]+)%", re.DOTALL)
RE_PAGES_RETIRED = re.compile(r"Pages Retired:\s+(\d+)")
RE_LINES_INVALIDATED = re.compile(r"Cache Lines Invalidated:\s+(\d+)")

RE_ROW_BUFFER_MISS = re.compile(r"ROW_BUFFER_MISS:\s+(\d+)")

WORKLOAD_RE = re.compile(r"^(\d+\.\w+)")


@dataclass
class Metrics:
    """All extractable metrics from a result file."""
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
    # ETT
    ett_entries: Optional[int] = None
    bloom_m: Optional[int] = None
    retire_threshold: Optional[int] = None
    total_errors: Optional[int] = None
    new_recordings: Optional[int] = None
    first_errors: Optional[int] = None
    additional_errors: Optional[int] = None
    page_retirements_ett: Optional[int] = None
    already_known: Optional[int] = None
    active_pages: Optional[int] = None
    single_error_pages: Optional[int] = None
    multi_error_pages: Optional[int] = None
    ett_used: Optional[int] = None
    ett_total: Optional[int] = None
    ett_evictions: Optional[int] = None
    bf_avg_occupancy: Optional[float] = None
    bf_fp_rate: Optional[float] = None
    pages_retired: Optional[int] = None
    lines_invalidated: Optional[int] = None
    # DRAM
    rbmpki: Optional[float] = None


def extract_workload(trace: str) -> str:
    m = WORKLOAD_RE.match(trace)
    return m.group(1) if m else trace


def extract_metrics(path: str) -> Metrics:
    """Parse a result file and extract all metrics."""
    try:
        with open(path, "r") as f:
            txt = f.read()
    except Exception:
        return Metrics()

    m = Metrics()

    # IPC
    match = RE_IPC.search(txt)
    if match:
        m.ipc = float(match.group(1))
        m.instructions = int(match.group(2))
        m.cycles = int(match.group(3))

    # Error way stats
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

    # ETT stats
    _set_int(m, "ett_entries", RE_ETT_ENTRIES_CFG, txt)
    _set_int(m, "bloom_m", RE_ETT_BLOOM_M, txt)
    _set_int(m, "retire_threshold", RE_ETT_RETIRE_THRESH, txt)
    _set_int(m, "total_errors", RE_ETT_TOTAL_ERRORS, txt)
    _set_int(m, "new_recordings", RE_ETT_NEW_RECORDINGS, txt)
    _set_int(m, "first_errors", RE_ETT_FIRST_ERROR, txt)
    _set_int(m, "additional_errors", RE_ETT_ADDITIONAL, txt)
    _set_int(m, "page_retirements_ett", RE_ETT_RETIREMENTS, txt)
    _set_int(m, "already_known", RE_ETT_ALREADY_KNOWN, txt)
    _set_int(m, "active_pages", RE_ETT_ACTIVE_PAGES, txt)
    _set_int(m, "single_error_pages", RE_ETT_SINGLE_ERR, txt)
    _set_int(m, "multi_error_pages", RE_ETT_MULTI_ERR, txt)
    match = RE_ETT_USED.search(txt)
    if match:
        m.ett_used = int(match.group(1))
        m.ett_total = int(match.group(2))
    _set_int(m, "ett_evictions", RE_ETT_EVICTIONS, txt)
    _set_float(m, "bf_avg_occupancy", RE_BF_AVG_OCC, txt)
    _set_float(m, "bf_fp_rate", RE_BF_FP_RATE, txt)
    _set_int(m, "pages_retired", RE_PAGES_RETIRED, txt)
    _set_int(m, "lines_invalidated", RE_LINES_INVALIDATED, txt)

    # RBMPKI
    if m.instructions and m.instructions > 0:
        rb_misses = sum(int(x) for x in RE_ROW_BUFFER_MISS.findall(txt))
        if rb_misses > 0:
            m.rbmpki = (rb_misses / m.instructions) * 1000

    return m


def _set_int(obj, attr, regex, txt):
    match = regex.search(txt)
    if match:
        setattr(obj, attr, int(match.group(1)))


def _set_float(obj, attr, regex, txt):
    match = regex.search(txt)
    if match:
        setattr(obj, attr, float(match.group(1)))


# ── Loaders ──

def load_err_sweep(result_dir: str = DIR_ERR_SWEEP) -> List[dict]:
    """Load 1_error_rate_sweep results."""
    records = []
    if not os.path.isdir(result_dir):
        return records
    for fname in sorted(os.listdir(result_dir)):
        match = RE_ERR_SWEEP.match(fname)
        if not match:
            continue
        path = os.path.join(result_dir, fname)
        metrics = extract_metrics(path)
        records.append({
            "pinning": match.group("pin") == "on",
            "error_rate": match.group("rate"),
            "trace": match.group("trace"),
            "workload": extract_workload(match.group("trace")),
            "metrics": metrics,
        })
    return records


def load_ett_entries(result_dir: str = DIR_ETT_SENS) -> List[dict]:
    """Load ETT entry sensitivity results."""
    records = []
    if not os.path.isdir(result_dir):
        return records
    for fname in sorted(os.listdir(result_dir)):
        match = RE_ETT_ENTRIES.match(fname)
        if not match:
            continue
        path = os.path.join(result_dir, fname)
        metrics = extract_metrics(path)
        records.append({
            "entries": int(match.group("entries")),
            "error_rate": match.group("rate"),
            "trace": match.group("trace"),
            "workload": extract_workload(match.group("trace")),
            "metrics": metrics,
        })
    return records


def load_retire_threshold(result_dir: str = DIR_ETT_SENS) -> List[dict]:
    """Load retirement threshold sensitivity results (pinning ON and OFF)."""
    records = []
    if not os.path.isdir(result_dir):
        return records
    for fname in sorted(os.listdir(result_dir)):
        match_on = RE_RETIRE_ON.match(fname)
        match_off = RE_RETIRE_OFF.match(fname)
        if match_on:
            pinning = True
            thresh = int(match_on.group("thresh"))
            rate = match_on.group("rate")
            trace = match_on.group("trace")
        elif match_off:
            pinning = False
            thresh = int(match_off.group("thresh"))
            rate = match_off.group("rate")
            trace = match_off.group("trace")
        else:
            continue
        path = os.path.join(result_dir, fname)
        metrics = extract_metrics(path)
        records.append({
            "pinning": pinning,
            "threshold": thresh,
            "error_rate": rate,
            "trace": trace,
            "workload": extract_workload(trace),
            "metrics": metrics,
        })
    return records


def load_errway_capacity(result_dir: str = DIR_ERRWAY_CAP) -> List[dict]:
    """Load error way capacity results."""
    records = []
    if not os.path.isdir(result_dir):
        return records
    for fname in sorted(os.listdir(result_dir)):
        match = RE_ERRWAY.match(fname)
        if not match:
            continue
        path = os.path.join(result_dir, fname)
        metrics = extract_metrics(path)
        records.append({
            "ways": int(match.group("ways")),
            "error_rate": match.group("rate"),
            "trace": match.group("trace"),
            "workload": extract_workload(match.group("trace")),
            "metrics": metrics,
        })
    return records


def load_llc_baseline(result_dir: str = DIR_LLC_BASELINE) -> List[dict]:
    """Load LLC baseline (no error) results."""
    records = []
    if not os.path.isdir(result_dir):
        return records
    for fname in sorted(os.listdir(result_dir)):
        match = RE_LLC_BASELINE.match(fname)
        if not match:
            continue
        path = os.path.join(result_dir, fname)
        metrics = extract_metrics(path)
        records.append({
            "llc_size": match.group("size"),
            "trace": match.group("trace"),
            "workload": extract_workload(match.group("trace")),
            "metrics": metrics,
        })
    return records


def gmean(values):
    """Geometric mean of positive values."""
    vals = [v for v in values if v is not None and v > 0]
    if not vals:
        return 0.0
    import numpy as np
    return float(np.exp(np.mean(np.log(vals))))
