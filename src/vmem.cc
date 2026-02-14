/*
 *    Copyright 2023 The ChampSim Contributors
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 * http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */

#include "vmem.h"

#include <cassert>
#include <fmt/core.h>

#include "champsim.h"
#include "dram_controller.h"
#include "util/bits.h"

using namespace champsim::data::data_literals;

VirtualMemory::VirtualMemory(champsim::data::bytes page_table_page_size, std::size_t page_table_levels,
                             champsim::chrono::clock::duration minor_penalty,
                             champsim::chrono::clock::duration data_4kb_penalty,
                             champsim::chrono::clock::duration data_2mb_penalty,
                             MEMORY_CONTROLLER& dram_, std::optional<uint64_t> randomization_seed_)
    : randomization_seed(randomization_seed_), dram(dram_), minor_fault_penalty(minor_penalty),
      data_page_fault_4kb_penalty(data_4kb_penalty), data_page_fault_2mb_penalty(data_2mb_penalty),
      pt_levels(page_table_levels), pte_page_size(page_table_page_size),
      next_pte_page(
          champsim::dynamic_extent{champsim::data::bits{LOG2_PAGE_SIZE}, champsim::data::bits{champsim::lg2(champsim::data::bytes{pte_page_size}.count())}}, 0)
{
  assert(pte_page_size > 1_kiB);
  assert(champsim::is_power_of_2(pte_page_size.count()));

  champsim::page_number last_vpage{
      champsim::lowest_address_for_size(champsim::data::bytes{PAGE_SIZE + champsim::ipow(pte_page_size.count(), static_cast<unsigned>(pt_levels))})};
  champsim::data::bits required_bits{LOG2_PAGE_SIZE + champsim::lg2(last_vpage.to<uint64_t>())};
  if (required_bits > champsim::address::bits) {
    fmt::print("[VMEM] WARNING: virtual memory configuration would require {} bits of addressing.\n", required_bits); // LCOV_EXCL_LINE
  }
  if (required_bits > champsim::data::bits{champsim::lg2(dram.size().count())}) {
    fmt::print("[VMEM] WARNING: physical memory size is smaller than virtual memory size.\n"); // LCOV_EXCL_LINE
  }
  // init_error_page_penalty(); // Hamoci's Addition
  populate_pages();
  shuffle_pages();
}

VirtualMemory::VirtualMemory(champsim::data::bytes page_table_page_size, std::size_t page_table_levels,
                             champsim::chrono::clock::duration minor_penalty,
                             champsim::chrono::clock::duration data_4kb_penalty,
                             champsim::chrono::clock::duration data_2mb_penalty,
                             MEMORY_CONTROLLER& dram_)
    : VirtualMemory(page_table_page_size, page_table_levels, minor_penalty, data_4kb_penalty, data_2mb_penalty, dram_, {})
{
}

void VirtualMemory::populate_pages()
{
  assert(dram.size() > 1_MiB);
  ppage_free_list.resize(((dram.size() - 1_MiB) / PAGE_SIZE).count());
  assert(ppage_free_list.size() != 0);
  champsim::page_number base_address =
      champsim::page_number{champsim::lowest_address_for_size(std::max<champsim::data::mebibytes>(champsim::data::bytes{PAGE_SIZE}, 1_MiB))};
  for (auto it = ppage_free_list.begin(); it != ppage_free_list.end(); it++) {
    *it = base_address;
    base_address++;
  }
}

void VirtualMemory::shuffle_pages()
{
  if (randomization_seed.has_value())
    std::shuffle(ppage_free_list.begin(), ppage_free_list.end(), std::mt19937_64{randomization_seed.value()});
}

champsim::dynamic_extent VirtualMemory::extent(std::size_t level) const
{
  const champsim::data::bits lower{LOG2_PAGE_SIZE + champsim::lg2(pte_page_size.count()) * (level - 1)};
  const auto size = static_cast<std::size_t>(champsim::lg2(pte_page_size.count()));
  return champsim::dynamic_extent{lower, size};
}

champsim::data::bits VirtualMemory::shamt(std::size_t level) const { return extent(level).lower; }

uint64_t VirtualMemory::get_offset(champsim::address vaddr, std::size_t level) const { return champsim::address_slice{extent(level), vaddr}.to<uint64_t>(); }

uint64_t VirtualMemory::get_offset(champsim::page_number vaddr, std::size_t level) const { return get_offset(champsim::address{vaddr}, level); }

champsim::page_number VirtualMemory::ppage_front() const
{
  assert(available_ppages() > 0);
  return ppage_free_list.front();
}

void VirtualMemory::ppage_pop()
{
  ppage_free_list.pop_front();
  if (available_ppages() == 0) {
    fmt::print("[VMEM] WARNING: Out of physical memory, freeing ppages\n");
    populate_pages();
    shuffle_pages();
  }
}

std::size_t VirtualMemory::available_ppages() const { return (ppage_free_list.size()); }

std::pair<champsim::page_number, champsim::chrono::clock::duration> VirtualMemory::va_to_pa(uint32_t cpu_num, champsim::page_number vaddr)
{
  auto [ppage, fault] = vpage_to_ppage_map.try_emplace({cpu_num, champsim::page_number{vaddr}}, ppage_front());
  //page_number{vaddr}이 vpage_to_ppage_map에 존재하지 않으면 {cpu_num, page_number{vaddr}}를 Key, ppage_front를 value로 추가
  // ppage_front는 Physical Page Free List의 Head를 가져옴
  //ppage에는 삽입된 항목의 iterator가, fault에는 삽입이 일어났는지 여부가 저장
  // this vpage doesn't yet have a ppage mapping
  if (fault) {
    ppage_pop();
    ErrorPageManager::get_instance().add_current_ppage(ppage->second); //Hamoci's Addition
    // Add reverse mapping for error latency calculation
    ppage_to_vpage_map[{cpu_num, ppage->second}] = champsim::page_number{vaddr};
  }

  // Select penalty based on PAGE_SIZE (4KB vs 2MB)
  auto penalty = champsim::chrono::clock::duration::zero();
  if (fault) {
    if (PAGE_SIZE == 4096) {
      penalty = data_page_fault_4kb_penalty;  // 4KB page
    } else if (PAGE_SIZE == 2097152) {
      penalty = data_page_fault_2mb_penalty;  // 2MB page
    } else {
      // Fallback: use 4KB penalty for unknown page sizes
      penalty = data_page_fault_4kb_penalty;
    }
  }

  /* Hamoci's Error Page Management Logic */
  // if (is_error_page(champsim::page_number{ppage->second})) {
  //   penalty += error_page_penalty;
  //   remove_error_page(champsim::page_number{ppage->second});
  // }
  //잘 생각해보니, 좀 더 나은 방법이 있을 것 같음
  //만약 va_to_pa, get_pte_pa만 Latency를 추가하게 되면, 즉 변환 과정에 Latency를 추가하게 되면
  //TLB Hit 시 Latency가 반영되지 않음
  //차라리 이렇게 할 바엔 실제 Physical Page에 접근하는 순간, 즉 Cache에 Data를 요청하기 직전에
  //Error Page에 대한 요청이라면 Error를 수정하는 Latency를 추가해주는 쪽이 더 정교할듯
  /* End of Hamoci's Error Page Management Logic */
  if constexpr (champsim::debug_print) {
    fmt::print("[VMEM] {} paddr: {} vpage: {} fault: {}\n", __func__, ppage->second, champsim::page_number{vaddr}, fault);
  }

  //ppage->second (Physical Page Number), Penalty가 전달됨
  return std::pair{ppage->second, penalty};
}

std::pair<champsim::address, champsim::chrono::clock::duration> VirtualMemory::get_pte_pa(uint32_t cpu_num, champsim::page_number vaddr, std::size_t level)
{
  if (champsim::page_offset{next_pte_page} == champsim::page_offset{0}) {
    active_pte_page = ppage_front();
    ppage_pop();
  }

  champsim::dynamic_extent pte_table_entry_extent{champsim::address::bits, shamt(level)};
  auto [ppage, fault] =
      page_table.try_emplace({cpu_num, level, champsim::address_slice{pte_table_entry_extent, vaddr}}, champsim::splice(active_pte_page, next_pte_page));

  // this PTE doesn't yet have a mapping
  if (fault) {
    next_pte_page++;
    ErrorPageManager::get_instance().add_current_ppage(champsim::page_number{ppage->second}); //Hamoci's Addition
  }

  auto offset = get_offset(vaddr, level);
  champsim::address paddr{
      champsim::splice(ppage->second, champsim::address_slice{champsim::dynamic_extent{champsim::data::bits{champsim::lg2(pte_entry::byte_multiple)},
                                                                                       static_cast<std::size_t>(champsim::lg2(pte_page_size.count()))},
                                                              offset})};
  if constexpr (champsim::debug_print) {
    fmt::print("[VMEM] {} paddr: {} vaddr: {} pt_page_offset: {} translation_level: {} fault: {}\n", __func__, paddr, vaddr, offset, level, fault);
  }

  auto penalty = minor_fault_penalty;
  if (!fault) {
    penalty = champsim::chrono::clock::duration::zero();
  }
    /* Hamoci's Error Page Management Logic */
  // if (is_error_page(champsim::page_number{ppage->second})) {
  //   penalty += error_page_penalty;
  //   remove_error_page(champsim::page_number{ppage->second});
  // }
  /* End of Hamoci's Error Page Management Logic */
  
  return {paddr, penalty};
}

std::optional<champsim::address> VirtualMemory::get_pte_pa_if_present(uint32_t cpu_num, champsim::page_number vaddr, std::size_t level) const
{
  champsim::dynamic_extent pte_table_entry_extent{champsim::address::bits, shamt(level)};
  auto key = std::make_tuple(cpu_num, static_cast<uint32_t>(level), champsim::address_slice{pte_table_entry_extent, vaddr});
  auto ppage = page_table.find(key);

  if (ppage == page_table.end()) {
    return std::nullopt;
  }

  auto offset = get_offset(vaddr, level);
  champsim::address paddr{
      champsim::splice(ppage->second, champsim::address_slice{champsim::dynamic_extent{champsim::data::bits{champsim::lg2(pte_entry::byte_multiple)},
                                                                                       static_cast<std::size_t>(champsim::lg2(pte_page_size.count()))},
                                                              offset})};
  return paddr;
}

/* Hamoci's Error Page Management Logic */
// void VirtualMemory::init_error_page_penalty(void) {
//   error_page_penalty = minor_fault_penalty * 4; // CPU Clock Period에 직접 접근하기 어려워, 간접적으로 사용
// }
// void VirtualMemory::add_error_page(champsim::page_number page) { error_pages.insert(page); }
// void VirtualMemory::remove_error_page(champsim::page_number page) { error_pages.erase(page); }
// bool VirtualMemory::is_error_page(champsim::page_number page) const { return error_pages.find(page) != error_pages.end(); }
/* End of Hamoci's Error Page Management Logic */

std::optional<champsim::page_number> VirtualMemory::get_vpage_for_ppage(uint32_t cpu_num, champsim::page_number paddr) const
{
  auto it = ppage_to_vpage_map.find({cpu_num, paddr});
  if (it != ppage_to_vpage_map.end()) {
    return it->second;
  }
  return std::nullopt;
}
