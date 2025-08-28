#include "error_page_manager.h"
#include <fmt/core.h>
#include <random>
#include <algorithm>

// Static member initialization
std::unique_ptr<ErrorPageManager> ErrorPageManager::instance = nullptr;

void ErrorPageManager::preload_error_pages(size_t count, uint64_t start_addr, uint64_t end_addr) {
    static std::mt19937 gen(54321);  // Different seed for preload
    std::uniform_int_distribution<uint64_t> addr_dist(start_addr, end_addr);
    
    fmt::print("[ERROR_PAGE_MANAGER] Pre-loading {} error pages...\n", count);
    
    for (size_t i = 0; i < count; ++i) {
        uint64_t error_addr = addr_dist(gen) & ~0xFFF;  // Align to page boundary
        auto page_num = get_page_number(champsim::address{error_addr});
        add_error_page(page_num);
        //fmt::print("[ERROR_PAGE_MANAGER] Pre-loaded error page #{}: 0x{:x}\n", i+1, page_num.to<uint64_t>());
    }
    
    fmt::print("[ERROR_PAGE_MANAGER] Pre-loading complete. Total error pages: {}\n", error_pages.size());
}

void ErrorPageManager::print_error_pages() const {
    fmt::print("[ERROR_PAGE_MANAGER] Total error pages: {}\n", error_pages.size());
    fmt::print("[ERROR_PAGE_MANAGER] Error latency penalty: {} cycles\n", 
               error_latency_penalty.count());
    
    if (!error_pages.empty()) {
        fmt::print("[ERROR_PAGE_MANAGER] Error page numbers: ");
        for (const auto& page : error_pages) {
            fmt::print("0x{:x} ", page);
        }
        fmt::print("\n");
    }
}

