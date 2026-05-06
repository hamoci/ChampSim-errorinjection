#include "error_page_manager.h"
#include "champsim.h"
#include "dram_controller.h"
#include <fmt/core.h>
#include <random>
#include <algorithm>
#include <cmath>

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

void ErrorPageManager::retire_page(uint64_t page_base) {
    if (debug == 1) {
        fmt::print("[ERROR_REC]   RETIRE page=0x{:x}:\n", page_base);
    }

    // 1. Remove page error counter
    page_error_counters.erase(page_base);
    if (debug == 1) {
        fmt::print("[ERROR_REC]     1. page_error_counters: erased\n");
    }

    // 2. Remove error addresses belonging to this page
    uint64_t page_mask = ~((1ULL << 21) - 1);
    size_t removed = 0;
    for (auto it = error_addresses.begin(); it != error_addresses.end(); ) {
        if ((*it & page_mask) == page_base) {
            it = error_addresses.erase(it);
            removed++;
        } else {
            ++it;
        }
    }
    if (debug == 1) {
        fmt::print("[ERROR_REC]     2. error_addresses: removed {} entries\n", removed);
    }

    // 3. Queue page for LLC error way sweep
    pending_retirement_pages.push_back(page_base);
    if (debug == 1) {
        fmt::print("[ERROR_REC]     3. pending_retirement_pages: queued (total pending={})\n",
                   pending_retirement_pages.size());
    }
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

    fmt::print("[ERROR] ============================================================\n");
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
