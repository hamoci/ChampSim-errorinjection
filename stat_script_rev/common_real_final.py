#!/usr/bin/env python3
import os
import re
from dataclasses import dataclass
from typing import List, Optional, Tuple


SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
BASE_DIR = os.path.dirname(SCRIPT_DIR)
RESULTS_DIR = os.path.join(BASE_DIR, "results/0219_finished/real_final_spec")

FILE_RE = re.compile(
    r"^champsim_(?:(?P<llc>[248])mb_)?(?P<page>4kb|2mb)_(?:(?:error_32gb_(?P<er>1e-\d+)(?P<pin>_cache_pinning)?)|32gb)_(?P<trace>.+)\.txt$"
)
WORKLOAD_RE = re.compile(r"^(\d+\.[^-_]+)")
IPC_RE = re.compile(r"CPU 0 cumulative IPC:\s+([\d.]+)")
ALLOC_RE = re.compile(r"Allocated Error Ways per Set:\s+(\d+)")
USED_RE = re.compile(r"Used Error Way Slots:\s+\d+\s+\(([\d.]+)%\)")


@dataclass
class Record:
    path: str
    filename: str
    llc_mb: int
    page: str
    error_rate: Optional[str]
    pinning: bool
    workload: str
    trace: str


def parse_filename(filename: str) -> Optional[Record]:
    m = FILE_RE.match(filename)
    if not m:
        return None

    llc = m.group("llc")
    llc_mb = int(llc) if llc else 2
    page = m.group("page")
    er = m.group("er")
    pinning = m.group("pin") is not None
    trace = m.group("trace")

    wm = WORKLOAD_RE.match(trace)
    workload = wm.group(1) if wm else trace

    return Record(
        path="",
        filename=filename,
        llc_mb=llc_mb,
        page=page,
        error_rate=er,
        pinning=pinning,
        workload=workload,
        trace=trace,
    )


def load_records(results_dir: str = RESULTS_DIR) -> List[Record]:
    records: List[Record] = []
    if not os.path.isdir(results_dir):
        return records

    for root, _, files in os.walk(results_dir):
        for filename in files:
            if not filename.endswith(".txt"):
                continue
            rec = parse_filename(filename)
            if rec is None:
                continue
            rec.path = os.path.join(root, filename)
            records.append(rec)

    return records


def extract_ipc(path: str) -> Optional[float]:
    try:
        with open(path, "r") as f:
            txt = f.read()
        m = IPC_RE.search(txt)
        return float(m.group(1)) if m else None
    except Exception:
        return None


def extract_cache_way_stats(path: str) -> Optional[Tuple[int, float]]:
    try:
        with open(path, "r") as f:
            txt = f.read()
        ma = ALLOC_RE.search(txt)
        mu = USED_RE.search(txt)
        if not ma or not mu:
            return None
        return int(ma.group(1)), float(mu.group(1))
    except Exception:
        return None
