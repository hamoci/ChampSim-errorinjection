#include "error_page_manager.h"
#include "champsim.h"
#include "dram_controller.h"
#include <fmt/core.h>
#include <random>
#include <algorithm>
#include <cmath>
#include <cstdlib>

// Static member initialization
std::unique_ptr<ErrorPageManager> ErrorPageManager::instance = nullptr;

// ============================================================
// Error Recording (MC CE_flag based — no bloom filter)
// ============================================================

ErrorRecordResult ErrorPageManager::record_error(uint64_t pa) {
    uint64_t page_base = get_page_base_pa(pa);
    uint64_t cl_addr = get_cache_line_addr(pa);

    if (debug == 1) {
        fmt::print("[ERROR_REC] ---- record_error(pa=0x{:x}) ----\n", pa);
        fmt::print("[ERROR_REC]   page_base=0x{:x}  cl_addr=0x{:x}\n", page_base, cl_addr);
    }

    // === Duplicate check via exact address set ===
    if (error_addresses.count(cl_addr) > 0) {
        stat_already_known_count++;
        if (debug == 1) {
            fmt::print("[ERROR_REC]   ALREADY_KNOWN: address 0x{:x} already tracked\n", cl_addr);
        }
        return ErrorRecordResult::ALREADY_KNOWN;
    }

    // === New error: increment counter ===
    uint32_t old_counter = page_error_counters[page_base];
    uint32_t new_count = old_counter + 1;
    page_error_counters[page_base] = new_count;

    // Register the exact error address
    error_addresses.insert(cl_addr);

    if (debug == 1) {
        fmt::print("[ERROR_REC]   counter: {} -> {}", old_counter, new_count);
        if (new_count >= retirement_threshold) {
            fmt::print("  (>= threshold {})\n", retirement_threshold);
        } else {
            fmt::print("  (threshold={})\n", retirement_threshold);
        }
    }

    // === Retirement check ===
    if (new_count >= retirement_threshold) {
        retire_page(page_base);
        stat_retirement_count++;
        if (debug == 1) {
            fmt::print("[ERROR_REC]   => PAGE_RETIRED\n");
        }
        return ErrorRecordResult::PAGE_RETIRED;
    }

    if (new_count == 1) {
        stat_first_error_count++;
        if (debug == 1) {
            fmt::print("[ERROR_REC]   => FIRST_ERROR\n");
        }
        return ErrorRecordResult::FIRST_ERROR;
    } else {
        stat_added_error_count++;
        if (debug == 1) {
            fmt::print("[ERROR_REC]   => ADDED_ERROR (count={})\n", new_count);
        }
        return ErrorRecordResult::ADDED_ERROR;
    }
}

void ErrorPageManager::retire_page(uint64_t page_base, bool queue_llc_sweep) {
    if (debug == 1) {
        fmt::print("[ERROR_REC]   RETIRE page=0x{:x}:\n", page_base);
    }

    // 1. Remove page error counters (both pinning ON and baseline paths)
    page_error_counters.erase(page_base);
    baseline_page_error_counts.erase(page_base);
    if (debug == 1) {
        fmt::print("[ERROR_REC]     1. page_error_counters: erased\n");
    }

    // 2. Move error addresses of this page from error_addresses → retired_error_addresses
    //    (set-based, unique-cl semantics; bounded by working set so snapshot is time-stable)
    constexpr uint64_t page_mask = CareEccCache::PAGE_BASE_MASK;
    size_t removed = 0;
    for (auto it = error_addresses.begin(); it != error_addresses.end(); ) {
        if ((*it & page_mask) == page_base) {
            retired_error_addresses.insert(*it);
            it = error_addresses.erase(it);
            removed++;
        } else {
            ++it;
        }
    }
    if (debug == 1) {
        fmt::print("[ERROR_REC]     2. error_addresses: removed {} entries (retired_set size now {})\n",
                   removed, retired_error_addresses.size());
    }

    // 3. Queue page for LLC error way sweep
    if (queue_llc_sweep) {
        pending_retirement_pages.push_back(page_base);
        if (debug == 1) {
            fmt::print("[ERROR_REC]     3. pending_retirement_pages: queued (total pending={})\n",
                       pending_retirement_pages.size());
        }
    }

    // 4. Clustered fault model: permanent retirement + fault lifecycle.
    //    UNIFORM keeps the legacy re-registration artifact (bit-identical).
    if (spatial_model == ErrorSpatialModel::CLUSTERED || spatial_model == ErrorSpatialModel::STICKY) {
        // Permanent retire + fault lifecycle (CELL/ROW die, BANK survives).
        // STICKY has no pending queue, so the resample loop inside is a no-op.
        on_page_retired_clustered(page_base);
    }
}

bool ErrorPageManager::record_baseline_error(uint64_t pa) {
    uint64_t page_base = get_page_base_pa(pa);
    uint64_t cl_addr   = get_cache_line_addr(pa);

    // Snapshot tracking for baseline Protection Coverage (unique cl_addr).
    // Duplicate cl_addr inserts are natural no-ops via set semantics.
    error_addresses.insert(cl_addr);

    auto& count = baseline_page_error_counts[page_base];
    count++;
    if (count >= baseline_retirement_threshold) {
        retire_page(page_base);                 // moves cl_addrs to retired_error_addresses,
                                                // erases counter, queues LLC sweep (no-op when no error ways)
        stat_baseline_retirement_count++;
        if (debug == 1) {
            fmt::print("[BASELINE_RETIRE] page=0x{:x} retired (threshold={}) pa=0x{:x}\n",
                       page_base, baseline_retirement_threshold, pa);
        }
        return true;
    }
    return false;
}

// ============================================================
// Spatial fault model (CLUSTERED) — Poisson cluster injection
// ============================================================
//
// Temporal layer: homogeneous Poisson process (exponential inter-arrival,
// mean = error_cycle_interval CPU cycles) on a dedicated seeded RNG, so the
// expected total error count matches the configured rate exactly.
//
// Spatial layer: every arrival is a manifestation of a persistent FaultDomain.
// With probability fault_reuse_prob it re-manifests an existing fault
// (concentration); otherwise a new fault is created with a mode sampled from
// the cell/row/bank weights. A new fault is unanchored: the next serviced read
// (any address) anchors it, inheriting that access's (bank, row, line) — this
// keeps every error on data the workload actually touches. Re-manifestations
// only consume on reads inside the fault's region (line / row / bank).
//
// Count preservation: a manifestation that no access matches within
// error_starvation_cycles falls back to "any read" (starved), so the total
// injected count still follows the Poisson budget; the fallback is counted.

void ErrorPageManager::update_clustered_errors(uint64_t current_cycle) {
    if (!injection_initialized) {
        temporal_rng.seed(error_seed);
        spatial_rng.seed(error_seed ^ 0x9E3779B97F4A7C15ULL);  // decorrelate streams
        std::exponential_distribution<double> d(1.0 / static_cast<double>(error_cycle_interval));
        next_error_cycle = current_cycle + std::max<uint64_t>(1, static_cast<uint64_t>(std::llround(d(temporal_rng))));
        injection_initialized = true;
    }

    // Catch up all arrivals scheduled at or before this cycle (true Poisson:
    // several arrivals may share a slow-clock window).
    std::exponential_distribution<double> d(1.0 / static_cast<double>(error_cycle_interval));
    while (current_cycle >= next_error_cycle) {
        spawn_manifest(next_error_cycle);
        next_error_cycle += std::max<uint64_t>(1, static_cast<uint64_t>(std::llround(d(temporal_rng))));
    }

    // Starvation aging: staged widening (exact -> fault's bank -> any read).
    // The bank stage keeps a stalled manifestation inside its fault's bank,
    // preserving spatial clustering; the any stage preserves the error count.
    for (auto& ev : pending_manifests) {
        uint64_t age = current_cycle - ev.fire_cycle;
        uint8_t target = (age > 2 * error_starvation_cycles) ? 2 : (age > error_starvation_cycles) ? 1 : 0;
        if (target > ev.widen) {
            if (target >= 1 && ev.widen < 1) stat_widened_bank++;
            if (target >= 2 && ev.widen < 2) stat_widened_any++;
            ev.widen = target;
            if (debug == 1) {
                fmt::print("[FAULT] manifestation of fault {} starved (fired at cycle {}), widened to {}\n",
                           ev.fault_idx, ev.fire_cycle, target == 1 ? "bank" : "any-read");
            }
        }
    }
}

// Pick the fault a new manifestation belongs to: reuse a live fault with
// probability fault_reuse_prob, otherwise create a new one. Dead faults
// (killed by page retirement) are excluded from the reuse pool.
size_t ErrorPageManager::select_fault_for_manifest() {
    std::uniform_real_distribution<double> u(0.0, 1.0);

    if (!live_fault_indices.empty() && u(spatial_rng) < fault_reuse_prob) {
        std::uniform_int_distribution<size_t> pick(0, live_fault_indices.size() - 1);
        return live_fault_indices[pick(spatial_rng)];
    }

    // New fault: sample mode from configured weights; every fault lives in
    // one x8 device (byte lane), sampled uniformly (CARE chip counters).
    double total = fault_weight_cell + fault_weight_row + fault_weight_bank;
    double r = u(spatial_rng) * total;
    FaultMode fault_mode = (r < fault_weight_cell)                     ? FaultMode::CELL
                         : (r < fault_weight_cell + fault_weight_row)  ? FaultMode::ROW
                                                                       : FaultMode::BANK;
    FaultDomain f{fault_mode};
    std::uniform_int_distribution<int> chip_pick(0, CareEccCache::NUM_GLOBAL_COUNTERS - 1);
    f.chip = static_cast<uint8_t>(chip_pick(spatial_rng));
    faults.push_back(f);
    size_t fault_idx = faults.size() - 1;
    live_fault_indices.push_back(fault_idx);
    stat_faults_created[static_cast<size_t>(fault_mode)]++;
    if (debug == 1) {
        fmt::print("[FAULT] new fault {} mode={} chip={}\n", fault_idx,
                   fault_mode == FaultMode::CELL ? "CELL" : fault_mode == FaultMode::ROW ? "ROW" : "BANK", f.chip);
    }
    return fault_idx;
}

void ErrorPageManager::spawn_manifest(uint64_t fire_cycle) {
    pending_manifests.push_back(PendingManifest{select_fault_for_manifest(), fire_cycle});
    stat_pending_peak = std::max(stat_pending_peak, pending_manifests.size());
}

// Page retirement under the clustered model: the page's data migrated to a
// healthy frame, so (1) the PA never records errors again, and (2) CELL/ROW
// faults anchored inside the page die — their future Poisson share is
// resampled onto live faults (count preservation, user decision 2026-07-15).
// BANK faults survive: bank circuitry is not fixed by migrating one page.
void ErrorPageManager::on_page_retired_clustered(uint64_t page_base) {
    clustered_retired_pages.insert(page_base);

    bool killed_any = false;
    for (auto it = live_fault_indices.begin(); it != live_fault_indices.end(); ) {
        FaultDomain& f = faults[*it];
        bool in_page = f.anchored && (f.anchor_cl & CareEccCache::PAGE_BASE_MASK) == page_base;
        if (in_page && (f.mode == FaultMode::CELL || f.mode == FaultMode::ROW)) {
            f.dead = true;
            stat_faults_killed[static_cast<size_t>(f.mode)]++;
            killed_any = true;
            if (debug == 1) {
                fmt::print("[FAULT] fault {} ({}) killed by retirement of page 0x{:x}\n",
                           *it, f.mode == FaultMode::CELL ? "CELL" : "ROW", page_base);
            }
            if (spatial_model == ErrorSpatialModel::STICKY) {   // keep the anchored bucket in sync
                auto bucket_it = sticky_anchored_by_bank.find(f.bank_key);
                if (bucket_it != sticky_anchored_by_bank.end()) {
                    auto& bucket = bucket_it->second;
                    auto p = std::lower_bound(bucket.begin(), bucket.end(), *it);
                    if (p != bucket.end() && *p == *it) bucket.erase(p);
                }
            }
            it = live_fault_indices.erase(it);
        } else {
            ++it;
        }
    }

    if (killed_any) {
        for (auto& ev : pending_manifests) {
            if (faults[ev.fault_idx].dead) {
                ev.fault_idx = select_fault_for_manifest();
                stat_resampled_manifests++;
            }
        }
    }
}

bool ErrorPageManager::consume_clustered_error(uint64_t cl_addr, uint64_t bank_key, uint64_t row) {
    // Reads to a retired page address the migrated-to healthy frame:
    // never consume (neither anchoring nor widened fallback) there.
    if (clustered_retired_pages.count(cl_addr & CareEccCache::PAGE_BASE_MASK) > 0) {
        return false;
    }

    for (auto it = pending_manifests.begin(); it != pending_manifests.end(); ++it) {
        FaultDomain& f = faults[it->fault_idx];
        bool anchored_now = false;
        bool match = false;

        if (!f.anchored) {
            // First manifestation anchors the fault at this access
            f.anchored = true;
            f.bank_key = bank_key;
            f.row = row;
            f.anchor_cl = cl_addr;
            anchored_now = true;
            match = true;
        } else {
            switch (f.mode) {
            case FaultMode::CELL: match = (cl_addr == f.anchor_cl); break;
            case FaultMode::ROW:  match = (bank_key == f.bank_key && row == f.row); break;
            case FaultMode::BANK: match = (bank_key == f.bank_key); break;
            }
            // Staged starvation widening: bank first, then anywhere
            if (!match && it->widen >= 1) match = (bank_key == f.bank_key);
            if (!match && it->widen >= 2) match = true;
        }

        if (match) {
            f.manifest_count++;
            stat_manifests[static_cast<size_t>(f.mode)]++;
            if (anchored_now) stat_anchor_manifests++;
            last_consumed_chip = f.chip;
            record_error_location(cl_addr, bank_key, row);
            if (debug == 1) {
                fmt::print("[FAULT] manifest fault {} mode={} cl=0x{:x} bank_key=0x{:x} row={}{}{}\n",
                           it->fault_idx,
                           f.mode == FaultMode::CELL ? "CELL" : f.mode == FaultMode::ROW ? "ROW" : "BANK",
                           cl_addr, bank_key, row,
                           anchored_now ? " (anchor)" : "", it->widen > 0 ? " (widened)" : "");
            }
            pending_manifests.erase(it);
            return true;
        }
    }
    return false;
}

// ============================================================
// Sticky hard-fault model (doc 10) — access-driven CE + per-mode density
// ============================================================
//
// Temporal layer: the same seeded Poisson process (mean = error_cycle_interval)
// now births persistent FAULTS instead of a CE budget. Faults accumulate over
// time; CELL/ROW die on page retirement, BANK survive.
//
// Spatial layer: a fault is a fixed region anchored to the first real access
// (working-set guarantee). Within the region a line is "bad" with probability
// fault_density_bank for BANK (a single-bank fault is a scattered subset, NOT
// the whole bank) and 1.0 for CELL/ROW (dense, tiny footprint). A bad line emits
// a CE on EVERY access (hard fault). No Poisson CE budget, no starvation
// widening: clustering is structural, count is bounded physically by density x
// access rate.

void ErrorPageManager::update_sticky_faults(uint64_t current_cycle) {
    if (!injection_initialized) {
        temporal_rng.seed(error_seed);
        spatial_rng.seed(error_seed ^ 0x9E3779B97F4A7C15ULL);  // decorrelate streams
        std::exponential_distribution<double> d(1.0 / static_cast<double>(error_cycle_interval));
        next_error_cycle = current_cycle + std::max<uint64_t>(1, static_cast<uint64_t>(std::llround(d(temporal_rng))));
        injection_initialized = true;
    }
    std::exponential_distribution<double> d(1.0 / static_cast<double>(error_cycle_interval));
    while (current_cycle >= next_error_cycle) {          // catch-up: true Poisson births
        birth_fault();
        next_error_cycle += std::max<uint64_t>(1, static_cast<uint64_t>(std::llround(d(temporal_rng))));
    }
}

// Create one persistent fault (mode ~ FIT weights, chip ~ uniform byte lane),
// left unanchored; the next serviced read fixes its coordinates. No reuse
// branch: clustering comes from the fault being a fixed region, not resampling.
void ErrorPageManager::birth_fault() {
    std::uniform_real_distribution<double> u(0.0, 1.0);

    // Co-location (doc 11): with probability fault_colocate_prob, cluster this new
    // fault into an existing ANCHORED fault's region — inherit its chip (defects on
    // one weak die correlate) and target its bank[, row-group]. The co-located
    // fault is unanchored but will only anchor to a read INSIDE that target region
    // (see consume_sticky_error), so it lands near its parent on real accesses.
    // Its mode/salt are its own. Models defect spatial correlation; p=0 => current
    // independent behavior (bit-identical).
    bool colocate = fault_colocate_prob > 0.0 && !live_fault_indices.empty()
                    && u(spatial_rng) < fault_colocate_prob;

    double total = fault_weight_cell + fault_weight_row + fault_weight_bank;
    double r = u(spatial_rng) * total;
    FaultMode fault_mode = (r < fault_weight_cell)                    ? FaultMode::CELL
                         : (r < fault_weight_cell + fault_weight_row) ? FaultMode::ROW
                                                                      : FaultMode::BANK;
    FaultDomain f{fault_mode};

    if (colocate) {
        // Pick the parent only among ANCHORED live faults. An unanchored parent
        // has no coordinates yet (bank_key defaults to 0), so inheriting from it
        // would target bank 0 instead of the parent's real region (a spurious
        // concentration artifact). Requiring an anchored parent also guarantees
        // the target region was actually accessed, which reduces co-located
        // starvation. If nothing is anchored yet, fall back to an independent fault.
        std::vector<size_t> anchored_parents;
        anchored_parents.reserve(live_fault_indices.size());
        for (size_t idx : live_fault_indices)
            if (faults[idx].anchored) anchored_parents.push_back(idx);
        if (!anchored_parents.empty()) {
            std::uniform_int_distribution<size_t> pick(0, anchored_parents.size() - 1);
            const FaultDomain& parent = faults[anchored_parents[pick(spatial_rng)]];
            f.chip = parent.chip;                        // inherit lane
            f.colocated = true;
            f.target_bank_key = parent.bank_key;
            f.target_rowgroup = fault_colocate_scope_set ? (parent.row >> care_row_group_shift) : 0;
            f.salt = spatial_rng();
            stat_colocated_faults++;
        } else {
            colocate = false;   // no anchored parent yet -> independent fault
        }
    }
    if (!colocate) {
        std::uniform_int_distribution<int> chip_pick(0, CareEccCache::NUM_GLOBAL_COUNTERS - 1);
        f.chip = static_cast<uint8_t>(chip_pick(spatial_rng));
        f.salt = spatial_rng();   // per-fault hash basis for BANK line density
    }

    faults.push_back(f);
    live_fault_indices.push_back(faults.size() - 1);
    sticky_unanchored.push_back(faults.size() - 1);   // new fault is unanchored (birth order preserved)
    stat_faults_created[static_cast<size_t>(fault_mode)]++;
    if (debug == 1) {
        fmt::print("[FAULT] birth fault {} mode={} chip={}{}\n", faults.size() - 1,
                   fault_mode == FaultMode::CELL ? "CELL" : fault_mode == FaultMode::ROW ? "ROW" : "BANK", f.chip,
                   colocate ? fmt::format(" colocated->bank_key=0x{:x}", f.target_bank_key) : "");
    }
}

// Deterministic, sticky per-line bad classification. CELL/ROW: whole (small)
// region bad. BANK: sparse subset at fault_density_bank (same line -> same
// verdict across accesses, no per-line storage).
bool ErrorPageManager::is_bad_line(const FaultDomain& f, uint64_t cl_addr) const {
    if (f.mode != FaultMode::BANK) return true;   // CELL/ROW dense
    uint64_t h = (cl_addr ^ f.salt) * 0x9E3779B97F4A7C15ULL;
    double frac = static_cast<double>(h >> 40) / static_cast<double>(1ULL << 24);  // in [0,1)
    return frac < fault_density_bank;
}

bool ErrorPageManager::consume_sticky_error(uint64_t cl_addr, uint64_t bank_key, uint64_t row) {
    // Reads to a retired page address the migrated-to healthy frame: never error.
    if (clustered_retired_pages.count(cl_addr & CareEccCache::PAGE_BASE_MASK) > 0) {
        return false;
    }

    // (1) Anchor the first ELIGIBLE unanchored fault to this real access — a fault
    //     never lands on memory the workload does not touch (working-set guarantee).
    //     Fresh faults anchor to any read; co-located faults (doc 11) only anchor
    //     to a read inside their target region (parent's bank[, row-group]) so they
    //     land near their parent -> per-set/per-bank concentration on one chip.
    for (auto uit = sticky_unanchored.begin(); uit != sticky_unanchored.end(); ++uit) {
        size_t idx = *uit;
        FaultDomain& f = faults[idx];   // every entry here is live and unanchored by construction
        if (f.colocated) {
            if (bank_key != f.target_bank_key) continue;
            if (fault_colocate_scope_set && (row >> care_row_group_shift) != f.target_rowgroup) continue;
        }
        f.anchored = true;
        f.bank_key = bank_key;
        f.row = row;
        f.anchor_cl = cl_addr;
        stat_anchor_manifests++;
        sticky_unanchored.erase(uit);   // leaves the unanchored pool (order of the rest preserved)
        // enter the bank bucket, kept ascending by fault index (== birth order == full-scan order)
        auto& bucket = sticky_anchored_by_bank[bank_key];
        bucket.insert(std::upper_bound(bucket.begin(), bucket.end(), idx), idx);
        break;   // at most one anchor per access
    }

    // (2) Access hits a bad line of a live anchored fault -> hard fault -> CE.
    //     First matching fault wins (any owning fault is physically valid).
    auto bucket_it = sticky_anchored_by_bank.find(bank_key);
    if (bucket_it != sticky_anchored_by_bank.end()) {
        for (size_t idx : bucket_it->second) {   // ascending fault index == birth order == full-scan order
            FaultDomain& f = faults[idx];        // every entry here is anchored with f.bank_key == bank_key
            bool in_region =
                (f.mode == FaultMode::CELL) ? (cl_addr == f.anchor_cl)
              : (f.mode == FaultMode::ROW)  ? (bank_key == f.bank_key && row == f.row)
                                            : (bank_key == f.bank_key);   // BANK
            if (in_region && is_bad_line(f, cl_addr)) {
                f.manifest_count++;
                stat_manifests[static_cast<size_t>(f.mode)]++;
                last_consumed_chip = f.chip;
                record_error_location(cl_addr, bank_key, row);
                if (debug == 1) {
                    fmt::print("[FAULT] sticky CE fault {} mode={} cl=0x{:x} bank_key=0x{:x} row={}\n", idx,
                               f.mode == FaultMode::CELL ? "CELL" : f.mode == FaultMode::ROW ? "ROW" : "BANK",
                               cl_addr, bank_key, row);
                }
                return true;
            }
        }
    }
    return false;
}

void ErrorPageManager::print_sticky_stats() const {
    uint64_t total_faults = stat_faults_created[0] + stat_faults_created[1] + stat_faults_created[2];
    uint64_t total_manifests = stat_manifests[0] + stat_manifests[1] + stat_manifests[2];
    size_t unanchored = 0;
    uint64_t max_manifest = 0;
    for (const auto& f : faults) {
        if (!f.dead && !f.anchored) unanchored++;
        max_manifest = std::max(max_manifest, f.manifest_count);
    }
    fmt::print("[ERROR]\n");
    fmt::print("[ERROR] [Spatial Fault Model (sticky)]\n");
    fmt::print("[ERROR]   Seed / Birth Interval:          {} / {} cyc\n", error_seed, error_cycle_interval);
    fmt::print("[ERROR]   BANK Line Density:              {:.4f}\n", fault_density_bank);
    fmt::print("[ERROR]   Faults Born:                    {} (cell={} row={} bank={})\n",
               total_faults, stat_faults_created[0], stat_faults_created[1], stat_faults_created[2]);
    if (fault_colocate_prob > 0.0) {
        fmt::print("[ERROR]   Co-located Faults:              {} (prob={:.2f}, scope={})\n",
                   stat_colocated_faults, fault_colocate_prob, fault_colocate_scope_set ? "set" : "bank");
    }
    fmt::print("[ERROR]   Faults Killed by Retirement:    {} (cell={} row={})\n",
               stat_faults_killed[0] + stat_faults_killed[1], stat_faults_killed[0], stat_faults_killed[1]);
    fmt::print("[ERROR]   Unanchored (waiting) at End:    {}\n", unanchored);
    fmt::print("[ERROR]   Retired Pages (permanent):      {}\n", clustered_retired_pages.size());
    fmt::print("[ERROR]   Injected CEs (access-driven):   {} (cell={} row={} bank={})\n",
               total_manifests, stat_manifests[0], stat_manifests[1], stat_manifests[2]);
    if (total_faults > 0) {
        fmt::print("[ERROR]   CEs per Fault (avg/max):        {:.1f} / {}\n",
                   static_cast<double>(total_manifests) / static_cast<double>(total_faults), max_manifest);
    }
    if (!bank_manifest_hist.empty() && total_manifests > 0) {
        std::vector<std::pair<uint64_t, uint64_t>> sorted(bank_manifest_hist.begin(), bank_manifest_hist.end());
        std::sort(sorted.begin(), sorted.end(), [](const auto& a, const auto& b) { return a.second > b.second; });
        fmt::print("[ERROR]   Banks Touched:                  {}\n", sorted.size());
        fmt::print("[ERROR]   Top Banks (ch/bank_idx: count):");
        size_t top_n = std::min<size_t>(8, sorted.size());
        for (size_t i = 0; i < top_n; i++) {
            fmt::print(" {}/{}:{}", sorted[i].first >> 32, sorted[i].first & 0xFFFFFFFFULL, sorted[i].second);
        }
        fmt::print("\n");
        fmt::print("[ERROR]   Top-1 Bank Share:               {:.1f}%\n",
                   100.0 * static_cast<double>(sorted[0].second) / static_cast<double>(total_manifests));
    }
    print_location_histograms();
}

void ErrorPageManager::print_spatial_fault_stats() const {
    if (spatial_model == ErrorSpatialModel::CLUSTERED) {
        print_clustered_stats();
    } else if (spatial_model == ErrorSpatialModel::STICKY) {
        print_sticky_stats();
    } else if (location_stats_enabled) {
        // UNIFORM comparison data: opt-in only (legacy output stays identical)
        fmt::print("[ERROR]\n");
        fmt::print("[ERROR] [Error Location Distribution (uniform)]\n");
        print_location_histograms();
    }
}

// Fixed-size summary of where consumed errors landed: distinct counts,
// avg/max per granularity, top-5 hot spots. Output size is independent of
// the number of errors (full dumps would be thousands of lines).
void ErrorPageManager::print_location_histograms() const {
    uint64_t total = 0;
    for (const auto& [k, v] : bank_manifest_hist) total += v;
    if (total == 0) {
        return;
    }

    auto max_count = [](const auto& hist) {
        uint64_t m = 0;
        for (const auto& [k, v] : hist) m = std::max(m, v);
        return m;
    };
    double total_d = static_cast<double>(total);
    fmt::print("[ERROR]   Distinct Lines / Rows / Banks:  {} / {} / {}\n",
               line_manifest_hist.size(), row_manifest_hist.size(), bank_manifest_hist.size());
    fmt::print("[ERROR]   Errors per Line (avg/max):      {:.2f} / {}\n",
               total_d / static_cast<double>(line_manifest_hist.size()), max_count(line_manifest_hist));
    fmt::print("[ERROR]   Errors per Row (avg/max):       {:.2f} / {}\n",
               total_d / static_cast<double>(row_manifest_hist.size()), max_count(row_manifest_hist));
    fmt::print("[ERROR]   Errors per Bank (avg/max):      {:.2f} / {}\n",
               total_d / static_cast<double>(bank_manifest_hist.size()), max_count(bank_manifest_hist));

    std::vector<std::pair<uint64_t, uint64_t>> lines(line_manifest_hist.begin(), line_manifest_hist.end());
    std::sort(lines.begin(), lines.end(), [](const auto& a, const auto& b) { return a.second > b.second; });
    fmt::print("[ERROR]   Top Lines (cl:count):          ");
    for (size_t i = 0; i < std::min<size_t>(5, lines.size()); i++) {
        fmt::print(" 0x{:x}:{}", lines[i].first, lines[i].second);
    }
    fmt::print("\n");

    std::vector<std::pair<std::pair<uint64_t, uint64_t>, uint64_t>> rows(row_manifest_hist.begin(), row_manifest_hist.end());
    std::sort(rows.begin(), rows.end(), [](const auto& a, const auto& b) { return a.second > b.second; });
    fmt::print("[ERROR]   Top Rows (ch/bank/row:count):  ");
    for (size_t i = 0; i < std::min<size_t>(5, rows.size()); i++) {
        fmt::print(" {}/{}/{}:{}", rows[i].first.first >> 32, rows[i].first.first & 0xFFFFFFFFULL,
                   rows[i].first.second, rows[i].second);
    }
    fmt::print("\n");
}

void ErrorPageManager::print_clustered_stats() const {
    uint64_t total_faults = stat_faults_created[0] + stat_faults_created[1] + stat_faults_created[2];
    uint64_t total_manifests = stat_manifests[0] + stat_manifests[1] + stat_manifests[2];

    fmt::print("[ERROR]\n");
    fmt::print("[ERROR] [Spatial Fault Model (clustered)]\n");
    fmt::print("[ERROR]   Seed:                           {}\n", error_seed);
    fmt::print("[ERROR]   Faults Created:                 {} (cell={} row={} bank={})\n",
               total_faults, stat_faults_created[0], stat_faults_created[1], stat_faults_created[2]);
    fmt::print("[ERROR]   Faults Killed by Retirement:    {} (cell={} row={})\n",
               stat_faults_killed[0] + stat_faults_killed[1], stat_faults_killed[0], stat_faults_killed[1]);
    fmt::print("[ERROR]   Resampled Manifestations:       {}\n", stat_resampled_manifests);
    fmt::print("[ERROR]   Retired Pages (permanent):      {}\n", clustered_retired_pages.size());
    fmt::print("[ERROR]   Manifestations (injected CEs):  {} (cell={} row={} bank={})\n",
               total_manifests, stat_manifests[0], stat_manifests[1], stat_manifests[2]);
    fmt::print("[ERROR]     Anchoring (first of a fault): {}\n", stat_anchor_manifests);
    fmt::print("[ERROR]     Starved -> Bank-Widened:      {}\n", stat_widened_bank);
    fmt::print("[ERROR]     Starved -> Any-Widened:       {}\n", stat_widened_any);
    fmt::print("[ERROR]   Pending at End / Peak:          {} / {}\n", pending_manifests.size(), stat_pending_peak);
    if (total_faults > 0) {
        uint64_t max_manifest = 0;
        for (const auto& f : faults) max_manifest = std::max(max_manifest, f.manifest_count);
        fmt::print("[ERROR]   Manifests per Fault (avg/max):  {:.1f} / {}\n",
                   static_cast<double>(total_manifests) / static_cast<double>(total_faults), max_manifest);
    }
    if (!bank_manifest_hist.empty() && total_manifests > 0) {
        std::vector<std::pair<uint64_t, uint64_t>> sorted(bank_manifest_hist.begin(), bank_manifest_hist.end());
        std::sort(sorted.begin(), sorted.end(), [](const auto& a, const auto& b) { return a.second > b.second; });
        fmt::print("[ERROR]   Banks Touched:                  {}\n", sorted.size());
        fmt::print("[ERROR]   Top Banks (ch/bank_idx: count):");
        size_t top_n = std::min<size_t>(8, sorted.size());
        for (size_t i = 0; i < top_n; i++) {
            fmt::print(" {}/{}:{}", sorted[i].first >> 32, sorted[i].first & 0xFFFFFFFFULL, sorted[i].second);
        }
        fmt::print("\n");
        fmt::print("[ERROR]   Top-1 Bank Share:               {:.1f}%\n",
                   100.0 * static_cast<double>(sorted[0].second) / static_cast<double>(total_manifests));
    }
    print_location_histograms();
}

// ============================================================
// CARE scheme (HPCA'21) — reactive-only, hard-error-only
// ============================================================

void ErrorPageManager::init_care_cache() {
    // Fail fast with a config-pointing message; the constructor's assert would
    // vanish under -DNDEBUG.
    if (care_ecc_sets == 0 || (care_ecc_sets & (care_ecc_sets - 1)) != 0 || care_ecc_ways == 0) {
        fmt::print("[ERROR_PAGE_MANAGER] FATAL: care_ecc_sets must be a nonzero power of two and care_ecc_ways nonzero (got {} x {})\n",
                   care_ecc_sets, care_ecc_ways);
        std::abort();
    }
    if (care_row_groups == 0) {
        fmt::print("[ERROR_PAGE_MANAGER] FATAL: CARE DRAM geometry not initialized (set_care_dram_geometry must run before init_care_cache)\n");
        std::abort();
    }
    care_cache = std::make_unique<CareEccCache>(care_ecc_sets, care_ecc_ways, care_proactive, care_proactive_or, care_retire_on_confirm);
}

void ErrorPageManager::set_care_dram_geometry(uint64_t channels, uint64_t banks_per_channel, uint64_t rows,
                                              uint64_t row_bit_offset) {
    care_banks_per_channel = banks_per_channel;
    care_total_banks = channels * banks_per_channel;
    care_row_bit_offset = row_bit_offset;
    care_row_count = rows;
    if (care_total_banks == 0 || care_ecc_sets % care_total_banks != 0) {
        fmt::print("[ERROR_PAGE_MANAGER] FATAL: care_ecc_sets ({}) must be a multiple of total DRAM banks ({} = {} ch x {}/ch) for the paper set index\n",
                   care_ecc_sets, care_total_banks, channels, banks_per_channel);
        std::abort();
    }
    care_row_groups = care_ecc_sets / care_total_banks;
    uint64_t row_bits = 0;
    while ((1ULL << row_bits) < rows) row_bits++;
    uint64_t group_bits = 0;
    while ((1ULL << group_bits) < care_row_groups) group_bits++;
    if (group_bits > row_bits) {
        fmt::print("[ERROR_PAGE_MANAGER] FATAL: row groups ({}) exceed row count ({})\n", care_row_groups, rows);
        std::abort();
    }
    care_row_group_shift = row_bits - group_bits;
    fmt::print("[ERROR_PAGE_MANAGER] CARE set index: {} banks x {} row-groups (row shift {}) = {} sets (paper III.B.3 layout)\n",
               care_total_banks, care_row_groups, care_row_group_shift, care_ecc_sets);
}

// Paper-literal proactive victims (III.C): every allocated page whose row range
// overlaps the triggering set's row-group. With fine block interleaving each such
// page has blocks in the region's (bank, row) pairs, so this is exactly "all the
// pages that contain all the rows the set is designed to protect". Excludes pages
// already permanently retired. Sorted for deterministic retirement order.
std::vector<uint64_t> ErrorPageManager::care_region_victim_pages(uint64_t row_group) const {
    std::vector<uint64_t> pages;
    for (uint64_t page_num : current_ppage) {
        uint64_t page_base = page_num << LOG2_PAGE_SIZE;
        uint64_t r0 = care_row_of_pa(page_base) >> care_row_group_shift;
        uint64_t r1 = care_row_of_pa(page_base + PAGE_SIZE - 1) >> care_row_group_shift;
        if (r0 <= row_group && row_group <= r1 && clustered_retired_pages.count(page_base) == 0) {
            pages.push_back(page_base);
        }
    }
    std::sort(pages.begin(), pages.end());
    return pages;
}

CareEccCache::ReadOutcome ErrorPageManager::care_on_read(uint64_t pa, uint32_t cpu_idx, uint64_t bank_key, uint64_t row) {
    uint64_t cl_addr = get_cache_line_addr(pa);
    size_t set = care_set_index(bank_key, row);
    last_proactive_victims = 0;   // handoff to service_packet: victims of THIS call only
    auto out = care_cache->on_read(cl_addr, set);

    if (debug == 1 && out.promoted_s3) {
        fmt::print("[CARE] S2->S3 addr=0x{:x} (hard error confirmed)\n", cl_addr);
    }

    if (out.retire) {
        care_execute_retirement(pa, cpu_idx, bank_key, row, set, out, "s3read");
    }
    return out;
}

void ErrorPageManager::care_execute_retirement(uint64_t pa, uint32_t cpu_idx, uint64_t bank_key, uint64_t row,
                                               size_t set, const CareEccCache::ReadOutcome& out, const char* src) {
    uint64_t cl_addr = get_cache_line_addr(pa);
    uint64_t page_base = get_page_base_pa(pa);
    last_proactive_victims = 0;   // handoff to service_packet: victims of THIS retirement only

    // Proactive victim list must be collected before any invalidation:
    // the triggering page is still in the observed list here.
    std::vector<uint64_t> proactive_victims;
    if (out.proactive) {
        proactive_victims = care_region_victims
            ? care_region_victim_pages(row >> care_row_group_shift)   // paper-literal
            : care_cache->region_error_pages(set);                    // evidence-based
    }

    size_t invalidated = care_cache->invalidate_page(page_base);
    retire_page(page_base, /*queue_llc_sweep=*/false);  // coverage move + counter erase; no sweep consumer under CARE
    stat_care_retirement_count++;
    per_cpu_error_stats[cpu_idx].care_retirements++;
    // Always-on event log (plan P3b): reactive retirements are rare
    // (tens per run) so this is grep-friendly signal, not noise.
    fmt::print("[CARE][RETIRE] page=0x{:x} trigger_cl=0x{:x} set={} chip={} err_count={} cpu={} ecc_invalidated={} src={}\n",
               page_base, cl_addr, set, out.entry_chip, out.entry_err_count, cpu_idx, invalidated, src);

    if (out.proactive) {
        // Paper III.C: retire everything the set protects. The batch is a
        // synchronous offline: each victim adds one page-offline penalty to
        // the triggering packet (handoff via last_proactive_victims — the
        // interrupted core pays migration of the whole batch).
        for (uint64_t victim : proactive_victims) {
            if (victim == page_base) continue;
            if (clustered_retired_pages.count(victim) > 0) continue;  // already permanently retired
            size_t v_inv = care_cache->invalidate_page(victim);
            retire_page(victim, /*queue_llc_sweep=*/false);
            stat_care_proactive_page_count++;
            last_proactive_victims++;
            if (debug == 1) {
                fmt::print("[CARE] PROACTIVE RETIRE page=0x{:x} (set {}) ecc_entries_invalidated={}\n",
                           victim, set, v_inv);
            }
        }
        // Always-on event log (plan P3b): region = (bank, row-group)
        fmt::print("[CARE][PROACTIVE] mode={} set={} biased_chip={} bias={} bank_key=0x{:x} row_group={} victims={} pages=[",
                   care_region_victims ? "region" : "observed",
                   set, out.biased_chip, out.bias, bank_key, row >> care_row_group_shift, proactive_victims.size());
        for (size_t i = 0; i < proactive_victims.size(); i++) {
            fmt::print("{}0x{:x}", i ? " " : "", proactive_victims[i]);
        }
        fmt::print("]\n");
    }
}

void ErrorPageManager::care_on_write(uint64_t pa, uint64_t bank_key, uint64_t row) {
    uint64_t cl_addr = get_cache_line_addr(pa);
    bool confirmed = care_cache->on_write(cl_addr, care_set_index(bank_key, row));
    if (debug == 1 && confirmed) {
        fmt::print("[CARE] S1->S2 addr=0x{:x} (write confirmation)\n", cl_addr);
    }
}

bool ErrorPageManager::care_on_injected_error(uint64_t pa, uint32_t cpu_idx, uint64_t bank_key, uint64_t row) {
    uint64_t cl_addr = get_cache_line_addr(pa);

    // Ground-truth faulty-line set for the Protection Coverage metric (D8) —
    // and, under celog-confirm, the model's stand-in for the MC CE log: a
    // failed insert means this line has errored before (repeat CE).
    // LLC pinning consumers of error_addresses are all is_cache_pinning_enabled()-gated.
    // Note: like the baseline path, a line of an already-retired page re-enters this
    // set on re-injection while staying in retired_error_addresses — a shared
    // simulation artifact across schemes (coverage double-count, plan D5).
    bool repeat = !error_addresses.insert(cl_addr).second;

    auto& s = per_cpu_error_stats[cpu_idx];
    s.errors_absorbed++;

    size_t set = care_set_index(bank_key, row);

    // Contention-free confirmation ("celog", rationale in care_ecc_cache.h):
    // a repeat CE on an untracked line carries the same evidence as the
    // tracked S2->S3 walk — demand scrubbing rewrote the line after its first
    // CE regardless of admission (paper p.533 fn.1), so this CE is a
    // post-rewrite recurrence = confirmed hard (III.B.2). Admission bounds
    // protection (BCH), not the verdict; the paper's own evaluation runs
    // where sets never contend, so there this path never diverges from
    // residency-based confirmation. Gated on demand scrubbing: without the
    // scrub write the second CE is not post-rewrite evidence.
    if (care_celog_confirm && care_demand_scrub && repeat && !care_cache->is_tracked(cl_addr, set)) {
        auto out = care_cache->confirm_untracked(set, last_consumed_chip);
        s.care_celog_retirements++;
        care_execute_retirement(pa, cpu_idx, bank_key, row, set, out, "celog");
        return true;
    }

    switch (care_cache->on_error(cl_addr, set, last_consumed_chip)) {
    case CareEccCache::RegisterOutcome::REGISTERED:
        s.care_registered++;
        if (debug == 1) fmt::print("[CARE] REG addr=0x{:x} set={} chip={} (S1)\n", cl_addr, set, last_consumed_chip);
        if (care_demand_scrub) {
            // MC demand scrub: corrective write follows the CE-detecting read,
            // confirming S1->S2 without waiting for an application writeback.
            care_cache->on_write(cl_addr, set);
            if (debug == 1) fmt::print("[CARE] SCRUB addr=0x{:x} (S1->S2)\n", cl_addr);
        }
        break;
    case CareEccCache::RegisterOutcome::DROPPED:
        s.care_dropped++;
        if (debug == 1) fmt::print("[CARE] DROP addr=0x{:x} (ECC cache set full)\n", cl_addr);
        break;
    case CareEccCache::RegisterOutcome::ALREADY_TRACKED:
        if (debug == 1) fmt::print("[CARE] KNOWN addr=0x{:x} (already tracked)\n", cl_addr);
        break;
    }
    return false;
}

void ErrorPageManager::print_care_stats() const {
    if (!care_cache) {
        fmt::print("\n[CARE] ECC cache not initialized (no stats)\n");
        return;
    }
    const auto& s = care_cache->stats();
    size_t capacity = care_ecc_sets * care_ecc_ways;
    size_t resident = care_cache->occupancy();
    // Repeat-CE confirmations consume an injected error without reaching
    // on_error (they retire instead) — count them so the total is the true
    // consumed-CE count. Zero when celog is off (legacy totals unchanged).
    uint64_t error_events = s.registered + s.errors_on_tracked + s.dropped + s.retires_celog;

    fmt::print("\n[CARE] ========== CARE Scheme Statistics ==========\n");
    fmt::print("[CARE]\n");
    fmt::print("[CARE] [Configuration]\n");
    fmt::print("[CARE]   ECC Cache Geometry:             {} sets x {} ways ({} blocks)\n", care_ecc_sets, care_ecc_ways, capacity);
    fmt::print("[CARE]   BCH Decode Latency:             {} CPU cycles\n", care_bch_decode_cycles);
    fmt::print("[CARE]\n");
    fmt::print("[CARE] [Error Events]\n");
    fmt::print("[CARE]   Total Injected Error Events:    {}\n", error_events);
    fmt::print("[CARE]     Registrations (new S1):       {}\n", s.registered);
    fmt::print("[CARE]     On Already-Tracked Blocks:    {}\n", s.errors_on_tracked);
    fmt::print("[CARE]     Dropped (set full):           {}\n", s.dropped);
    if (care_celog_confirm && care_demand_scrub) {
        fmt::print("[CARE]     Repeat-CE Confirms (retired): {}\n", s.retires_celog);
    }
    fmt::print("[CARE]\n");
    fmt::print("[CARE] [Tracked-Block Accesses]\n");
    fmt::print("[CARE]   BCH Decode Reads (+{} cyc):     {}\n", care_bch_decode_cycles, s.decode_reads);
    fmt::print("[CARE]   S1->S2 Write Confirmations:     {}\n", s.writes_s1_to_s2);
    fmt::print("[CARE]   S2->S3 Hard Confirmations:      {}\n", s.reads_s2_to_s3);
    fmt::print("[CARE]\n");
    fmt::print("[CARE] [Retirement]\n");
    fmt::print("[CARE]   Pages Retired (reactive):       {}\n", stat_care_retirement_count);
    // Breakdown by confirmation path (celog-confirm mimic). Printed only when
    // the celog path is armed so legacy configs keep byte-identical output.
    if (care_celog_confirm && care_demand_scrub) {
        fmt::print("[CARE]     via S3-Read Confirm:          {}\n", s.retires);
        fmt::print("[CARE]     via Repeat-CE Confirm:        {}\n", s.retires_celog);
    }
    if (care_proactive) {
        fmt::print("[CARE]\n");
        fmt::print("[CARE] [Proactive Retirement]\n");
        fmt::print("[CARE]   Triggers:                       {}\n", s.proactive_triggers);
        fmt::print("[CARE]   Pages Retired (proactive):      {}\n", stat_care_proactive_page_count);
        fmt::print("[CARE]   Counter Accumulations:          {}\n", s.gc_accumulations);
        fmt::print("[CARE]   Accounting Rounds Closed:       {}\n", s.gc_resets);
        fmt::print("[CARE]   Peak Counter Value:             {} / {} (saturation)\n", s.gc_peak_value, CareEccCache::GLOBAL_COUNTER_MAX);
        fmt::print("[CARE]   Peak Bias (max-min):            {} / {} (trigger bound)\n", s.gc_peak_bias, CareEccCache::PROACTIVE_BIAS_MIN);
    }
    fmt::print("[CARE]   ECC Entries Invalidated:        {}\n", s.invalidated_entries);
    fmt::print("[CARE]\n");
    fmt::print("[CARE] [Final ECC Cache State]\n");
    fmt::print("[CARE]   Resident Entries:               {} / {} ({:.2f}%)\n", resident, capacity,
               capacity > 0 ? 100.0 * static_cast<double>(resident) / static_cast<double>(capacity) : 0.0);
    fmt::print("[CARE] ============================================\n");
    // Per-CPU care attribution is printed by print_per_cpu_error_stats (gated line)
    // so each CPU appears in exactly one authoritative per-CPU block.
}

void ErrorPageManager::print_error_stats() const {
    uint64_t total_new_recordings = stat_first_error_count + stat_added_error_count;
    uint64_t total_dram_error_events = total_new_recordings + stat_retirement_count + stat_already_known_count;

    // Count multi-error pages from page_error_counters
    uint64_t multi_error_page_count = 0;
    for (const auto& [page, cnt] : page_error_counters) {
        if (cnt >= 2) multi_error_page_count++;
    }
    uint64_t active_single_error_pages = page_error_counters.size() - multi_error_page_count;

    fmt::print("\n[ERROR] ========== Error Recording Statistics ==========\n");

    fmt::print("[ERROR]\n");
    fmt::print("[ERROR] [Configuration]\n");
    fmt::print("[ERROR]   Retirement Threshold:           {}\n", retirement_threshold);
    fmt::print("[ERROR]   Tracked Error Addresses:        {}\n", error_addresses.size());

    fmt::print("[ERROR]\n");
    fmt::print("[ERROR] [DRAM Error Events]\n");
    fmt::print("[ERROR]   Total DRAM Error Events:        {}\n", total_dram_error_events);
    fmt::print("[ERROR]     New Error Recordings:         {}\n", total_new_recordings);
    fmt::print("[ERROR]       First Error (per page):     {}\n", stat_first_error_count);
    fmt::print("[ERROR]       Additional Errors:          {}\n", stat_added_error_count);
    fmt::print("[ERROR]     Page Retirements ({}th err): {}\n", retirement_threshold, stat_retirement_count);
    fmt::print("[ERROR]     Already Known:                {}\n", stat_already_known_count);

    fmt::print("[ERROR]\n");
    fmt::print("[ERROR] [Page Status]\n");
    fmt::print("[ERROR]   Active Pages (tracked):         {}\n", page_error_counters.size());
    fmt::print("[ERROR]     Single-error pages:           {}\n", active_single_error_pages);
    fmt::print("[ERROR]     Multi-error pages:            {}\n", multi_error_page_count);

    fmt::print("[ERROR]\n");
    fmt::print("[ERROR] [Retirement Detail]\n");
    fmt::print("[ERROR]   Pages Retired:                  {}\n", stat_retirement_count);
    fmt::print("[ERROR]   Cache Lines Invalidated:        {}\n", stat_retirement_invalidated_lines);
    if (stat_retirement_count > 0) {
        fmt::print("[ERROR]   Avg Lines per Retirement:       {:.1f}\n",
                   static_cast<double>(stat_retirement_invalidated_lines) / static_cast<double>(stat_retirement_count));
    }

    print_spatial_fault_stats();

    print_per_cpu_error_stats();

    fmt::print("[ERROR] ============================================================\n");
}

void ErrorPageManager::print_per_cpu_error_stats() const {
    if (per_cpu_error_stats.empty()) {
        return;
    }
    fmt::print("[ERROR]\n");
    fmt::print("[ERROR] [Per-CPU Error Attribution]\n");
    for (const auto& [cpu_idx, s] : per_cpu_error_stats) {
        fmt::print("[ERROR]   CPU {}: absorbed={} first={} added={} known={} retired={} baseline_retired={}\n",
                   cpu_idx, s.errors_absorbed, s.first_errors, s.added_errors,
                   s.already_known, s.retirements, s.baseline_retirements);
        // Existing line above stays byte-identical for non-CARE runs; care fields
        // appear on a separate gated line only.
        if (care_enabled) {
            fmt::print("[ERROR]   CPU {}: care_registered={} care_dropped={} care_retired={} care_celog_retired={}\n",
                       cpu_idx, s.care_registered, s.care_dropped, s.care_retirements, s.care_celog_retirements);
        }
    }
}

// ============================================================
// Existing implementations (unchanged)
// ============================================================

void ErrorPageManager::init_page_error_rate(double init_ber) {
    // Store bit error rate
    this->bit_error_rate = init_ber;
    this->page_size_bits = PAGE_SIZE * 8; // Convert bytes to bits

    // Theoretical page error rate
    double theoretical_page_error_rate = 1.0 - std::pow(1.0 - bit_error_rate, static_cast<double>(page_size_bits));
    this->page_error_rate = theoretical_page_error_rate;

    fmt::print("[ERROR_PAGE_MANAGER] Monte Carlo Simulation Results:\n");
    fmt::print("[ERROR_PAGE_MANAGER]   Random Seed: 54321 (fixed)\n");
    fmt::print("[ERROR_PAGE_MANAGER]   Bit Error Rate: {:.2e}\n", bit_error_rate);
    fmt::print("[ERROR_PAGE_MANAGER]   Page Size: {} bytes ({} bits)\n", PAGE_SIZE, page_size_bits);
    fmt::print("[ERROR_PAGE_MANAGER]   Theoretical Page Error Rate: {:.6f} ({:.2e})\n",
               theoretical_page_error_rate, theoretical_page_error_rate);
}

void ErrorPageManager::all_error_pages_on(uint64_t page_num) {

    fmt::print("[ERROR_PAGE_MANAGER] setting all error pages on...\n");

    for (size_t i = 0; i < page_num; i++) {
        uint64_t page_addr = i << LOG2_PAGE_SIZE;
        auto page = get_page_number(champsim::address{page_addr});
        add_error_page(page);
    }

    fmt::print("[ERROR_PAGE_MANAGER] setting all error pages on complete.\n");
}

void ErrorPageManager::print_error_pages() const {
    fmt::print("[ERROR_PAGE_MANAGER] Total error pages: {}\n", error_pages.size());
    fmt::print("[ERROR_PAGE_MANAGER] Error latency penalty: {}\n",
               error_latency_penalty.count());

    if (!error_pages.empty()) {
        fmt::print("[ERROR_PAGE_MANAGER] Error page numbers: ");
        for (const auto& page : error_pages) {
            fmt::print("0x{:x} ", page);
        }
        fmt::print("\n");
    }
}
