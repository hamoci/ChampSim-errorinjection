#include "error_page_manager.h"
#include "champsim.h"
#include "dram_controller.h"
#include <fmt/core.h>
#include <random>
#include <algorithm>

// Static member initialization
std::unique_ptr<ErrorPageManager> ErrorPageManager::instance = nullptr;

// ============================================================
// Dual-Layer Error Recording (EPT) Implementation
// ============================================================

ErrorRecordResult ErrorPageManager::record_error(uint64_t pa) {
    uint64_t page_base = get_page_base_pa(pa);
    uint16_t cl_index = extract_cache_line_index(pa);

    // Build the full 64B-aligned address for error_addresses set (shifted by 6)
    uint64_t aligned_addr_shifted = pa >> 6;

    // Check if this exact position is already known
    auto inline_it = inline_descriptors.find(page_base);
    if (inline_it != inline_descriptors.end()) {
        // Page has at least one error - check if this position is already tracked
        if (inline_it->second == cl_index) {
            stat_already_known_count++;
            return ErrorRecordResult::ALREADY_KNOWN;
        }
        // Check EPT for this position
        if (multi_error_pages.find(page_base) != multi_error_pages.end()) {
            int ept_idx = find_ept_entry(page_base);
            if (ept_idx >= 0) {
                for (uint8_t s = 0; s < ept[ept_idx].slot_count; s++) {
                    if (ept[ept_idx].slots[s] == cl_index) {
                        // Update LRU
                        ept[ept_idx].lru_counter = ++ept_lru_counter;
                        stat_already_known_count++;
                        return ErrorRecordResult::ALREADY_KNOWN;
                    }
                }
            }
        }
    }

    // === Case 1: First error on this page ===
    if (inline_it == inline_descriptors.end()) {
        inline_descriptors[page_base] = cl_index;
        error_addresses.insert(aligned_addr_shifted);
        stat_case1_count++;
        if (debug == 1) {
            fmt::print("[EPT] Case1 FIRST_ERROR: page=0x{:x} cl_index={} pa=0x{:x}\n",
                       page_base, cl_index, pa);
        }
        return ErrorRecordResult::FIRST_ERROR;
    }

    // === Case 2: Second error (inline exists, multi not set) ===
    if (multi_error_pages.find(page_base) == multi_error_pages.end()) {
        multi_error_pages.insert(page_base);
        int ept_idx = allocate_ept_entry(page_base);
        if (ept_idx >= 0) {
            ept[ept_idx].slots[0] = cl_index;
            ept[ept_idx].slot_count = 1;
            ept[ept_idx].lru_counter = ++ept_lru_counter;
        }
        error_addresses.insert(aligned_addr_shifted);
        stat_case2_count++;
        if (debug == 1) {
            fmt::print("[EPT] Case2 SECOND_ERROR: page=0x{:x} cl_index={} ept_idx={} pa=0x{:x}\n",
                       page_base, cl_index, ept_idx, pa);
        }
        return ErrorRecordResult::ADDED_ERROR;
    }

    // === Case 3: Third or more error (multi already set) ===
    int ept_idx = find_ept_entry(page_base);

    // EPT entry exists for this page
    if (ept_idx >= 0) {
        if (ept[ept_idx].slot_count < EPT_SLOTS_PER_ENTRY) {
            // Still have room in EPT
            ept[ept_idx].slots[ept[ept_idx].slot_count] = cl_index;
            ept[ept_idx].slot_count++;
            ept[ept_idx].lru_counter = ++ept_lru_counter;
            error_addresses.insert(aligned_addr_shifted);
            stat_case3_count++;
            if (debug == 1) {
                fmt::print("[EPT] Case3 ADDED_ERROR: page=0x{:x} cl_index={} slot={} pa=0x{:x}\n",
                           page_base, cl_index, ept[ept_idx].slot_count - 1, pa);
            }
            return ErrorRecordResult::ADDED_ERROR;
        } else {
            // EPT full for this page (4 slots used + 1 inline = 5 total)
            // 6th error → page retirement: clean up all tracking and unpin
            retire_page(page_base, ept_idx);
            stat_retirement_count++;
            if (debug == 1) {
                fmt::print("[EPT] PAGE_RETIRED: page=0x{:x} cl_index={} (6th error) pa=0x{:x}\n",
                           page_base, cl_index, pa);
            }
            return ErrorRecordResult::PAGE_RETIRED;
        }
    }

    // EPT entry was evicted for this page (multi is set but no EPT entry)
    // Need to re-allocate EPT entry
    ept_idx = allocate_ept_entry(page_base);
    if (ept_idx >= 0) {
        ept[ept_idx].slots[0] = cl_index;
        ept[ept_idx].slot_count = 1;
        ept[ept_idx].lru_counter = ++ept_lru_counter;
    }
    error_addresses.insert(aligned_addr_shifted);
    stat_case3_count++;
    if (debug == 1) {
        fmt::print("[EPT] Case3 RE-ALLOC: page=0x{:x} cl_index={} ept_idx={} pa=0x{:x}\n",
                   page_base, cl_index, ept_idx, pa);
    }
    return ErrorRecordResult::ADDED_ERROR;
}

bool ErrorPageManager::is_error_position(uint64_t pa) const {
    uint64_t aligned_addr_shifted = pa >> 6;
    return error_addresses.find(aligned_addr_shifted) != error_addresses.end();
}

std::vector<uint64_t> ErrorPageManager::get_ept_eviction_victims(size_t ept_index) const {
    std::vector<uint64_t> victims;
    if (ept_index >= EPT_NUM_ENTRIES || !ept[ept_index].valid) {
        return victims;
    }
    const auto& entry = ept[ept_index];
    for (uint8_t s = 0; s < entry.slot_count; s++) {
        // Reconstruct full PA from page base + cache line index
        uint64_t full_pa = entry.tag | (static_cast<uint64_t>(entry.slots[s]) << 6);
        // Return the shifted address (matching error_addresses format)
        victims.push_back(full_pa >> 6);
    }
    return victims;
}

int ErrorPageManager::find_ept_entry(uint64_t page_base_pa) const {
    for (size_t i = 0; i < EPT_NUM_ENTRIES; i++) {
        if (ept[i].valid && ept[i].tag == page_base_pa) {
            return static_cast<int>(i);
        }
    }
    return -1;
}

int ErrorPageManager::allocate_ept_entry(uint64_t page_base_pa) {
    // First, try to find an invalid (empty) entry
    for (size_t i = 0; i < EPT_NUM_ENTRIES; i++) {
        if (!ept[i].valid) {
            ept[i].valid = true;
            ept[i].tag = page_base_pa;
            ept[i].slot_count = 0;
            ept[i].lru_counter = ++ept_lru_counter;
            return static_cast<int>(i);
        }
    }

    // All entries full - evict LRU
    int victim_idx = evict_ept_lru();
    if (victim_idx >= 0) {
        // Before eviction: remove the EPT-tracked error positions from error_addresses
        auto victims = get_ept_eviction_victims(static_cast<size_t>(victim_idx));
        for (auto addr_shifted : victims) {
            error_addresses.erase(addr_shifted);
        }

        if (debug == 1) {
            fmt::print("[EPT] EVICT: entry={} page=0x{:x} slots_removed={}\n",
                       victim_idx, ept[victim_idx].tag, ept[victim_idx].slot_count);
        }

        stat_ept_eviction_count++;

        // Re-initialize the entry
        ept[victim_idx].valid = true;
        ept[victim_idx].tag = page_base_pa;
        ept[victim_idx].slot_count = 0;
        ept[victim_idx].lru_counter = ++ept_lru_counter;
    }
    return victim_idx;
}

int ErrorPageManager::evict_ept_lru() {
    int victim = -1;
    uint64_t min_lru = UINT64_MAX;
    for (size_t i = 0; i < EPT_NUM_ENTRIES; i++) {
        if (ept[i].valid && ept[i].lru_counter < min_lru) {
            min_lru = ept[i].lru_counter;
            victim = static_cast<int>(i);
        }
    }
    return victim;
}

void ErrorPageManager::retire_page(uint64_t page_base, int ept_idx) {
    // Page retirement = new page allocation emulation
    // Clean up all tracking so the page starts fresh (as if a new physical page)
    // retirement_count is tracked by the caller for statistics

    // 1. Remove inline descriptor's error address from error_addresses
    auto inline_it = inline_descriptors.find(page_base);
    if (inline_it != inline_descriptors.end()) {
        uint64_t inline_pa = page_base | (static_cast<uint64_t>(inline_it->second) << 6);
        error_addresses.erase(inline_pa >> 6);
        inline_descriptors.erase(inline_it);
    }

    // 3. Remove EPT entry's error addresses from error_addresses
    if (ept_idx >= 0 && ept[ept_idx].valid) {
        for (uint8_t s = 0; s < ept[ept_idx].slot_count; s++) {
            uint64_t slot_pa = page_base | (static_cast<uint64_t>(ept[ept_idx].slots[s]) << 6);
            error_addresses.erase(slot_pa >> 6);
        }
        ept[ept_idx].valid = false;
    }

    // 4. Remove from multi_error_pages
    multi_error_pages.erase(page_base);

    if (debug == 1) {
        fmt::print("[EPT] RETIRE_CLEANUP: page=0x{:x} removed from inline/EPT/error_addresses\n", page_base);
    }
}

size_t ErrorPageManager::get_ept_used_entries() const {
    size_t count = 0;
    for (size_t i = 0; i < EPT_NUM_ENTRIES; i++) {
        if (ept[i].valid) count++;
    }
    return count;
}

void ErrorPageManager::print_ept_stats() const {
    uint64_t total_new_recordings = stat_case1_count + stat_case2_count + stat_case3_count;
    uint64_t total_dram_error_events = total_new_recordings + stat_retirement_count + stat_already_known_count;
    uint64_t active_single_error_pages = inline_descriptors.size() - multi_error_pages.size();

    fmt::print("\n[EPT] ========== Error Position Table Statistics ==========\n");

    fmt::print("[EPT]\n");
    fmt::print("[EPT] [DRAM Error Events]\n");
    fmt::print("[EPT]   Total DRAM Error Events:       {}\n", total_dram_error_events);
    fmt::print("[EPT]     New Error Recordings:        {}\n", total_new_recordings);
    fmt::print("[EPT]       Case 1 (1st error/page):   {}\n", stat_case1_count);
    fmt::print("[EPT]       Case 2 (2nd error/page):   {}\n", stat_case2_count);
    fmt::print("[EPT]       Case 3 (3rd~5th err/page): {}\n", stat_case3_count);
    fmt::print("[EPT]     Page Retirements (6th err):  {}\n", stat_retirement_count);
    fmt::print("[EPT]     Already Known (duplicate):   {}\n", stat_already_known_count);

    fmt::print("[EPT]\n");
    fmt::print("[EPT] [Page Status]  (after retirement, page resets to clean)\n");
    fmt::print("[EPT]   Active Pages (pinned):         {}\n", inline_descriptors.size());
    fmt::print("[EPT]     Single-error pages:          {}\n", active_single_error_pages);
    fmt::print("[EPT]     Multi-error pages:           {}\n", multi_error_pages.size());

    fmt::print("[EPT]\n");
    fmt::print("[EPT] [EPT Table Usage]\n");
    fmt::print("[EPT]   EPT Entries Used:              {} / {}\n", get_ept_used_entries(), EPT_NUM_ENTRIES);
    fmt::print("[EPT]   EPT Evictions:                 {}\n", stat_ept_eviction_count);

    fmt::print("[EPT]\n");
    fmt::print("[EPT] [LLC Pinning]\n");
    fmt::print("[EPT]   Currently Pinned Positions:    {}\n", error_addresses.size());

    fmt::print("[EPT] ======================================================\n");
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
