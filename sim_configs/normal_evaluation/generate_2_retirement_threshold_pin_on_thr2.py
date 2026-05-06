#!/usr/bin/env python3
"""Generate only retirement-threshold=2 configs with LLC pinning enabled."""

import copy
import os

from generate_configs import (
    BASE_DIR,
    EPM_PINNING_ON,
    INTERVAL_MAP,
    make_config,
    write_config,
)


def main():
    print("\n=== 2. Retirement Threshold: pinning_on threshold=2 only ===")
    for rate_name, interval in INTERVAL_MAP.items():
        epm = copy.deepcopy(EPM_PINNING_ON)
        epm["error_cycle_interval"] = interval
        epm["retirement_threshold"] = 2
        exe = f"retire_on_2_{rate_name}"
        cfg = make_config(exe, epm=epm)
        path = os.path.join(
            BASE_DIR, "2_retirement_threshold", "pinning_on",
            f"threshold_2_{rate_name}.json")
        write_config(path, cfg)
    print("\nDone! threshold=2 pinning_on configs generated.")


if __name__ == "__main__":
    main()
