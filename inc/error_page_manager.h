/*
 * Error Page Manager for ChampSim
 * Manages error pages that require additional latency when accessed
 *
 * Dual-Layer Error Recording:
 *   - Inline Error Descriptor: PDE unused bit (1 multi + 15 position) → first error per page
 *   - Error Position Table (EPT): LLC controller internal, 64 entries, 4 slots each → 2nd~5th errors
 *   - Page Retirement: 6th+ error → large latency penalty (bad page offlining emulation)
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
    FIRST_ERROR,      // Case 1: first error on this page, inline descriptor set
    ADDED_ERROR,      // Case 2/3: additional error recorded in EPT
    ALREADY_KNOWN,    // already registered error position, no new recording
    PAGE_RETIRED,     // 6th+ error, page retirement triggered
};

// EPT Entry: one per 2MB page, holds up to 4 additional error positions
struct EPTEntry {
    uint64_t tag{0};            // page base PA (2MB aligned physical address)
    uint16_t slots[4]{0};       // 15-bit cache line index per slot
    uint8_t  slot_count{0};     // number of used slots (0~4)
    uint64_t lru_counter{0};    // for LRU eviction
    bool     valid{false};
};

class ErrorPageManager {
// Global Private Variables
private:
    std::unordered_set<uint64_t> error_pages;  // Page 단위 error (기존 호환용)
    std::unordered_set<uint64_t> current_ppage;
    ErrorPageManagerMode mode;
    champsim::chrono::clock::duration error_latency_penalty{};
    champsim::chrono::clock::duration pte_error_latency_penalty{};
    champsim::chrono::clock::duration retirement_latency_penalty{};  // page retirement penalty
    static std::unique_ptr<ErrorPageManager> instance;

// Dual-Layer Error Recording (EPT)
private:
    // Inline Error Descriptor: page_base_pa → first error's 15-bit cache line index
    std::unordered_map<uint64_t, uint16_t> inline_descriptors;
    // Multi-error flag: pages with 2+ errors
    std::unordered_set<uint64_t> multi_error_pages;
    // Error Position Table: 64 entries
    static constexpr size_t EPT_NUM_ENTRIES = 64;
    static constexpr size_t EPT_SLOTS_PER_ENTRY = 4;
    static constexpr size_t MAX_ERRORS_PER_PAGE = 5;  // 1 inline + 4 EPT
    std::array<EPTEntry, EPT_NUM_ENTRIES> ept{};
    uint64_t ept_lru_counter{0};
    // retired_pages removed: retirement now resets page to clean state (new page allocation emulation)

    // Also maintain a flat set for fast is_error_position lookup (cache line aligned addresses)
    std::unordered_set<uint64_t> error_addresses;  // all tracked error positions (for cache is_error_data)

// EPT Statistics
private:
    uint64_t stat_case1_count{0};     // first error recordings
    uint64_t stat_case2_count{0};     // second error recordings (EPT entry allocated)
    uint64_t stat_case3_count{0};     // third+ error recordings (EPT slot appended)
    uint64_t stat_retirement_count{0}; // pages newly retired (6th error triggers retirement)
    uint64_t stat_ept_eviction_count{0}; // EPT entry evictions
    uint64_t stat_already_known_count{0}; // duplicate error accesses

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
    int debug{1};  // Debug flag: 1 to enable [ERROR_CYCLE] and [EPT] logs, 0 to disable

// Cache Pinning (Error Way Partitioning)
private:
    bool cache_pinning_enabled{false};  // Enable/disable cache pinning feature
    bool dynamic_error_latency_enabled{true};  // true: emulate PTW(PSC+cache), false: fixed error_latency_penalty
    uint32_t max_error_ways_per_set{8};  // Maximum number of pinned/error ways per LLC set


// Error Statistics
private:
    uint64_t total_error_count{0};

public:
    // Singleton pattern
    static ErrorPageManager& get_instance() {
        if (!instance) {
            instance = std::make_unique<ErrorPageManager>();
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
    // Dual-Layer Error Recording API
    // ============================================================

    // Record a new error at physical address (64B aligned).
    // Returns the result indicating which case was triggered.
    ErrorRecordResult record_error(uint64_t pa);

    // Check if the given physical address (full, not shifted) is an error position
    // that should be pinned in LLC. Checks inline descriptor + EPT + retired page.
    bool is_error_position(uint64_t pa) const;


    // Get error positions that will be unpinned due to EPT eviction
    // Returns the list of full physical addresses (64B aligned, NOT shifted) that were in the evicted entry
    std::vector<uint64_t> get_ept_eviction_victims(size_t ept_index) const;

    // Legacy compatibility: is_error_address checks error_addresses set
    bool is_error_address(champsim::address addr) const { return error_addresses.find(addr.to<uint64_t>()) != error_addresses.end(); }

    // Get number of tracked error addresses
    size_t get_error_address_count() const { return error_addresses.size(); }
    void clear_all_error_addresses() { error_addresses.clear(); inline_descriptors.clear(); multi_error_pages.clear(); for(auto& e : ept) e.valid = false; }

    // EPT statistics
    uint64_t get_stat_case1_count() const { return stat_case1_count; }
    uint64_t get_stat_case2_count() const { return stat_case2_count; }
    uint64_t get_stat_case3_count() const { return stat_case3_count; }
    uint64_t get_stat_retirement_count() const { return stat_retirement_count; }
    uint64_t get_stat_ept_eviction_count() const { return stat_ept_eviction_count; }
    uint64_t get_stat_already_known_count() const { return stat_already_known_count; }
    size_t get_ept_used_entries() const;
    void print_ept_stats() const;

    // Retirement latency
    void set_retirement_latency(champsim::chrono::clock::duration latency) { retirement_latency_penalty = latency; }
    champsim::chrono::clock::duration get_retirement_latency() const { return retirement_latency_penalty; }

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
    // Internal EPT helpers
    int find_ept_entry(uint64_t page_base_pa) const;
    int allocate_ept_entry(uint64_t page_base_pa);
    int evict_ept_lru();
    void retire_page(uint64_t page_base, int ept_idx);
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
