/*
 * Error Page Manager for ChampSim
 * Manages error pages that require additional latency when accessed
 */

#ifndef ERROR_PAGE_MANAGER_H
#define ERROR_PAGE_MANAGER_H

#include <unordered_set>
#include <memory>
#include "address.h"
#include "chrono.h"
#include "champsim.h"

class ErrorPageManager {
private:
    std::unordered_set<uint64_t> error_pages;  // Page numbers as integers for efficiency
    champsim::chrono::clock::duration error_latency_penalty{};
    static std::unique_ptr<ErrorPageManager> instance;

public:
    // Singleton pattern
    static ErrorPageManager& get_instance() {
        if (!instance) {
            instance = std::make_unique<ErrorPageManager>();
        }
        return *instance;
    }

    // Error page management
    void add_error_page(champsim::page_number page) {
        error_pages.insert(page.to<uint64_t>());
    }

    void remove_error_page(champsim::page_number page) {
        error_pages.erase(page.to<uint64_t>());
    }

    bool is_error_page(champsim::page_number page) const {
        return error_pages.find(page.to<uint64_t>()) != error_pages.end();
    }

    // Latency management
    void set_error_latency(champsim::chrono::clock::duration latency) {
        error_latency_penalty = latency;
    }

    champsim::chrono::clock::duration get_error_latency() const {
        return error_latency_penalty;
    }

    // Extract page number from physical address
    static champsim::page_number get_page_number(champsim::address addr) {
        return champsim::page_number{addr};
    }

    // Utility functions
    size_t get_error_page_count() const {
        return error_pages.size();
    }

    void clear_all_error_pages() {
        error_pages.clear();
    }

    // Pre-inject error pages at simulation start
    void preload_error_pages(size_t count, uint64_t start_addr = 0x10000000, uint64_t end_addr = 0x80000000);

    // For debugging
    void print_error_pages() const;

};

#endif // ERROR_PAGE_MANAGER_H
