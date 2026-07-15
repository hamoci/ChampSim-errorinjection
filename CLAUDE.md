# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

ChampSim is a trace-based microarchitecture simulator. This fork adds **DRAM error page management** and **LLC cache pinning** for research on memory error resilience.

## Build Commands

```bash
# Install dependencies (first time)
git submodule update --init
vcpkg/bootstrap-vcpkg.sh
vcpkg/vcpkg install

# Configure and build (always run config.sh before make)
./config.sh <config.json>
make -j$(nproc)

# Run simulation
bin/<executable_name> --warmup-instructions 200000000 --simulation-instructions 500000000 path/to/trace.xz

# Tests
make test          # C++ tests (Catch2)
make pytest        # Python config tests
```

Build scripts for batch configs: `build_final_rev.sh`, `build_real_final.sh`.

## Architecture

### Simulation Flow
1. `src/main.cc` — CLI parsing (CLI11), trace loading, calls `champsim::main()`
2. `src/champsim.cc` — `do_phase()` → `do_cycle()` loop: sorts operables by time, calls `operate()` on each component, feeds instructions from traces to CPUs

### Core Components (all inherit `champsim::operable`)
- **O3_CPU** (`inc/ooo_cpu.h`, `src/ooo_cpu.cc`) — Out-of-order CPU core
- **CACHE** (`inc/cache.h`, `src/cache.cc`) — Cache hierarchy (L1I/L1D/L2C/LLC, TLBs)
- **PageTableWalker** (`inc/ptw.h`, `src/ptw.cc`) — TLB miss handling, PSC caching
- **DRAM_CHANNEL** (`inc/dram_controller.h`, `src/dram_controller.cc`) — Memory controller
- **VirtualMemory** (`inc/vmem.h`, `src/vmem.cc`) — VA→PA translation

Components communicate via `champsim::channel` queues between cache levels.

### Configuration System
- JSON config files define the full system (caches, CPU, DRAM, TLBs, prefetchers, replacement policies)
- `config/parse.py` parses JSON → `config/defaults.py` fills defaults → `config/instantiation_file.py` generates C++ instantiation code
- Generated code goes to `.csconfig/`
- `champsim::configured::generated_environment<BUILD_ID>` template specializes the system at compile time

### Module System
Pluggable modules in `branch/`, `btb/`, `prefetcher/`, `replacement/` directories. To add a new module, create a subdirectory with a `.cc` file and reference it in the JSON config.

## Custom Research Extensions

### ErrorPageManager (`inc/error_page_manager.h`, `src/error_page_manager.cc`)
Singleton that tracks DRAM errors using a dual-layer scheme:
1. **Inline PDE descriptor** — first error's cache line index (15-bit) + multi-error flag
2. **Error Position Table (EPT)** — 64 entries × 4 slots for 2nd–5th errors per page
3. **Page retirement** — 6th error triggers page offline

Error injection modes: `ALL_ON`, `RANDOM` (BER-based), `CYCLE` (exponential distribution), `OFF`.

Config in JSON under `error_page_manager` section; defaults in `config/defaults.py:error_page_manager_defaults()`.

### LLC Cache Pinning (`src/cache.cc`)
Error data gets pinned to reserved high-index LLC ways (15, 14, 13...). Key functions: `allocate_error_way()`, `find_error_way()`, `find_normal_way()`, `is_error_data()`. Enabled via `cache_pinning: true` in config.

### Dynamic Error Latency (`src/ptw.cc`)
Calculates PTW cost dynamically based on PSC cache state — determines which page table levels are cached and applies appropriate latency. Integrates with `VirtualMemory::ppage_to_vpage_map` for reverse mapping.

## Key Config Files
- `champsim_config_origin.json` — Baseline (4KB pages)
- `champsim_config_2MBLLC_2MBPage_L1D.json` — 2MB page config
- `sim_configs/` — Batch simulation configs organized by experiment

## Stat Scripts
`stat_script_rev/` contains Python scripts for parsing simulation output and generating comparison plots (IPC, RBMPKI, cache way usage, pinning effects).
