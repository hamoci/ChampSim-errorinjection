#!/usr/bin/env python3
"""Generate all config files for LLC Pinning evaluation experiments.

Experiments:
  1. Error Rate Sweep: BER (1e-5 ~ 1e-8) x Pinning ON/OFF
  2. Retirement Threshold Sensitivity: threshold sweep x Pinning ON/OFF x BER
  3. Error Way Capacity: max_error_ways_per_set sweep x BER
  4. LLC Size Baseline: LLC size sweep (no error)
  5. LLC Size Sensitivity: LLC size x Pinning ON x BER
"""

import json
import os
import copy

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Error cycle interval mapping (BER → cycle interval)
INTERVAL_MAP = {
    "1e-5": 144000000,
    "1e-6": 14400000,
    "1e-7": 1440000,
    "1e-8": 144000,
}

# Base template (2MB LLC, 2MB page, 32GB DRAM)
TEMPLATE = {
    "block_size": 64,
    "page_size": 2097152,
    "heartbeat_frequency": 10000000,
    "num_cores": 1,
    "ooo_cpu": [
        {
            "frequency": 4000,
            "ifetch_buffer_size": 64,
            "decode_buffer_size": 32,
            "dispatch_buffer_size": 32,
            "register_file_size": 128,
            "rob_size": 352,
            "lq_size": 128,
            "sq_size": 72,
            "fetch_width": 6,
            "decode_width": 6,
            "dispatch_width": 6,
            "execute_width": 4,
            "lq_width": 2,
            "sq_width": 2,
            "retire_width": 5,
            "mispredict_penalty": 1,
            "scheduler_size": 128,
            "decode_latency": 1,
            "dispatch_latency": 1,
            "schedule_latency": 0,
            "execute_latency": 0,
            "branch_predictor": "bimodal",
            "btb": "basic_btb"
        }
    ],
    "DIB": {"window_size": 16, "sets": 32, "ways": 8},
    "L1I": {
        "sets": 64, "ways": 8, "rq_size": 64, "wq_size": 64, "pq_size": 32,
        "mshr_size": 8, "latency": 4, "max_tag_check": 2, "max_fill": 2,
        "prefetch_as_load": False, "virtual_prefetch": True,
        "prefetch_activate": "LOAD,PREFETCH", "prefetcher": "no"
    },
    "L1D": {
        "sets": 64, "ways": 12, "rq_size": 64, "wq_size": 64, "pq_size": 8,
        "mshr_size": 16, "latency": 5, "max_tag_check": 2, "max_fill": 2,
        "prefetch_as_load": False, "virtual_prefetch": False,
        "prefetch_activate": "LOAD,PREFETCH", "prefetcher": "no"
    },
    "L2C": {
        "sets": 1024, "ways": 8, "rq_size": 32, "wq_size": 32, "pq_size": 16,
        "mshr_size": 32, "latency": 10, "max_tag_check": 1, "max_fill": 1,
        "prefetch_as_load": False, "virtual_prefetch": False,
        "prefetch_activate": "LOAD,PREFETCH", "prefetcher": "no"
    },
    "ITLB": {
        "sets": 16, "ways": 4, "rq_size": 16, "wq_size": 16, "pq_size": 0,
        "mshr_size": 8, "latency": 1, "max_tag_check": 2, "max_fill": 2,
        "prefetch_as_load": False
    },
    "DTLB": {
        "sets": 16, "ways": 4, "rq_size": 16, "wq_size": 16, "pq_size": 0,
        "mshr_size": 8, "latency": 1, "max_tag_check": 2, "max_fill": 2,
        "prefetch_as_load": False
    },
    "STLB": {
        "sets": 128, "ways": 12, "rq_size": 32, "wq_size": 32, "pq_size": 0,
        "mshr_size": 16, "latency": 8, "max_tag_check": 1, "max_fill": 1,
        "prefetch_as_load": False
    },
    "PTW": {
        "lower_level": "cpu0_L1D",
        "pscl4_set": 1, "pscl4_way": 4,
        "pscl3_set": 2, "pscl3_way": 4,
        "pscl2_set": 4, "pscl2_way": 8,
        "rq_size": 16, "mshr_size": 5, "max_read": 2, "max_write": 2
    },
    "LLC": {
        "frequency": 4000, "sets": 2048, "ways": 16,
        "rq_size": 32, "wq_size": 32, "pq_size": 32, "mshr_size": 64,
        "latency": 20, "max_tag_check": 1, "max_fill": 1,
        "prefetch_as_load": False, "virtual_prefetch": False,
        "prefetch_activate": "LOAD,PREFETCH", "prefetcher": "no",
        "replacement": "lru"
    },
    "physical_memory": {
        "data_rate": 4800, "channels": 2, "ranks": 1,
        "bankgroups": 8, "banks": 4, "bank_rows": 65536, "bank_columns": 2048,
        "channel_width": 4, "wq_size": 64, "rq_size": 64,
        "tCAS": 40, "tRCD": 40, "tRP": 40, "tRAS": 76,
        "refresh_period": 32, "refreshes_per_period": 8192
    },
    "virtual_memory": {
        "pte_page_size": 4096, "num_levels": 4,
        "minor_fault_penalty": 3956,
        "data_page_fault_4kb": 3956, "data_page_fault_2mb": 109201,
        "randomization": 1
    },
}

# Default error_page_manager for pinning ON (no ETT — MC CE_flag based)
EPM_PINNING_ON = {
    "mode": "CYCLE",
    "cache_pinning": True,
    "dynamic_error_latency": True,
    "error_latency_penalty": 454568,
    "retirement_threshold": 32,
    "max_error_ways_per_set": 8,
    "debug": 0
}

# Default error_page_manager for pinning OFF (baseline retirement)
EPM_PINNING_OFF = {
    "mode": "CYCLE",
    "cache_pinning": False,
    "dynamic_error_latency": False,
    "error_latency_penalty": 454568,
    "baseline_retirement_threshold": 1,
    "debug": 0
}

LLC_WAY_SWEEP_CONFIGS = [
    ("2MB", 2048, 16),
    ("4MB", 4096, 16),
    ("8MB", 2048, 64),
]
LLC_WAY_SWEEP_MAX_WAYS = [1, 2, 4, 6, 8, 10, 12]
LLC_WAY_SWEEP_EXTRA_MAX_WAYS = [6, 10, 12]
LLC_WAY_SWEEP_TARGET_RATES = ("1e-7", "1e-8")


def write_config(path, config):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w') as f:
        json.dump(config, f, indent=2)
        f.write('\n')
    print(f"  Created: {os.path.relpath(path, BASE_DIR)}")


def make_config(exe_name, llc_sets=2048, llc_ways=16, epm=None):
    cfg = copy.deepcopy(TEMPLATE)
    cfg["executable_name"] = exe_name
    cfg["LLC"]["sets"] = llc_sets
    cfg["LLC"]["ways"] = llc_ways
    if epm is not None:
        cfg["error_page_manager"] = copy.deepcopy(epm)
    return cfg


def gen_1_error_rate_sweep():
    """Experiment 1: Error rate sweep (1e-5 ~ 1e-8) x pinning ON/OFF"""
    print("\n=== 1. Error Rate Sweep ===")
    for rate_name, interval in INTERVAL_MAP.items():
        # Pinning ON
        epm = copy.deepcopy(EPM_PINNING_ON)
        epm["error_cycle_interval"] = interval
        exe = f"pin_on_{rate_name}"
        cfg = make_config(exe, epm=epm)
        path = os.path.join(BASE_DIR, "1_error_rate_sweep", "pinning_on",
                            f"2MBLLC_2MBPage_{rate_name}.json")
        write_config(path, cfg)

        # Pinning OFF
        epm = copy.deepcopy(EPM_PINNING_OFF)
        epm["error_cycle_interval"] = interval
        exe = f"pin_off_{rate_name}"
        cfg = make_config(exe, epm=epm)
        path = os.path.join(BASE_DIR, "1_error_rate_sweep", "pinning_off",
                            f"2MBLLC_2MBPage_{rate_name}.json")
        write_config(path, cfg)


def gen_2_retirement_threshold():
    """Experiment 2: Retirement threshold sensitivity x BER x pinning ON/OFF"""
    print("\n=== 2. Retirement Threshold Sensitivity ===")
    for rate_name, interval in INTERVAL_MAP.items():
        # Pinning ON: threshold sweep
        for threshold in [2, 4, 8, 16, 32]:
            epm = copy.deepcopy(EPM_PINNING_ON)
            epm["error_cycle_interval"] = interval
            epm["retirement_threshold"] = threshold
            exe = f"retire_on_{threshold}_{rate_name}"
            cfg = make_config(exe, epm=epm)
            path = os.path.join(BASE_DIR, "2_retirement_threshold", "pinning_on",
                                f"threshold_{threshold}_{rate_name}.json")
            write_config(path, cfg)

        # Pinning OFF: baseline_retirement_threshold sweep
        for threshold in [2, 4, 8, 16, 32]:
            epm = copy.deepcopy(EPM_PINNING_OFF)
            epm["error_cycle_interval"] = interval
            epm["baseline_retirement_threshold"] = threshold
            exe = f"retire_off_{threshold}_{rate_name}"
            cfg = make_config(exe, epm=epm)
            path = os.path.join(BASE_DIR, "2_retirement_threshold", "pinning_off",
                                f"threshold_{threshold}_{rate_name}.json")
            write_config(path, cfg)


def gen_3_error_way_capacity():
    """Experiment 3: max_error_ways_per_set sweep x BER"""
    print("\n=== 3. Error Way Capacity ===")
    for rate_name, interval in INTERVAL_MAP.items():
        for ways in [1, 2, 4, 8]:
            epm = copy.deepcopy(EPM_PINNING_ON)
            epm["error_cycle_interval"] = interval
            epm["max_error_ways_per_set"] = ways
            exe = f"errway_{ways}w_{rate_name}"
            cfg = make_config(exe, epm=epm)
            path = os.path.join(BASE_DIR, "3_error_way_capacity",
                                f"max_errways_{ways}_{rate_name}.json")
            write_config(path, cfg)


def gen_4_llc_size_baseline():
    """Experiment 4: LLC size sweep without errors"""
    print("\n=== 4. LLC Size Baseline (no error) ===")
    llc_configs = [
        ("1MB", 2048, 8),
        ("2MB", 2048, 16),
        ("4MB", 4096, 16),
        ("8MB", 2048, 64),
    ]
    for size_name, sets, ways in llc_configs:
        exe = f"llc_baseline_{size_name}"
        cfg = make_config(exe, llc_sets=sets, llc_ways=ways)
        path = os.path.join(BASE_DIR, "4_llc_size_baseline",
                            f"LLC_{size_name}_no_error.json")
        write_config(path, cfg)


def gen_5_llc_size_sensitivity():
    """Experiment 5: LLC size sweep with pinning ON x BER"""
    print("\n=== 5. LLC Size Sensitivity (pinning ON) ===")
    llc_configs = [
        ("1MB", 2048, 8),
        ("2MB", 2048, 16),
        ("4MB", 4096, 16),
        ("8MB", 2048, 64),
    ]
    for rate_name, interval in INTERVAL_MAP.items():
        for size_name, sets, ways in llc_configs:
            epm = copy.deepcopy(EPM_PINNING_ON)
            epm["error_cycle_interval"] = interval
            exe = f"llc_{size_name}_{rate_name}"
            cfg = make_config(exe, llc_sets=sets, llc_ways=ways, epm=epm)
            path = os.path.join(BASE_DIR, "5_llc_size_sensitivity",
                                f"LLC_{size_name}_{rate_name}.json")
            write_config(path, cfg)


def gen_7_no_error_way_sweep():
    """Experiment 7: No-error LLC way sweep (static reservation reference).

    Reduce LLC ways from 16 down to 8 (step=1) at fixed sets, with no errors.
    Acts as a lower-bound reference for pinning experiments — quantifies the
    pure capacity-loss IPC degradation when N ways are taken away from the
    normal cache (mirrors what static reservation would cost).
    """
    print("\n=== 7. No-error LLC Way Sweep ===")
    llc_configs = [
        ("2MB", 2048),
        ("4MB", 4096),
    ]
    ways_list = list(range(16, 7, -1))  # 16, 15, ..., 8

    for size_name, sets in llc_configs:
        for ways in ways_list:
            exe = f"noerr_{size_name}_w{ways}"
            cfg = make_config(exe, llc_sets=sets, llc_ways=ways)
            path = os.path.join(BASE_DIR, "7_no_error_way_sweep",
                                f"LLC_{size_name}_ways_{ways}.json")
            write_config(path, cfg)


def gen_6_llc_way_sweep(max_ways_list=None):
    """Experiment 6: LLC size x max_error_ways x BER (low-rate regimes only)

    Restricted to 1e-7 and 1e-8 BER (where pinning vs. retirement tradeoffs
    are most informative — high-rate regimes covered in experiment 1).
    Run scripts override SPEC_TRACES to cover all 10 SPEC workloads.
    """
    print("\n=== 6. LLC Size x Error Way Capacity Sweep ===")
    if max_ways_list is None:
        max_ways_list = LLC_WAY_SWEEP_MAX_WAYS

    for rate_name in LLC_WAY_SWEEP_TARGET_RATES:
        interval = INTERVAL_MAP[rate_name]
        for size_name, sets, ways in LLC_WAY_SWEEP_CONFIGS:
            for max_ways in max_ways_list:
                epm = copy.deepcopy(EPM_PINNING_ON)
                epm["error_cycle_interval"] = interval
                epm["max_error_ways_per_set"] = max_ways
                exe = f"sweep_{size_name}_w{max_ways}_{rate_name}"
                cfg = make_config(exe, llc_sets=sets, llc_ways=ways, epm=epm)
                path = os.path.join(
                    BASE_DIR, "6_llc_way_sweep",
                    f"LLC_{size_name}_maxway_{max_ways}_{rate_name}.json")
                write_config(path, cfg)


def gen_6_llc_way_sweep_extra():
    """Generate only the newly added 6/10/12-way experiment-6 configs."""
    gen_6_llc_way_sweep(LLC_WAY_SWEEP_EXTRA_MAX_WAYS)


if __name__ == "__main__":
    gen_1_error_rate_sweep()
    gen_2_retirement_threshold()
    gen_3_error_way_capacity()
    gen_4_llc_size_baseline()
    gen_5_llc_size_sensitivity()
    gen_6_llc_way_sweep()
    gen_7_no_error_way_sweep()
    print("\nDone! All configs generated.")
