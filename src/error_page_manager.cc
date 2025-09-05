#include "error_page_manager.h"
#include "dram_controller.h"
#include <fmt/core.h>
#include <random>
#include <algorithm>

// Static member initialization
std::unique_ptr<ErrorPageManager> ErrorPageManager::instance = nullptr;

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

void ErrorPageManager::inject_error_at_random(void) {
    if (prob_dist(gen) < base_error_probability) {
        if (current_ppage.empty()) {
            return;
        }
        //Interval 당 Error를 몇 개 만들 것인지
        uint32_t num_errors = std::min(errors_per_interval, static_cast<uint32_t>(current_ppage.size()));

        for (uint32_t i = 0; i < num_errors; ++i) {
            std::uniform_int_distribution<size_t> page_dist(0, current_ppage.size() - 1);
            auto it = current_ppage.begin();
            //하.. 근데 이거 성능 문제가 분명 있을 것 같은데... vector로 바꾸는 것을 고려해봐야 할듯
            std::advance(it, page_dist(gen));
            
            champsim::page_number selected_page{*it};
            add_error_page(selected_page);
            //fmt::print("[ERROR_PAGE_MANAGER] Injected error at page: 0x{:x}\n", selected_page.to<uint64_t>());
        }
    }
}

