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
// H3 Hash Implementation
// ============================================================

void H3Hash::init(int num_k, int bloom_size, uint64_t seed) {
    k = num_k;
    output_bits = 0;
    int m = bloom_size;
    while (m > 1) { output_bits++; m >>= 1; }
    // output_bits = log2(bloom_size)

    std::mt19937_64 rng(seed);
    matrices.resize(k);
    for (int i = 0; i < k; i++) {
        matrices[i].resize(input_bits);
        for (int j = 0; j < input_bits; j++) {
            // Generate random value, mask to output_bits
            matrices[i][j] = static_cast<uint32_t>(rng() & ((1ULL << output_bits) - 1));
        }
    }
}

std::vector<int> H3Hash::hash(uint16_t cl_index) const {
    std::vector<int> results(k, 0);
    for (int i = 0; i < k; i++) {
        uint32_t h = 0;
        uint16_t val = cl_index;
        for (int j = 0; j < input_bits; j++) {
            if (val & 1) {
                h ^= matrices[i][j];
            }
            val >>= 1;
        }
        results[i] = static_cast<int>(h);
    }
    return results;
}

// ============================================================
// ETTEntry Implementation
// ============================================================

void ETTEntry::insert(uint16_t cl_index, const H3Hash& h3) {
    auto positions = h3.hash(cl_index);
    for (int pos : positions) {
        if (pos < static_cast<int>(bloom_filter.size())) {
            bloom_filter[pos] = true;
        }
    }
}

bool ETTEntry::query(uint16_t cl_index, const H3Hash& h3) const {
    auto positions = h3.hash(cl_index);
    for (int pos : positions) {
        if (pos >= static_cast<int>(bloom_filter.size()) || !bloom_filter[pos]) {
            return false;
        }
    }
    return true;
}

void ETTEntry::clear(size_t bloom_filter_size) {
    tag = 0;
    bloom_filter.assign(bloom_filter_size, false);
    lru_counter = 0;
    valid = false;
}

// ============================================================
// ErrorPageManager ETT Implementation
// ============================================================

void ErrorPageManager::init_ett() {
    // Initialize H3 hash with fixed seed for reproducibility
    h3_hash.init(static_cast<int>(bloom_filter_k), static_cast<int>(bloom_filter_size), 54321);

    // Initialize ETT entries
    ett.resize(ett_num_entries);
    for (auto& entry : ett) {
        entry.clear(bloom_filter_size);
    }

    // Initialize ECT entries (structure only)
    ect.resize(ect_num_entries);
    for (auto& entry : ect) {
        entry.tag = 0;
        entry.counter = 0;
        entry.valid = false;
    }
}

// Helper: count set bits in bloom filter
static size_t count_bloom_bits(const std::vector<bool>& bf) {
    size_t count = 0;
    for (size_t i = 0; i < bf.size(); i++) {
        if (bf[i]) count++;
    }
    return count;
}

ErrorRecordResult ErrorPageManager::record_error(uint64_t pa) {
    uint64_t page_base = get_page_base_pa(pa);
    uint16_t cl_index = extract_cache_line_index(pa);

    if (debug == 1) {
        fmt::print("[ETT] ---- record_error(pa=0x{:x}) ----\n", pa);
        fmt::print("[ETT]   page_base=0x{:x}  cl_index={}\n", page_base, cl_index);
    }

    // === Duplicate check via bloom filter ===
    int ett_idx = find_ett_entry(page_base);
    if (ett_idx >= 0 && ett[ett_idx].query(cl_index, h3_hash)) {
        stat_already_known_count++;
        if (debug == 1) {
            auto positions = h3_hash.hash(cl_index);
            fmt::print("[ETT]   ALREADY_KNOWN: bloom filter hit at ETT[{}], hash positions=[", ett_idx);
            for (size_t i = 0; i < positions.size(); i++) {
                fmt::print("{}{}", positions[i], (i + 1 < positions.size()) ? "," : "");
            }
            fmt::print("] all=1\n");
        }
        return ErrorRecordResult::ALREADY_KNOWN;
    }

    // === New error: increment counter ===
    uint8_t old_counter = page_error_counters[page_base];
    uint8_t new_count = old_counter + 1;
    page_error_counters[page_base] = new_count;

    if (debug == 1) {
        fmt::print("[ETT]   counter: {} -> {}", old_counter, new_count);
        if (new_count >= retirement_threshold) {
            fmt::print("  (>= threshold {})\n", retirement_threshold);
        } else {
            fmt::print("  (threshold={})\n", retirement_threshold);
        }
    }

    // === Retirement check ===
    if (new_count >= retirement_threshold) {
        if (debug == 1) {
            // Show bloom filter state before retirement
            if (ett_idx >= 0) {
                size_t bits_set = count_bloom_bits(ett[ett_idx].bloom_filter);
                fmt::print("[ETT]   ETT[{}] bloom filter before retire: {}/{} bits set ({:.1f}%)\n",
                           ett_idx, bits_set, bloom_filter_size,
                           100.0 * bits_set / bloom_filter_size);
            }
        }
        retire_page(page_base, ett_idx);
        stat_retirement_count++;
        if (debug == 1) {
            fmt::print("[ETT]   => PAGE_RETIRED\n");
        }
        return ErrorRecordResult::PAGE_RETIRED;
    }

    // === Insert into ETT bloom filter ===
    bool new_ett_entry = false;
    if (ett_idx < 0) {
        ett_idx = allocate_ett_entry(page_base);
        new_ett_entry = true;
    }

    // Get hash positions for debug
    auto positions = h3_hash.hash(cl_index);

    if (ett_idx >= 0) {
        if (debug == 1) {
            if (new_ett_entry) {
                fmt::print("[ETT]   ETT entry ALLOCATED: ETT[{}] for page 0x{:x}\n", ett_idx, page_base);
            } else {
                fmt::print("[ETT]   ETT entry EXISTS: ETT[{}]\n", ett_idx);
            }
            // Show which bloom filter bits will be set
            fmt::print("[ETT]   H3 hash(cl_index={}) -> positions=[", cl_index);
            for (size_t i = 0; i < positions.size(); i++) {
                fmt::print("{}{}", positions[i], (i + 1 < positions.size()) ? "," : "");
            }
            fmt::print("]\n");
            // Show before state of those bits
            fmt::print("[ETT]   bloom bits before: [");
            for (size_t i = 0; i < positions.size(); i++) {
                int pos = positions[i];
                fmt::print("bit[{}]={}{}", pos,
                           (pos < static_cast<int>(ett[ett_idx].bloom_filter.size()) && ett[ett_idx].bloom_filter[pos]) ? 1 : 0,
                           (i + 1 < positions.size()) ? ", " : "");
            }
            fmt::print("]\n");
        }

        ett[ett_idx].insert(cl_index, h3_hash);
        ett[ett_idx].lru_counter = ++ett_lru_counter;

        if (debug == 1) {
            size_t bits_set = count_bloom_bits(ett[ett_idx].bloom_filter);
            fmt::print("[ETT]   bloom bits after insert: {}/{} bits set ({:.1f}%)\n",
                       bits_set, bloom_filter_size,
                       100.0 * bits_set / bloom_filter_size);
        }
    }

    if (new_count == 1) {
        stat_first_error_count++;
        if (debug == 1) {
            fmt::print("[ETT]   => FIRST_ERROR\n");
        }
        return ErrorRecordResult::FIRST_ERROR;
    } else {
        stat_added_error_count++;
        if (debug == 1) {
            fmt::print("[ETT]   => ADDED_ERROR (count={})\n", new_count);
        }
        return ErrorRecordResult::ADDED_ERROR;
    }
}

bool ErrorPageManager::is_error_position(uint64_t pa) const {
    uint64_t page_base = get_page_base_pa(pa);

    // Fast path: no errors on this page
    auto it = page_error_counters.find(page_base);
    if (it == page_error_counters.end() || it->second == 0) {
        return false;
    }

    // Query ETT bloom filter
    uint16_t cl_index = extract_cache_line_index(pa);
    return ett_query(page_base, cl_index);
}

bool ErrorPageManager::ett_query(uint64_t page_base, uint16_t cl_index) const {
    int ett_idx = find_ett_entry(page_base);
    if (ett_idx < 0) {
        return false;
    }
    return ett[ett_idx].query(cl_index, h3_hash);
}

int ErrorPageManager::find_ett_entry(uint64_t page_base_pa) const {
    for (size_t i = 0; i < ett_num_entries; i++) {
        if (ett[i].valid && ett[i].tag == page_base_pa) {
            return static_cast<int>(i);
        }
    }
    return -1;
}

int ErrorPageManager::allocate_ett_entry(uint64_t page_base_pa) {
    // First, try to find an invalid (empty) entry
    for (size_t i = 0; i < ett_num_entries; i++) {
        if (!ett[i].valid) {
            ett[i].valid = true;
            ett[i].tag = page_base_pa;
            ett[i].bloom_filter.assign(bloom_filter_size, false);
            ett[i].lru_counter = ++ett_lru_counter;
            return static_cast<int>(i);
        }
    }

    // All entries full - evict LRU
    int victim_idx = evict_ett_lru();
    if (victim_idx >= 0) {
        if (debug == 1) {
            fmt::print("[ETT] EVICT: entry={} page=0x{:x}\n",
                       victim_idx, ett[victim_idx].tag);
        }

        stat_ett_eviction_count++;

        // Re-initialize the entry
        ett[victim_idx].valid = true;
        ett[victim_idx].tag = page_base_pa;
        ett[victim_idx].bloom_filter.assign(bloom_filter_size, false);
        ett[victim_idx].lru_counter = ++ett_lru_counter;
    }
    return victim_idx;
}

int ErrorPageManager::evict_ett_lru() {
    int victim = -1;
    uint64_t min_lru = UINT64_MAX;
    for (size_t i = 0; i < ett_num_entries; i++) {
        if (ett[i].valid && ett[i].lru_counter < min_lru) {
            min_lru = ett[i].lru_counter;
            victim = static_cast<int>(i);
        }
    }
    return victim;
}

void ErrorPageManager::retire_page(uint64_t page_base, int ett_idx) {
    // Page retirement = new page allocation emulation
    // Clean up all tracking so the page starts fresh

    if (debug == 1) {
        fmt::print("[ETT]   RETIRE page=0x{:x}:\n", page_base);
    }

    // 1. Remove page error counter
    page_error_counters.erase(page_base);
    if (debug == 1) {
        fmt::print("[ETT]     1. page_error_counters: erased\n");
    }

    // 2. Invalidate ETT entry
    if (ett_idx >= 0 && static_cast<size_t>(ett_idx) < ett_num_entries && ett[ett_idx].valid) {
        if (debug == 1) {
            size_t bits_set = count_bloom_bits(ett[ett_idx].bloom_filter);
            fmt::print("[ETT]     2. ETT[{}]: cleared (had {}/{} bloom bits set)\n",
                       ett_idx, bits_set, bloom_filter_size);
        }
        ett[ett_idx].clear(bloom_filter_size);
    } else {
        if (debug == 1) {
            fmt::print("[ETT]     2. ETT entry: not found (idx={})\n", ett_idx);
        }
    }

    // 3. Queue page for LLC error way sweep
    pending_retirement_pages.push_back(page_base);
    if (debug == 1) {
        fmt::print("[ETT]     3. pending_retirement_pages: queued (total pending={})\n",
                   pending_retirement_pages.size());
    }
}

size_t ErrorPageManager::get_ett_used_entries() const {
    size_t count = 0;
    for (size_t i = 0; i < ett_num_entries; i++) {
        if (ett[i].valid) count++;
    }
    return count;
}

void ErrorPageManager::print_ett_stats() const {
    uint64_t total_new_recordings = stat_first_error_count + stat_added_error_count;
    uint64_t total_dram_error_events = total_new_recordings + stat_retirement_count + stat_already_known_count;

    // Count multi-error pages from page_error_counters
    uint64_t multi_error_page_count = 0;
    for (const auto& [page, cnt] : page_error_counters) {
        if (cnt >= 2) multi_error_page_count++;
    }
    uint64_t active_single_error_pages = page_error_counters.size() - multi_error_page_count;

    fmt::print("\n[ETT] ========== Error Tracking Table Statistics ==========\n");

    fmt::print("[ETT]\n");
    fmt::print("[ETT] [Configuration]\n");
    fmt::print("[ETT]   ETT Entries:                    {}\n", ett_num_entries);
    fmt::print("[ETT]   Bloom Filter Size (m):          {} bits\n", bloom_filter_size);
    fmt::print("[ETT]   Hash Functions (k):             {}\n", bloom_filter_k);
    fmt::print("[ETT]   Retirement Threshold:           {}\n", retirement_threshold);

    fmt::print("[ETT]\n");
    fmt::print("[ETT] [DRAM Error Events]\n");
    fmt::print("[ETT]   Total DRAM Error Events:        {}\n", total_dram_error_events);
    fmt::print("[ETT]     New Error Recordings:         {}\n", total_new_recordings);
    fmt::print("[ETT]       First Error (per page):     {}\n", stat_first_error_count);
    fmt::print("[ETT]       Additional Errors:          {}\n", stat_added_error_count);
    fmt::print("[ETT]     Page Retirements ({}th err): {}\n", retirement_threshold, stat_retirement_count);
    fmt::print("[ETT]     Already Known (bloom hit):    {}\n", stat_already_known_count);

    fmt::print("[ETT]\n");
    fmt::print("[ETT] [Page Status]  (after retirement, page resets to clean)\n");
    fmt::print("[ETT]   Active Pages (tracked):         {}\n", page_error_counters.size());
    fmt::print("[ETT]     Single-error pages:           {}\n", active_single_error_pages);
    fmt::print("[ETT]     Multi-error pages:            {}\n", multi_error_page_count);

    fmt::print("[ETT]\n");
    fmt::print("[ETT] [ETT Table Usage]\n");
    fmt::print("[ETT]   ETT Entries Used:               {} / {}\n", get_ett_used_entries(), ett_num_entries);
    fmt::print("[ETT]   ETT Evictions:                  {}\n", stat_ett_eviction_count);

    fmt::print("[ETT] ============================================================\n");
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
