/*
 * Error Page Manager for ChampSim
 * Manages error pages that require additional latency when accessed
 */

#ifndef ERROR_PAGE_MANAGER_H
#define ERROR_PAGE_MANAGER_H

#include <unordered_set>
#include <random>
#include <memory>
#include "address.h"
#include "chrono.h"
#include "champsim.h"

enum class ErrorPageManagerMode {
    ALL_ON,
    RANDOM,
    CYCLE,
    OFF,
};

class ErrorPageManager {
// Global Private Variables
private:
    std::unordered_set<uint64_t> error_pages;  // Page 단위 error (기존 호환용)
    std::unordered_set<uint64_t> error_addresses;  // Address 단위 error (신규)
    std::unordered_set<uint64_t> current_ppage; 
    ErrorPageManagerMode mode;
    champsim::chrono::clock::duration error_latency_penalty{};
    static std::unique_ptr<ErrorPageManager> instance;

//For Random Error Injection
private:
    std::mt19937 gen{54321};
    std::uniform_real_distribution<double> prob_dist{0.0, 1.0};
    std::exponential_distribution<double> exp_dist{1.0};  // For exponential interval
    //double base_error_probability{0.001};
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
    int debug{0};  // Debug flag: 1 to enable [ERROR_CYCLE] logs, 0 to disable

// Cache Pinning (Error Way Partitioning)
private:
    bool cache_pinning_enabled{false};  // Enable/disable cache pinning feature


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

    // Error address management (신규 - Address 단위)
    void add_error_address(champsim::address addr) { error_addresses.insert(addr.to<uint64_t>()); }
    void remove_error_address(champsim::address addr) { error_addresses.erase(addr.to<uint64_t>()); }
    bool is_error_address(champsim::address addr) const { return error_addresses.find(addr.to<uint64_t>()) != error_addresses.end(); }

    // Monte Carlo Simulation for page error rate
    void init_page_error_rate(double bit_error_rate);

    // Latency management
    void set_error_latency(champsim::chrono::clock::duration latency) { error_latency_penalty = latency; }
    champsim::chrono::clock::duration get_error_latency() const { return error_latency_penalty; }

    // Random error injection settings
    //void set_base_error_probability(double prob) { base_error_probability = prob; }
    void set_errors_per_interval(uint32_t count) { errors_per_interval = count; }
    //double get_base_error_probability() const { return base_error_probability; }
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
    size_t get_error_address_count() const { return error_addresses.size(); }
    size_t get_current_ppage_count() const { return current_ppage.size(); }
    void clear_all_error_pages() { error_pages.clear(); }
    void clear_all_error_addresses() { error_addresses.clear(); }
    void clear_current_ppage() { current_ppage.clear(); }

    // Inject Error at All Pages
    void all_error_pages_on(uint64_t page_num);
    // Inject Random Error 
    // void inject_error_at_random(void);
    
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

};

#endif // ERROR_PAGE_MANAGER_H
