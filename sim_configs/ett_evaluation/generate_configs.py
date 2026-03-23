#!/usr/bin/env python3
"""Generate all config files for ETT evaluation experiments."""

import json
import os
import copy

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Error cycle interval mapping
INTERVAL_MAP = {
    "1e-5": 1440000000,
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

# Default error_page_manager for pinning ON
EPM_PINNING_ON = {
    "mode": "CYCLE",
    "cache_pinning": True,
    "dynamic_error_latency": True,
    "error_latency_penalty": 454568,
    "ett_entries": 128,
    "bloom_filter_size": 256,
    "bloom_filter_k": 4,
    "retirement_threshold": 32,
    "max_error_ways_per_set": 8,
    "debug": 0
}

# Default error_page_manager for pinning OFF
EPM_PINNING_OFF = {
    "mode": "CYCLE",
    "cache_pinning": False,
    "dynamic_error_latency": False,
    "error_latency_penalty": 454568,
    "debug": 0
}


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
        exe = f"ett_err_sweep_pinning_on_{rate_name}"
        cfg = make_config(exe, epm=epm)
        path = os.path.join(BASE_DIR, "1_error_rate_sweep", "pinning_on",
                            f"2MBLLC_2MBPage_{rate_name}.json")
        write_config(path, cfg)

        # Pinning OFF
        epm = copy.deepcopy(EPM_PINNING_OFF)
        epm["error_cycle_interval"] = interval
        exe = f"ett_err_sweep_pinning_off_{rate_name}"
        cfg = make_config(exe, epm=epm)
        path = os.path.join(BASE_DIR, "1_error_rate_sweep", "pinning_off",
                            f"2MBLLC_2MBPage_{rate_name}.json")
        write_config(path, cfg)


def gen_2_ett_sensitivity():
    """Experiment 2: ETT sensitivity x all error rates"""
    print("\n=== 2. ETT Sensitivity ===")
    for rate_name, interval in INTERVAL_MAP.items():
        # 2a. ETT entries sweep: 32, 64, 128(baseline), 256
        for entries in [32, 64, 128, 256]:
            epm = copy.deepcopy(EPM_PINNING_ON)
            epm["error_cycle_interval"] = interval
            epm["ett_entries"] = entries
            exe = f"ett_sens_entries_{entries}_{rate_name}"
            cfg = make_config(exe, epm=epm)
            path = os.path.join(BASE_DIR, "2_ett_sensitivity", "ett_entries",
                                f"entries_{entries}_{rate_name}.json")
            write_config(path, cfg)

        # 2b. Retirement threshold sweep: 4, 8, 16, 32
        for threshold in [4, 8, 16, 32]:
            epm = copy.deepcopy(EPM_PINNING_ON)
            epm["error_cycle_interval"] = interval
            epm["retirement_threshold"] = threshold
            exe = f"ett_sens_retire_{threshold}_{rate_name}"
            cfg = make_config(exe, epm=epm)
            path = os.path.join(BASE_DIR, "2_ett_sensitivity", "retirement_threshold",
                                f"threshold_{threshold}_{rate_name}.json")
            write_config(path, cfg)


def gen_3_error_way_capacity():
    """Experiment 3: max_error_ways_per_set x all error rates"""
    print("\n=== 3. Error Way Capacity ===")
    for rate_name, interval in INTERVAL_MAP.items():
        for ways in [1, 4, 8]:
            epm = copy.deepcopy(EPM_PINNING_ON)
            epm["error_cycle_interval"] = interval
            epm["max_error_ways_per_set"] = ways
            exe = f"ett_errway_{ways}ways_{rate_name}"
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
        exe = f"ett_llc_baseline_{size_name}"
        cfg = make_config(exe, llc_sets=sets, llc_ways=ways)
        path = os.path.join(BASE_DIR, "4_llc_size_baseline",
                            f"LLC_{size_name}_no_error.json")
        write_config(path, cfg)


if __name__ == "__main__":
    gen_1_error_rate_sweep()
    gen_2_ett_sensitivity()
    gen_3_error_way_capacity()
    gen_4_llc_size_baseline()
    print("\nDone! All configs generated.")
