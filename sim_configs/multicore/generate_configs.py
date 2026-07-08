#!/usr/bin/env python3
"""Generate 4-core multicore mix experiment configs (Track A).

System: 4 cores, 8MB/16way LLC (per-core 2MB parity with single-core runs),
2MB pages, 32GB DDR5 (same DRAM params as single-core experiments).

Schemes:
  - no_error     : injection OFF (upper bound)
  - pinning_off  : conventional page offline (baseline_retirement_threshold=2,
                   Linux RAS/CEC default per paper outline Table 2)
  - pinning_on   : LLC pinning (retirement_threshold=32, max 8 error ways/set,
                   dynamic error latency)

Error rates: same time-based CYCLE intervals as single-core (DIMM-level rate
is independent of core count).
"""

import json
import os
import copy

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

NUM_CORES = 4

# Error cycle interval mapping (same convention as ett_evaluation)
INTERVAL_MAP = {
    "1e-6": 14400000,
    "1e-7": 1440000,
}

# Base template: identical to single-core template except num_cores and LLC size.
# NOTE: PTW section intentionally has no "lower_level" — config defaults wire
# each cpuN_PTW to its own cpuN_L1D (a global "cpu0_L1D" would mis-wire cores 1-3).
TEMPLATE = {
    "block_size": 64,
    "page_size": 2097152,
    "heartbeat_frequency": 10000000,
    "num_cores": NUM_CORES,
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
        "pscl4_set": 1, "pscl4_way": 4,
        "pscl3_set": 2, "pscl3_way": 4,
        "pscl2_set": 4, "pscl2_way": 8,
        "rq_size": 16, "mshr_size": 5, "max_read": 2, "max_write": 2
    },
    "LLC": {
        "frequency": 4000, "sets": 8192, "ways": 16,
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

EPM_NO_ERROR = {
    "mode": "OFF",
    "error_latency_penalty": 454568,
    "debug": 0
}

EPM_PINNING_ON = {
    "mode": "CYCLE",
    "cache_pinning": True,
    "dynamic_error_latency": True,
    "error_latency_penalty": 454568,
    "retirement_threshold": 32,
    "max_error_ways_per_set": 8,
    "debug": 0
}

EPM_PINNING_OFF = {
    "mode": "CYCLE",
    "cache_pinning": False,
    "dynamic_error_latency": False,
    "error_latency_penalty": 454568,
    "baseline_retirement_threshold": 2,
    "debug": 0
}


def write_config(path, config):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w') as f:
        json.dump(config, f, indent=2)
        f.write('\n')
    print(f"  Created: {os.path.relpath(path, BASE_DIR)}")


def make_config(exe_name, epm):
    cfg = copy.deepcopy(TEMPLATE)
    cfg["executable_name"] = exe_name
    cfg["error_page_manager"] = copy.deepcopy(epm)
    return cfg


def main():
    print("=== 4-core multicore configs (8MB LLC, 2MB page) ===")

    # No-error upper bound
    cfg = make_config("champsim_4core_8mb_noerr", EPM_NO_ERROR)
    write_config(os.path.join(BASE_DIR, "no_error", "4core_8MBLLC_2MBPage_noerr.json"), cfg)

    for rate_name, interval in INTERVAL_MAP.items():
        # Conventional page offline (pinning OFF)
        epm = copy.deepcopy(EPM_PINNING_OFF)
        epm["error_cycle_interval"] = interval
        cfg = make_config(f"champsim_4core_8mb_off_{rate_name}", epm)
        write_config(os.path.join(BASE_DIR, "pinning_off",
                                  f"4core_8MBLLC_2MBPage_off_{rate_name}.json"), cfg)

        # LLC pinning (pinning ON)
        epm = copy.deepcopy(EPM_PINNING_ON)
        epm["error_cycle_interval"] = interval
        cfg = make_config(f"champsim_4core_8mb_pin_{rate_name}", epm)
        write_config(os.path.join(BASE_DIR, "pinning_on",
                                  f"4core_8MBLLC_2MBPage_pin_{rate_name}.json"), cfg)

    print("Done.")


if __name__ == "__main__":
    main()
