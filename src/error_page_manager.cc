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
// CARE scheme (HPCA'21) — reactive-only, hard-error-only
// ============================================================

void ErrorPageManager::init_care_cache() {
    // Fail fast with a config-pointing message; the constructor's assert would
    // vanish under -DNDEBUG and the set-index mask would silently alias.
    if (care_ecc_sets == 0 || (care_ecc_sets & (care_ecc_sets - 1)) != 0 || care_ecc_ways == 0) {
        fmt::print("[ERROR_PAGE_MANAGER] FATAL: care_ecc_sets must be a nonzero power of two and care_ecc_ways nonzero (got {} x {})\n",
                   care_ecc_sets, care_ecc_ways);
        std::abort();
    }
    care_cache = std::make_unique<CareEccCache>(care_ecc_sets, care_ecc_ways, care_proactive, care_proactive_or);
}

CareEccCache::ReadOutcome ErrorPageManager::care_on_read(uint64_t pa, uint32_t cpu_idx) {
    uint64_t cl_addr = get_cache_line_addr(pa);
    auto out = care_cache->on_read(cl_addr);

    if (debug == 1 && out.promoted_s3) {
        fmt::print("[CARE] S2->S3 addr=0x{:x} (hard error confirmed)\n", cl_addr);
    }

    if (out.retire) {
        uint64_t page_base = get_page_base_pa(pa);

        // Proactive victim list must be collected before any invalidation:
        // the triggering entry (and its set neighbors) are still resident here.
        std::vector<uint64_t> proactive_victims;
        if (out.proactive) {
            proactive_victims = care_cache->set_resident_pages(cl_addr);
        }

        size_t invalidated = care_cache->invalidate_page(page_base);
        retire_page(page_base, /*queue_llc_sweep=*/false);  // coverage move + counter erase; no sweep consumer under CARE
        stat_care_retirement_count++;
        per_cpu_error_stats[cpu_idx].care_retirements++;
        if (debug == 1) {
            fmt::print("[CARE] RETIRE page=0x{:x} trigger_addr=0x{:x} ecc_entries_invalidated={}\n",
                       page_base, cl_addr, invalidated);
        }

        if (out.proactive) {
            // Paper III.C: retire everything the set protects. The triggering
            // packet's single page-offline latency stands in for the batched
            // interrupt (cost under-counted; trigger count is the metric here).
            for (uint64_t victim : proactive_victims) {
                if (victim == page_base) continue;
                size_t v_inv = care_cache->invalidate_page(victim);
                retire_page(victim, /*queue_llc_sweep=*/false);
                stat_care_proactive_page_count++;
                if (debug == 1) {
                    fmt::print("[CARE] PROACTIVE RETIRE page=0x{:x} (set of 0x{:x}) ecc_entries_invalidated={}\n",
                               victim, cl_addr, v_inv);
                }
            }
            if (debug == 1) {
                fmt::print("[CARE] PROACTIVE TRIGGER trigger_addr=0x{:x} batch_pages={}\n",
                           cl_addr, proactive_victims.size());
            }
        }
    }
    return out;
}

void ErrorPageManager::care_on_write(uint64_t pa) {
    uint64_t cl_addr = get_cache_line_addr(pa);
    bool confirmed = care_cache->on_write(cl_addr);
    if (debug == 1 && confirmed) {
        fmt::print("[CARE] S1->S2 addr=0x{:x} (write confirmation)\n", cl_addr);
    }
}

void ErrorPageManager::care_on_injected_error(uint64_t pa, uint32_t cpu_idx, uint8_t bank_idx) {
    uint64_t cl_addr = get_cache_line_addr(pa);

    // Ground-truth faulty-line set for the Protection Coverage metric (D8).
    // LLC pinning consumers of error_addresses are all is_cache_pinning_enabled()-gated.
    // Note: like the baseline path, a line of an already-retired page re-enters this
    // set on re-injection while staying in retired_error_addresses — a shared
    // simulation artifact across schemes (coverage double-count, plan D5).
    error_addresses.insert(cl_addr);

    auto& s = per_cpu_error_stats[cpu_idx];
    s.errors_absorbed++;

    switch (care_cache->on_error(cl_addr, bank_idx)) {
    case CareEccCache::RegisterOutcome::REGISTERED:
        s.care_registered++;
        if (debug == 1) fmt::print("[CARE] REG addr=0x{:x} (S1)\n", cl_addr);
        if (care_demand_scrub) {
            // MC demand scrub: corrective write follows the CE-detecting read,
            // confirming S1->S2 without waiting for an application writeback.
            care_cache->on_write(cl_addr);
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
}

void ErrorPageManager::print_care_stats() const {
    if (!care_cache) {
        fmt::print("\n[CARE] ECC cache not initialized (no stats)\n");
        return;
    }
    const auto& s = care_cache->stats();
    size_t capacity = care_ecc_sets * care_ecc_ways;
    size_t resident = care_cache->occupancy();
    uint64_t error_events = s.registered + s.errors_on_tracked + s.dropped;

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
    fmt::print("[CARE]\n");
    fmt::print("[CARE] [Tracked-Block Accesses]\n");
    fmt::print("[CARE]   BCH Decode Reads (+{} cyc):     {}\n", care_bch_decode_cycles, s.decode_reads);
    fmt::print("[CARE]   S1->S2 Write Confirmations:     {}\n", s.writes_s1_to_s2);
    fmt::print("[CARE]   S2->S3 Hard Confirmations:      {}\n", s.reads_s2_to_s3);
    fmt::print("[CARE]\n");
    fmt::print("[CARE] [Retirement]\n");
    fmt::print("[CARE]   Pages Retired (reactive):       {}\n", stat_care_retirement_count);
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
            fmt::print("[ERROR]   CPU {}: care_registered={} care_dropped={} care_retired={}\n",
                       cpu_idx, s.care_registered, s.care_dropped, s.care_retirements);
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
