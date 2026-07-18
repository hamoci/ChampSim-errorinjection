#!/usr/bin/env python3
"""Generate 4-core multicore configs for Exp 2'/6'/7' (Track A follow-ups).

All error-injecting configs use the CLUSTERED fault model (seed 54321,
FIT mode mix) — the validated injection model as of 2026-07-17 (see
error_injection_docs/09: uniform over-penalizes the offline baseline).

  2_retirement_threshold/  pin thr{2,4,8,16,32} + off thr{...} @ 1e-8
                           (1e-7 dropped: exp1 showed ~zero retirements there)
  6_llc_way_sweep/         pin max_error_ways {1,2,4,6,8,10,12} @ {1e-7,1e-8}
  7_no_error_way_sweep/    noerr LLC ways {8..15} (w16 == exp1 noerr, reused)

Base template: pinning_on/4core_8MBLLC_2MBPage_pin_1e-8.json (8192 sets x 16w).
"""

import copy
import json
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TEMPLATE = json.load(open(os.path.join(BASE_DIR, "pinning_on", "4core_8MBLLC_2MBPage_pin_1e-8.json")))

THRESHOLDS = [2, 4, 8, 16, 32]
MAX_WAYS = [1, 2, 4, 6, 8, 10, 12]
RATES = {"1e-7": 1440000, "1e-8": 144000}
NOERR_WAYS = list(range(8, 16))  # w16 = exp1 noerr binary (validated identical)

CLUSTERED = {"error_spatial_model": "clustered", "error_seed": 54321}


def emit(subdir, name, exe, epm_overrides, llc_ways=None):
    c = copy.deepcopy(TEMPLATE)
    c["executable_name"] = exe
    epm = c["error_page_manager"]
    epm.update(epm_overrides)
    if llc_ways is not None:
        c["LLC"]["ways"] = llc_ways
    outdir = os.path.join(BASE_DIR, subdir)
    os.makedirs(outdir, exist_ok=True)
    path = os.path.join(outdir, f"{name}.json")
    json.dump(c, open(path, "w"), indent=4)
    return exe


exes = {"2": [], "6": [], "7": []}

# Exp 2': retirement threshold sweep @ 1e-8, both schemes, clustered
for thr in THRESHOLDS:
    exes["2"].append(emit(
        "2_retirement_threshold", f"pin_thr{thr}_clu_1e-8",
        f"champsim_4core_8mb_pin_thr{thr}_clu_1e-8",
        {**CLUSTERED, "cache_pinning": True, "dynamic_error_latency": True,
         "retirement_threshold": thr, "error_cycle_interval": RATES["1e-8"]}))
    exes["2"].append(emit(
        "2_retirement_threshold", f"off_thr{thr}_clu_1e-8",
        f"champsim_4core_8mb_off_thr{thr}_clu_1e-8",
        {**CLUSTERED, "cache_pinning": False, "dynamic_error_latency": False,
         "baseline_retirement_threshold": thr, "error_cycle_interval": RATES["1e-8"]}))

# Exp 6': max error ways sweep, pin only, clustered
for w in MAX_WAYS:
    for rate, interval in RATES.items():
        exes["6"].append(emit(
            "6_llc_way_sweep", f"pin_mw{w}_clu_{rate}",
            f"champsim_4core_8mb_pin_mw{w}_clu_{rate}",
            {**CLUSTERED, "cache_pinning": True, "dynamic_error_latency": True,
             "retirement_threshold": 32, "max_error_ways_per_set": w,
             "error_cycle_interval": interval}))

# Exp 7': no-error LLC way sweep (injection OFF — model-independent)
for w in NOERR_WAYS:
    exes["7"].append(emit(
        "7_no_error_way_sweep", f"noerr_w{w}",
        f"champsim_4core_8mb_noerr_w{w}",
        {"mode": "OFF", "cache_pinning": False, "error_cycle_interval": 0},
        llc_ways=w))

for k, v in exes.items():
    print(f"exp{k}: {len(v)} binaries")
    for e in v:
        print(f"  {e}")
