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
    //PRELOADED,
    ALL_ON,
    RANDOM,
    OFF,
};

class ErrorPageManager {
// Global Private Variables  
private:
    std::unordered_set<uint64_t> error_pages;
    std::unordered_set<uint64_t> current_ppage; 
    ErrorPageManagerMode mode;
    champsim::chrono::clock::duration error_latency_penalty{};
    static std::unique_ptr<ErrorPageManager> instance;

//For Random Error Injection
private:
    std::mt19937 gen{54321};
    std::uniform_real_distribution<double> prob_dist{0.0, 1.0};
    double base_error_probability{0.001};
    uint32_t errors_per_interval{1}; 

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

    // Error page management
    void add_error_page(champsim::page_number page) { error_pages.insert(page.to<uint64_t>()); }
    void remove_error_page(champsim::page_number page) { error_pages.erase(page.to<uint64_t>()); }
    bool is_error_page(champsim::page_number page) const { return error_pages.find(page.to<uint64_t>()) != error_pages.end(); }


    // Latency management
    void set_error_latency(champsim::chrono::clock::duration latency) { error_latency_penalty = latency; }
    champsim::chrono::clock::duration get_error_latency() const { return error_latency_penalty; }
    
    // Random error injection settings
    void set_base_error_probability(double prob) { base_error_probability = prob; }
    void set_errors_per_interval(uint32_t count) { errors_per_interval = count; }
    double get_base_error_probability() const { return base_error_probability; }
    uint32_t get_errors_per_interval() const { return errors_per_interval; }

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
    // Inject Random Error 
    void inject_error_at_random(void);
    
    // For debugging
    void print_error_pages() const;

};

#endif // ERROR_PAGE_MANAGER_H
