/*
 * Error Page Manager for ChampSim
 * Manages error pages that require additional latency when accessed
 *
 * ETT (Error Tracking Table) with Bloom Filter:
 *   - Page Error Counter: page_base → error count (up to retirement_threshold)
 *   - ETT Entry: tag + bloom filter (m bits, H3 hash) per 2MB page
 *   - Page Retirement: retirement_threshold-th error → page offline emulation
 *
 * ECT (Error Counter Table): structure only, for paper completeness
 */

#ifndef ERROR_PAGE_MANAGER_H
#define ERROR_PAGE_MANAGER_H

#include <unordered_set>
#include <unordered_map>
#include <array>
#include <vector>
#include <random>
#include <memory>
#include <algorithm>
#include <cstdint>
#include "address.h"
#include "chrono.h"
#include "champsim.h"

enum class ErrorPageManagerMode {
    ALL_ON,
    RANDOM,
    CYCLE,
    OFF,
};

// record_error() return values
enum class ErrorRecordResult {
    FIRST_ERROR,      // first error on this page
    ADDED_ERROR,      // additional error recorded
    ALREADY_KNOWN,    // already registered error position (bloom filter hit)
    PAGE_RETIRED,     // retirement threshold reached
};

// H3 Hash for bloom filter indexing
// Uses random bit matrices for independent hash functions
struct H3Hash {
    int k{4};             // number of hash functions
    int input_bits{15};   // cl_index is 15 bits
    int output_bits{8};   // log2(bloom_filter_size)
    // matrices[i][j] = random value for hash function i, input bit j
    // Each hash output = XOR of matrices[i][j] for all set bits j in input
    std::vector<std::vector<uint32_t>> matrices;  // [k][input_bits]

    void init(int num_k, int bloom_size, uint64_t seed);
    std::vector<int> hash(uint16_t cl_index) const;
};

// ETT Entry: one per 2MB page, holds bloom filter for error positions
struct ETTEntry {
    uint64_t tag{0};              // page base PA (2MB aligned)
    std::vector<bool> bloom_filter; // m bits (configurable: 128/256/512)
    uint64_t lru_counter{0};
    bool valid{false};

    void insert(uint16_t cl_index, const H3Hash& h3);
    bool query(uint16_t cl_index, const H3Hash& h3) const;
    void clear(size_t bloom_filter_size);
};

// ECT Entry: structure only (paper completeness)
struct ECTEntry {
    uint64_t tag{0};       // page base PA
    uint8_t counter{0};    // CE count
    bool valid{false};
};

class ErrorPageManager {
// Global Private Variables
private:
    std::unordered_set<uint64_t> error_pages;  // Page 단위 error (기존 호환용)
    std::unordered_set<uint64_t> current_ppage;
    ErrorPageManagerMode mode;
    champsim::chrono::clock::duration error_latency_penalty{};
    champsim::chrono::clock::duration pte_error_latency_penalty{};
    static std::unique_ptr<ErrorPageManager> instance;

// ETT (Error Tracking Table) with Bloom Filter
private:
    // Page error counters: page_base → error count
    std::unordered_map<uint64_t, uint32_t> page_error_counters;
    // ETT: configurable entries with bloom filters
    size_t ett_num_entries{64};
    size_t bloom_filter_size{256};  // m bits
    size_t bloom_filter_k{4};      // number of hash functions
    size_t retirement_threshold{32};
    std::vector<ETTEntry> ett;
    uint64_t ett_lru_counter{0};
    H3Hash h3_hash;

    // Pending LLC page retirements (page_base values)
    std::vector<uint64_t> pending_retirement_pages;

// ECT (Error Counter Table) — structure only, paper completeness
private:
    std::vector<ECTEntry> ect;  // 1024 entries default
    size_t ect_num_entries{1024};

// ETT Statistics
private:
    uint64_t stat_first_error_count{0};    // first error recordings
    uint64_t stat_added_error_count{0};    // additional error recordings
    uint64_t stat_retirement_count{0};     // pages retired
    uint64_t stat_ett_eviction_count{0};   // ETT entry evictions
    uint64_t stat_already_known_count{0};  // duplicate error accesses (bloom filter hit)

    // Bloom filter occupancy tracking (cumulative)
    uint64_t stat_bloom_bits_set_sum{0};   // sum of bits_set at each insert
    uint64_t stat_bloom_insert_count{0};   // number of inserts

    // Retirement detail
    uint64_t stat_retirement_invalidated_lines{0};  // total cache lines invalidated by retirement sweeps

//For Random Error Injection
private:
    std::mt19937 gen{54321};
    std::uniform_real_distribution<double> prob_dist{0.0, 1.0};
    std::exponential_distribution<double> exp_dist{1.0};  // For exponential interval
    uint32_t errors_per_interval{1};

// Monte Carlo Simulation Results
private:
    double bit_error_rate{0.0};
    double page_error_rate{0.0};
    uint64_t page_size_bits{0};

// Cycle-based Error Injection
private:
    uint64_t error_cycle_interval{0};
    champsim::chrono::picoseconds cpu_clock_period{};
    uint64_t last_error_cycle{0};  // Track the last cycle when error was triggered
    uint64_t pending_error_count{0};  // Counter for pending errors
    int debug{1};  // Debug flag: 1 to enable debug logs, 0 to disable

// Cache Pinning (Error Way Partitioning)
private:
    bool cache_pinning_enabled{false};  // Enable/disable cache pinning feature
    bool dynamic_error_latency_enabled{true};  // true: emulate PTW(PSC+cache), false: fixed error_latency_penalty
    uint32_t max_error_ways_per_set{8};  // Maximum number of pinned/error ways per LLC set

// Baseline Page Retirement (no pinning)
private:
    size_t baseline_retirement_threshold{6};  // retire (reset) page after this many errors
    std::unordered_map<uint64_t, uint32_t> baseline_page_error_counts;  // page_base → error count
    uint64_t stat_baseline_retirement_count{0};

// Error Statistics
private:
    uint64_t total_error_count{0};

public:
    // Singleton pattern
    static ErrorPageManager& get_instance() {
        if (!instance) {
            instance = std::make_unique<ErrorPageManager>();
            instance->init_ett();
        }
        return *instance;
    }

    void set_mode(ErrorPageManagerMode new_mode) { mode = new_mode; }

    ErrorPageManagerMode get_mode() const {
        return mode;
    }

    // Error page management (기존 방식 - 호환용)
    void add_error_page(champsim::page_number page) { error_pages.insert(page.to<uint64_t>()); }
    void remove_error_page(champsim::page_number page) { error_pages.erase(page.to<uint64_t>()); }
    bool is_error_page(champsim::page_number page) const { return error_pages.find(page.to<uint64_t>()) != error_pages.end(); }

    // ============================================================
    // ETT (Error Tracking Table) API
    // ============================================================

    // Record a new error at physical address (64B aligned).
    // Returns the result indicating which case was triggered.
    ErrorRecordResult record_error(uint64_t pa);

    // Check if the given physical address is an error position via bloom filter
    bool is_error_position(uint64_t pa) const;

    // Query ETT bloom filter: page_base + cl_index
    bool ett_query(uint64_t page_base, uint16_t cl_index) const;

    // Get page error counter (0 if not tracked)
    uint32_t get_page_error_counter(uint64_t page_base) const {
        auto it = page_error_counters.find(page_base);
        return (it != page_error_counters.end()) ? it->second : 0;
    }

    // Drain pending LLC page retirements (called from LLC operate())
    std::vector<uint64_t> drain_pending_retirements() {
        std::vector<uint64_t> result;
        result.swap(pending_retirement_pages);
        return result;
    }
    bool has_pending_retirements() const { return !pending_retirement_pages.empty(); }

    // Get number of tracked error pages
    size_t get_error_page_counter_count() const { return page_error_counters.size(); }
    void clear_all_ett() {
        page_error_counters.clear();
        for (auto& e : ett) e.valid = false;
    }

    // ETT configuration setters (must be called before simulation starts)
    void set_ett_num_entries(size_t entries) {
        ett_num_entries = entries;
        init_ett();
    }
    void set_bloom_filter_size(size_t size) {
        bloom_filter_size = size;
        init_ett();
    }
    void set_bloom_filter_k(size_t k) {
        bloom_filter_k = k;
        init_ett();
    }
    void set_retirement_threshold(size_t threshold) { retirement_threshold = threshold; }
    size_t get_ett_num_entries() const { return ett_num_entries; }
    size_t get_bloom_filter_size() const { return bloom_filter_size; }
    size_t get_bloom_filter_k() const { return bloom_filter_k; }
    size_t get_retirement_threshold() const { return retirement_threshold; }

    // ETT statistics
    uint64_t get_stat_first_error_count() const { return stat_first_error_count; }
    uint64_t get_stat_added_error_count() const { return stat_added_error_count; }
    uint64_t get_stat_retirement_count() const { return stat_retirement_count; }
    uint64_t get_stat_ett_eviction_count() const { return stat_ett_eviction_count; }
    uint64_t get_stat_already_known_count() const { return stat_already_known_count; }
    void add_retirement_invalidated_lines(uint64_t count) { stat_retirement_invalidated_lines += count; }
    size_t get_ett_used_entries() const;
    void print_ett_stats() const;

    // ============================================================
    // Existing API (unchanged)
    // ============================================================

    // Monte Carlo Simulation for page error rate
    void init_page_error_rate(double bit_error_rate);

    // Latency management
    void set_error_latency(champsim::chrono::clock::duration latency) { error_latency_penalty = latency; }
    champsim::chrono::clock::duration get_error_latency() const { return error_latency_penalty; }
    void set_pte_error_latency(champsim::chrono::clock::duration latency) { pte_error_latency_penalty = latency; }
    champsim::chrono::clock::duration get_pte_error_latency() const { return pte_error_latency_penalty; }

    // Random error injection settings
    void set_errors_per_interval(uint32_t count) { errors_per_interval = count; }
    uint32_t get_errors_per_interval() const { return errors_per_interval; }

    // Monte Carlo simulation results
    void set_bit_error_rate(double ber) { bit_error_rate = ber; }
    double get_bit_error_rate() const { return bit_error_rate; }
    double get_page_error_rate() const { return page_error_rate; }
    uint64_t get_page_size_bits() const { return page_size_bits; }

    // Check if error occurs for current DRAM access based on Page Error Rate
    bool check_page_error() { return prob_dist(gen) < page_error_rate; }

    // Cycle-based error injection setters/getters
    void set_error_cycle_interval(uint64_t interval) {
        error_cycle_interval = interval;
        // Initialize exponential distribution with rate = 1/mean_interval
        if (interval > 0) {
            exp_dist = std::exponential_distribution<double>(1.0 / static_cast<double>(interval));
            // Initialize first error cycle with exponential sample
            last_error_cycle = static_cast<uint64_t>(exp_dist(gen));
        }
    }
    uint64_t get_error_cycle_interval() const { return error_cycle_interval; }
    void set_cpu_clock_period(champsim::chrono::picoseconds period) { cpu_clock_period = period; }
    champsim::chrono::picoseconds get_cpu_clock_period() const { return cpu_clock_period; }

    // Debug mode setter/getter
    void set_debug(int debug_mode) { debug = debug_mode; }
    int get_debug() const { return debug; }

    // Cache Pinning setter/getter
    void set_cache_pinning_enabled(bool enabled) { cache_pinning_enabled = enabled; }
    bool is_cache_pinning_enabled() const { return cache_pinning_enabled; }

    // Dynamic/Fixed error latency mode setter/getter
    void set_dynamic_error_latency_enabled(bool enabled) { dynamic_error_latency_enabled = enabled; }
    bool is_dynamic_error_latency_enabled() const { return dynamic_error_latency_enabled; }

    // Cache pinning capacity setter/getter
    void set_max_error_ways_per_set(uint32_t ways) { max_error_ways_per_set = std::max<uint32_t>(1, ways); }
    uint32_t get_max_error_ways_per_set() const { return max_error_ways_per_set; }

    // Baseline retirement threshold setter/getter
    void set_baseline_retirement_threshold(size_t threshold) { baseline_retirement_threshold = threshold; }
    size_t get_baseline_retirement_threshold() const { return baseline_retirement_threshold; }

    // Baseline page retirement: returns true if this error triggers retirement
    bool record_baseline_error(uint64_t pa) {
        uint64_t page_base = get_page_base_pa(pa);
        auto& count = baseline_page_error_counts[page_base];
        count++;
        if (count >= baseline_retirement_threshold) {
            count = 0;  // reset — emulate new page allocation
            stat_baseline_retirement_count++;
            if (debug == 1) {
                fmt::print("[BASELINE_RETIRE] page=0x{:x} retired (threshold={}) pa=0x{:x}\n",
                           page_base, baseline_retirement_threshold, pa);
            }
            return true;
        }
        return false;
    }
    uint64_t get_stat_baseline_retirement_count() const { return stat_baseline_retirement_count; }

    // Update cycle error counter (called from operate() every cycle)
    void update_cycle_errors(champsim::chrono::clock::time_point current_time) {
        if (error_cycle_interval == 0 || cpu_clock_period.count() == 0) {
            return;
        }

        uint64_t current_cycle = current_time.time_since_epoch().count() / cpu_clock_period.count();

        // last_error_cycle is now used as "next_error_cycle"
        // If current cycle reaches the next scheduled error cycle, trigger error
        if (current_cycle >= last_error_cycle) {
            pending_error_count++;

            // Sample next interval from exponential distribution
            double next_interval = exp_dist(gen);
            last_error_cycle = current_cycle + static_cast<uint64_t>(next_interval);

            // Debug output - only show when debug=1
            if (debug == 1) {
                fmt::print("[ERROR_CYCLE] Error added at CPU cycle {}, next at {}, pending count: {}\n",
                           current_cycle, last_error_cycle, pending_error_count);
            }
        }
    }

    // Consume one error from the counter (called from service_packet)
    bool consume_cycle_error() {
        if (pending_error_count > 0) {
            pending_error_count--;
            return true;
        }
        return false;
    }

    // Extract page number from physical address
    static champsim::page_number get_page_number(champsim::address addr) {
        return champsim::page_number{addr};
    }

    // Physical Page Management
    void add_current_ppage(champsim::page_number page) { current_ppage.insert(page.to<uint64_t>()); }
    void remove_current_ppage(champsim::page_number page) { current_ppage.erase(page.to<uint64_t>()); }
    bool is_current_ppage(champsim::page_number page) const { return current_ppage.find(page.to<uint64_t>()) != current_ppage.end(); }

    // Utility functions
    size_t get_error_page_count() const { return error_pages.size(); }
    size_t get_current_ppage_count() const { return current_ppage.size(); }
    void clear_all_error_pages() { error_pages.clear(); }
    void clear_current_ppage() { current_ppage.clear(); }

    // Inject Error at All Pages
    void all_error_pages_on(uint64_t page_num);

    // Error Statistics
    void record_error_access(void) {
        total_error_count++;
    }
    uint64_t get_total_error_count() const { return total_error_count; }
    void reset_error_stats() {
        total_error_count = 0;
    }

    // For debugging
    void print_error_pages() const;

private:
    // Initialize ETT and H3 hash
    void init_ett();

    // Internal ETT helpers
    int find_ett_entry(uint64_t page_base_pa) const;
    int allocate_ett_entry(uint64_t page_base_pa);
    int evict_ett_lru();
    void retire_page(uint64_t page_base, int ett_idx);
    static uint16_t extract_cache_line_index(uint64_t pa) {
        // PA[20:6] → 15-bit cache line index within a 2MB page
        return static_cast<uint16_t>((pa >> 6) & 0x7FFF);
    }
    static uint64_t get_page_base_pa(uint64_t pa) {
        // 2MB aligned: clear lower 21 bits
        return pa & ~((1ULL << 21) - 1);
    }
};

#endif // ERROR_PAGE_MANAGER_H
