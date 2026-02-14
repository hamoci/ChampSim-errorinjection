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

#include "dram_controller.h"

#include <algorithm>
#include <cfenv>
#include <cmath>
#include <random>
#include <fmt/core.h>

#include "deadlock.h"
#include "error_page_manager.h"  // Hamoci's addition for error page support
#include "instruction.h"
#include "util/bits.h" // for lg2, bitmask
#include "util/span.h"
#include "util/units.h"
#include "vmem.h"      // For dynamic error latency calculation
#include "ptw.h"       // For PSC access
#include "cache.h"     // For cache lookup

namespace
{
// Local debug switch for focused dynamic error-latency traces.
// Toggle this directly in code without enabling global champsim::debug_print.
constexpr bool debug_dynamic_error_latency = false;

uint64_t to_cpu_cycles(champsim::chrono::clock::duration latency)
{
  auto cpu_period = ErrorPageManager::get_instance().get_cpu_clock_period();
  if (cpu_period.count() == 0) {
    return 0;
  }
  return static_cast<uint64_t>(latency / cpu_period);
}
}

MEMORY_CONTROLLER::MEMORY_CONTROLLER(champsim::chrono::picoseconds dbus_period, champsim::chrono::picoseconds mc_period, std::size_t t_rp, std::size_t t_rcd,
                                     std::size_t t_cas, std::size_t t_ras, champsim::chrono::microseconds refresh_period, std::vector<channel_type*>&& ul,
                                     std::size_t rq_size, std::size_t wq_size, std::size_t chans, champsim::data::bytes chan_width, std::size_t rows,
                                     std::size_t columns, std::size_t ranks, std::size_t bankgroups, std::size_t banks, std::size_t refreshes_per_period)
    : champsim::operable(mc_period), queues(std::move(ul)), channel_width(chan_width),
      address_mapping(chan_width, BLOCK_SIZE / chan_width.count(), chans, bankgroups, banks, columns, ranks, rows), data_bus_period(dbus_period)
{
  for (std::size_t i{0}; i < chans; ++i) {
    channels.emplace_back(dbus_period, mc_period, t_rp, t_rcd, t_cas, t_ras, refresh_period, refreshes_per_period, chan_width, rq_size, wq_size,
                          address_mapping);
  }
}

DRAM_CHANNEL::DRAM_CHANNEL(champsim::chrono::picoseconds dbus_period, champsim::chrono::picoseconds mc_period, std::size_t t_rp, std::size_t t_rcd,
                           std::size_t t_cas, std::size_t t_ras, champsim::chrono::microseconds refresh_period, std::size_t refreshes_per_period,
                           champsim::data::bytes width, std::size_t rq_size, std::size_t wq_size, DRAM_ADDRESS_MAPPING addr_mapper)
    : champsim::operable(mc_period), address_mapping(addr_mapper), WQ{wq_size}, RQ{rq_size}, channel_width(width),
      DRAM_ROWS_PER_REFRESH(address_mapping.rows() / refreshes_per_period), tRP(t_rp * mc_period), tRCD(t_rcd * mc_period), tCAS(t_cas * mc_period),
      tRAS(t_ras * mc_period), tREF(refresh_period / refreshes_per_period),
      tRFC(std::chrono::duration_cast<champsim::chrono::clock::duration>(
          std::sqrt(champsim::data::bits_per_byte * (double)champsim::data::gibibytes{density()}.count()) * mc_period * t_ras)),
      DRAM_DBUS_TURN_AROUND_TIME(tRAS),
      DRAM_DBUS_RETURN_TIME(std::chrono::duration_cast<champsim::chrono::clock::duration>(dbus_period * address_mapping.prefetch_size)),
      DRAM_DBUS_BANKGROUP_STALL(
          std::chrono::duration_cast<champsim::chrono::clock::duration>((dbus_period * std::max(address_mapping.prefetch_size / 3, std::size_t{1})))),
      data_bus_period(dbus_period)
{
  request_array_type br(address_mapping.ranks() * address_mapping.banks() * address_mapping.bankgroups());
  bank_request = br;
  active_request = std::end(bank_request);
}

DRAM_ADDRESS_MAPPING::DRAM_ADDRESS_MAPPING(champsim::data::bytes channel_width_, std::size_t pref_size_, std::size_t channels_, std::size_t bankgroups_,
                                           std::size_t banks_, std::size_t columns_, std::size_t ranks_, std::size_t rows_)
    : address_slicer(make_slicer(channel_width_, pref_size_, channels_, bankgroups_, banks_, columns_, ranks_, rows_)), prefetch_size(pref_size_)
{
  // assert prefetch size is not zero
  assert(prefetch_size != 0);
  // assert prefetch size is multiple of block size
  assert((channel_width_.count() * prefetch_size) % BLOCK_SIZE == 0);

  // mapping sanity check
  assert(columns() >= 1 && columns() == columns_);
  assert(rows() >= 1 && rows() == rows_);
  assert(banks() >= 1 && banks() == banks_);
  assert(bankgroups() >= 1 && bankgroups() == bankgroups_);
  assert(ranks() >= 1 && ranks() == ranks_);
  assert(channels() >= 1 && channels() == channels_);
}

auto DRAM_ADDRESS_MAPPING::make_slicer(champsim::data::bytes channel_width, std::size_t pref_size, std::size_t channels, std::size_t bankgroups,
                                       std::size_t banks, std::size_t columns, std::size_t ranks, std::size_t rows) -> slicer_type
{
  std::array<std::size_t, slicer_type::size()> params{};
  params.at(SLICER_ROW_IDX) = rows;
  params.at(SLICER_COLUMN_IDX) = columns / pref_size;
  params.at(SLICER_RANK_IDX) = ranks;
  params.at(SLICER_BANK_IDX) = banks;
  params.at(SLICER_BANKGROUP_IDX) = bankgroups;
  params.at(SLICER_CHANNEL_IDX) = channels;
  params.at(SLICER_OFFSET_IDX) = channel_width.count() * pref_size;
  return std::apply([](auto... p) { return champsim::make_contiguous_extent_set(0, champsim::lg2(p)...); }, params);
}

long MEMORY_CONTROLLER::operate()
{
  long progress{0};

  initiate_requests();

  for (auto& channel : channels) {
    progress += channel._operate();
  }

  return progress;
}

long DRAM_CHANNEL::operate()
{
  long progress{0};

  if (warmup) {
    for (auto& entry : RQ) {
      if (entry.has_value()) {
        response_type response{entry->address, entry->v_address, entry->data, entry->pf_metadata, entry->instr_depend_on_me};
        for (auto* ret : entry.value().to_return) {
          ret->push_back(response);
        }

        ++progress;
        entry.reset();
      }
    }

    for (auto& entry : WQ) {
      if (entry.has_value()) {
        ++progress;
      }
      entry.reset();
    }
  }

  /* Hamoci : Cycle-based Error Tracking */
  // Update cycle error counter every cycle (only in non-warmup and CYCLE mode)
  if (!warmup && ErrorPageManager::get_instance().get_mode() == ErrorPageManagerMode::CYCLE) {
    ErrorPageManager::get_instance().update_cycle_errors(current_time);
  }
  /* Hamoci : End of Error Tracking */

  check_write_collision();
  check_read_collision();
  progress += finish_dbus_request();
  swap_write_mode();
  progress += schedule_refresh();
  progress += populate_dbus();
  progress += service_packet(schedule_packet());

  return progress;
}

long DRAM_CHANNEL::finish_dbus_request()
{
  long progress{0};

  if (active_request != std::end(bank_request) && active_request->ready_time <= current_time) {
    response_type response{active_request->pkt->value().address, active_request->pkt->value().v_address, active_request->pkt->value().data,
                           active_request->pkt->value().pf_metadata, active_request->pkt->value().instr_depend_on_me};
    for (auto* ret : active_request->pkt->value().to_return) {
      ret->push_back(response);
    }

    active_request->valid = false;

    active_request->pkt->reset();
    active_request = std::end(bank_request);
    ++progress;
  }

  return progress;
}

long DRAM_CHANNEL::schedule_refresh()
{
  long progress = {0};
  // check if we reached refresh cycle

  bool schedule_refresh = current_time >= last_refresh + tREF;
  // if so, record stats
  if (schedule_refresh) {
    last_refresh = current_time;
    refresh_row += DRAM_ROWS_PER_REFRESH;
    sim_stats.refresh_cycles++;
    if (refresh_row >= address_mapping.rows())
      refresh_row -= address_mapping.rows();
  }

  // go through each bank, and handle refreshes
  for (auto& b_req : bank_request) {
    // refresh is now needed for this bank
    if (schedule_refresh) {
      b_req.need_refresh = true;
    }
    // refresh is being scheduled for this bank
    if (b_req.need_refresh && !b_req.valid) {
      b_req.ready_time = current_time + tRFC;
      b_req.need_refresh = false;
      b_req.under_refresh = true;
    }
    // refresh is done for this bank
    else if (b_req.under_refresh && b_req.ready_time <= current_time) {
      b_req.under_refresh = false;
      b_req.open_row.reset();
      progress++;
    }

    if (b_req.under_refresh)
      progress++;
  }
  return (progress);
}

void DRAM_CHANNEL::swap_write_mode()
{
  // these values control when to send out a burst of writes
  const std::size_t DRAM_WRITE_HIGH_WM = ((std::size(WQ) * 7) >> 3); // 7/8th
  const std::size_t DRAM_WRITE_LOW_WM = ((std::size(WQ) * 6) >> 3);  // 6/8th
  // const std::size_t MIN_DRAM_WRITES_PER_SWITCH = ((std::size(WQ) * 1) >> 2); // 1/4

  // Check queue occupancy
  auto wq_occu = static_cast<std::size_t>(std::count_if(std::begin(WQ), std::end(WQ), [](const auto& x) { return x.has_value(); }));
  auto rq_occu = static_cast<std::size_t>(std::count_if(std::begin(RQ), std::end(RQ), [](const auto& x) { return x.has_value(); }));

  // Change modes if the queues are unbalanced
  if ((!write_mode && (wq_occu >= DRAM_WRITE_HIGH_WM || (rq_occu == 0 && wq_occu > 0)))
      || (write_mode && (wq_occu == 0 || (rq_occu > 0 && wq_occu < DRAM_WRITE_LOW_WM)))) {
    // Reset scheduled requests
    for (auto it = std::begin(bank_request); it != std::end(bank_request); ++it) {
      // Leave active request on the data bus
      if (it != active_request && it->valid) {
        // Leave rows charged
        if (it->ready_time < (current_time + tCAS)) {
          it->open_row.reset();
        }

        // This bank is ready for another DRAM request
        it->valid = false;
        it->pkt->value().scheduled = false;
        it->pkt->value().ready_time = current_time;
      }
    }

    // Add data bus turn-around time
    if (active_request != std::end(bank_request)) {
      dbus_cycle_available = active_request->ready_time + DRAM_DBUS_TURN_AROUND_TIME; // After ongoing finish
    } else {
      dbus_cycle_available = current_time + DRAM_DBUS_TURN_AROUND_TIME;
    }

    // Invert the mode
    write_mode = !write_mode;
  }
}

// Look for requests to put on the bus
long DRAM_CHANNEL::populate_dbus()
{
  long progress{0};

  //Hamoci : std::min_element을 통해 Ready Time이 작은 Bank Request 먼저 처리함
  auto iter_next_process = std::min_element(std::begin(bank_request), std::end(bank_request),
                                            [](const auto& lhs, const auto& rhs) { return !rhs.valid || (lhs.valid && lhs.ready_time < rhs.ready_time); });
  if (iter_next_process->valid && iter_next_process->ready_time <= current_time) {
    if (active_request == std::end(bank_request) && dbus_cycle_available <= current_time) {
      // Bus is available
      // Put this request on the data bus

      // get which bankgroup we are in
      auto op_bankgroup = bankgroup_request_index(iter_next_process->pkt->value().address);
      auto bankgroup_ready_time = bankgroup_readytime[op_bankgroup];

      active_request = iter_next_process;

      // set return time. Incur penalty if bankgroup is on cooldown
      if (bankgroup_ready_time > current_time)
        active_request->ready_time = bankgroup_ready_time + DRAM_DBUS_RETURN_TIME;
      else
        active_request->ready_time = current_time + DRAM_DBUS_RETURN_TIME;

      // set when bankgroup dbus will be next ready
      bankgroup_readytime[op_bankgroup] = current_time + DRAM_DBUS_RETURN_TIME + DRAM_DBUS_BANKGROUP_STALL;

      if (iter_next_process->row_buffer_hit) {
        if (write_mode) {
          ++sim_stats.WQ_ROW_BUFFER_HIT;
        } else {
          ++sim_stats.RQ_ROW_BUFFER_HIT;
        }
      } else if (write_mode) {
        ++sim_stats.WQ_ROW_BUFFER_MISS;
      } else {
        ++sim_stats.RQ_ROW_BUFFER_MISS;
      }

      ++progress;
    } else {
      // Bus is congested
      if (active_request != std::end(bank_request)) {
        sim_stats.dbus_cycle_congested += (active_request->ready_time - current_time) / data_bus_period;
      } else {
        sim_stats.dbus_cycle_congested += (dbus_cycle_available - current_time) / data_bus_period;
      }
      ++sim_stats.dbus_count_congested;
    }
  }

  return progress;
}

std::size_t DRAM_CHANNEL::bank_request_index(champsim::address addr) const
{
  auto op_bank = address_mapping.get_bank(addr);

  return (bankgroup_request_index(addr) * address_mapping.banks() + op_bank);
}

std::size_t DRAM_CHANNEL::bankgroup_request_index(champsim::address addr) const
{
  auto op_rank = address_mapping.get_rank(addr);
  auto op_bankgroup = address_mapping.get_bankgroup(addr);

  return (op_rank * address_mapping.bankgroups() + op_bankgroup);
}

// Look for queued packets that have not been scheduled
DRAM_CHANNEL::queue_type::iterator DRAM_CHANNEL::schedule_packet()
{
  // Look for queued packets that have not been scheduled
  // prioritize packets that are ready to execute, bank is free
  auto next_schedule = [this](const auto& lhs, const auto& rhs) {
    if (!(rhs.has_value() && !rhs.value().scheduled)) {
      return true;
    }
    if (!(lhs.has_value() && !lhs.value().scheduled)) {
      return false;
    }

    auto lop_idx = this->bank_request_index(lhs.value().address);
    auto rop_idx = this->bank_request_index(rhs.value().address);
    auto rready = !this->bank_request[rop_idx].valid;
    auto lready = !this->bank_request[lop_idx].valid;
    return (rready == lready) ? lhs.value().ready_time <= rhs.value().ready_time : lready;
  };
  queue_type::iterator iter_next_schedule;
  if (write_mode) {
    iter_next_schedule = std::min_element(std::begin(WQ), std::end(WQ), next_schedule);
  } else {
    iter_next_schedule = std::min_element(std::begin(RQ), std::end(RQ), next_schedule);
  }
  return (iter_next_schedule);
}

long DRAM_CHANNEL::service_packet(DRAM_CHANNEL::queue_type::iterator pkt)
{
  long progress{0};
  static long int dram_access_count{0};
  if (pkt->has_value() && pkt->value().ready_time <= current_time) {
    auto op_row = address_mapping.get_row(pkt->value().address);
    auto op_idx = bank_request_index(pkt->value().address);

    if (!bank_request[op_idx].valid && !bank_request[op_idx].under_refresh) {
      bool row_buffer_hit = (bank_request[op_idx].open_row.has_value() && *(bank_request[op_idx].open_row) == op_row);
      dram_access_count++;
      // Hamoci's Error Check - Apply error latency based on mode
      auto error_latency = champsim::chrono::clock::duration{};

      // RANDOM mode: BER-based error check
      if (ErrorPageManager::get_instance().get_mode() == ErrorPageManagerMode::RANDOM &&
          ErrorPageManager::get_instance().check_page_error()) {
        // Select latency based on access type and dynamic/fixed mode
        if (ErrorPageManager::get_instance().is_dynamic_error_latency_enabled()) {
          std::optional<champsim::address> vaddr_hint = std::nullopt;
          if (pkt->value().type == access_type::TRANSLATION) {
            vaddr_hint = pkt->value().v_address;
          }
          error_latency = calculate_dynamic_error_latency(pkt->value().cpu, pkt->value().address, vaddr_hint);
          if (debug_dynamic_error_latency) {
            fmt::print("[ERR_LAT][RANDOM][DYNAMIC] type={} addr=0x{:x} cpu={} latency={} cycles\n",
                       access_type_names.at(champsim::to_underlying(pkt->value().type)),
                       pkt->value().address.to<uint64_t>(), pkt->value().cpu, to_cpu_cycles(error_latency));
          }
        } else if (pkt->value().type == access_type::TRANSLATION) {
          error_latency = ErrorPageManager::get_instance().get_pte_error_latency();
        } else {
          error_latency = ErrorPageManager::get_instance().get_error_latency();
          if (debug_dynamic_error_latency) {
            fmt::print("[ERR_LAT][RANDOM][FIXED] type={} addr=0x{:x} cpu={} latency={} cycles\n",
                       access_type_names.at(champsim::to_underlying(pkt->value().type)),
                       pkt->value().address.to<uint64_t>(), pkt->value().cpu, to_cpu_cycles(error_latency));
          }
        }
        ErrorPageManager::get_instance().record_error_access();
        //for debug
        //fmt::print("[DRAM_BER_ERROR] Page error occurred! address={} page_error_rate={:.2e} additional_latency={} cycles, dram access ={}\n",
        //           pkt->value().address, ErrorPageManager::get_instance().get_page_error_rate(),
        //           error_latency.count(), dram_access_count);
      }
      // CYCLE mode: Consume error from counter
      else if (ErrorPageManager::get_instance().get_mode() == ErrorPageManagerMode::CYCLE &&
               ErrorPageManager::get_instance().consume_cycle_error()) {
        // 64B 정렬된 주소 (캐시 라인 단위)
        auto aligned_addr = champsim::address{pkt->value().address.to<uint64_t>() >> 6};

        bool already_registered = false;

        // Cache Pinning 활성화 시에만 중복 체크
        if (ErrorPageManager::get_instance().is_cache_pinning_enabled()) {
          // 이미 등록된 캐시 라인인지 체크
          already_registered = ErrorPageManager::get_instance().is_error_address(aligned_addr);
          // 64B 정렬된 주소로 등록
          ErrorPageManager::get_instance().add_error_address(aligned_addr);
        }

        // Cache Pinning 비활성화 또는 새로운 캐시 라인일 때 latency 부여
        if (!already_registered) {
          // Select latency based on access type and dynamic/fixed mode
          if (ErrorPageManager::get_instance().is_dynamic_error_latency_enabled()) {
            std::optional<champsim::address> vaddr_hint = std::nullopt;
            if (pkt->value().type == access_type::TRANSLATION) {
              vaddr_hint = pkt->value().v_address;
            }
            error_latency = calculate_dynamic_error_latency(pkt->value().cpu, pkt->value().address, vaddr_hint);
            if (debug_dynamic_error_latency) {
              fmt::print("[ERR_LAT][CYCLE][DYNAMIC] type={} addr=0x{:x} cpu={} latency={} cycles\n",
                         access_type_names.at(champsim::to_underlying(pkt->value().type)),
                         pkt->value().address.to<uint64_t>(), pkt->value().cpu, to_cpu_cycles(error_latency));
            }
          } else if (pkt->value().type == access_type::TRANSLATION) {
            error_latency = ErrorPageManager::get_instance().get_pte_error_latency();
          } else {
            error_latency = ErrorPageManager::get_instance().get_error_latency();
            if (debug_dynamic_error_latency) {
              fmt::print("[ERR_LAT][CYCLE][FIXED] type={} addr=0x{:x} cpu={} latency={} cycles\n",
                         access_type_names.at(champsim::to_underlying(pkt->value().type)),
                         pkt->value().address.to<uint64_t>(), pkt->value().cpu, to_cpu_cycles(error_latency));
            }
          }
        }
        ErrorPageManager::get_instance().record_error_access();

        // Debug output - show when error occurs
        bool debug_mode = false; //hamoci: revise this for debug print
        if(debug_mode) {
          fmt::print("[ERROR_OCCUR] Address: 0x{:x} Aligned: 0x{:x} (Total Errors: {}) {} (PinnedLines: {})\n",
                    pkt->value().address.to<uint64_t>(),
                    aligned_addr.to<uint64_t>(),
                    ErrorPageManager::get_instance().get_total_error_count(),
                    already_registered ? "(already registered)" : "(new)",
                    ErrorPageManager::get_instance().get_error_address_count());
        }
      }

      // this bank is now busy
      auto row_charge_delay = champsim::chrono::clock::duration{bank_request[op_idx].open_row.has_value() ? tRP + tRCD : tRCD};
      auto base_latency = tCAS + (row_buffer_hit ? champsim::chrono::clock::duration{} : row_charge_delay);
      auto total_latency = base_latency + error_latency;
      
      // Print timing info for verification
      // if (error_latency > champsim::chrono::clock::duration{}) {
      //   fmt::print("[DRAM_TIMING] Normal latency: {} DRAM cycles, Error latency: {} CPU cycles, Total: {} DRAM cycles\n", 
      //              base_latency.count() / clock_period.count(),
      //              ErrorPageManager::get_instance().get_error_latency_cycles(),
      //              total_latency.count() / clock_period.count());
      // }
      
      bank_request[op_idx] = {true,  row_buffer_hit,        false,
                              false, std::optional{op_row}, 
                              current_time + total_latency,
                              pkt};
      pkt->value().scheduled = true;
      pkt->value().ready_time = champsim::chrono::clock::time_point::max();

      ++progress;
    }
  }

  return progress;
}

void MEMORY_CONTROLLER::initialize()
{
  using namespace champsim::data::data_literals;
  using namespace std::literals::chrono_literals;
  auto sz = this->size();
  if (champsim::data::gibibytes gb_sz{sz}; gb_sz > 1_GiB) {
    fmt::print("Off-chip DRAM Size: {}", gb_sz);
  } else if (champsim::data::mebibytes mb_sz{sz}; mb_sz > 1_MiB) {
    fmt::print("Off-chip DRAM Size: {}", mb_sz);
  } else if (champsim::data::kibibytes kb_sz{sz}; kb_sz > 1_kiB) {
    fmt::print("Off-chip DRAM Size: {}", kb_sz);
  } else {
    fmt::print("Off-chip DRAM Size: {}", sz);
  }
  fmt::print(" Channels: {} Width: {}-bit Data Rate: {} MT/s\n", std::size(channels), champsim::data::bits_per_byte * channel_width.count(),
             1us / (data_bus_period));

  // Hamoci's Error Page Manager initialization
  // Example initialization with BER-based error modeling

  fmt::print("[ERROR_PAGE_MANAGER] Error latency: {} \n",
             ErrorPageManager::get_instance().get_error_latency().count());
  fmt::print("[ERROR_PAGE_MANAGER] Dynamic error latency: {}\n",
             ErrorPageManager::get_instance().is_dynamic_error_latency_enabled() ? "ON" : "OFF (fixed)");
  fmt::print("[ERROR_PAGE_MANAGER] Random seed: 54321 (fixed for preload reproducibility)\n");
  
  if (ErrorPageManager::get_instance().get_mode() == ErrorPageManagerMode::ALL_ON) {
    uint64_t all_error_pages_count = this->size().count() >> LOG2_PAGE_SIZE;
    ErrorPageManager::get_instance().all_error_pages_on(all_error_pages_count);
    fmt::print("[ERROR_PAGE_MANAGER] All error pages on: {}\n", all_error_pages_count);
    fmt::print("[ERROR_PAGE_MANAGER] Total error pages: {}\n", 
             ErrorPageManager::get_instance().get_error_page_count());
  }
  else if (ErrorPageManager::get_instance().get_mode() == ErrorPageManagerMode::RANDOM) {
    fmt::print("[ERROR_PAGE_MANAGER] BER-based error modeling enabled\n");
    // Initialize page error rate from configured bit error rate
    double ber = ErrorPageManager::get_instance().get_bit_error_rate();
    if (ber > 0.0) {
      ErrorPageManager::get_instance().init_page_error_rate(ber);
    } else {
      // Fallback to default DRAM BER if not configured
      ErrorPageManager::get_instance().init_page_error_rate(1e-12);
    }
    fmt::print("[ERROR_PAGE_MANAGER] Bit Error Rate: {:.2e}\n", 
      ErrorPageManager::get_instance().get_bit_error_rate());
    fmt::print("[ERROR_PAGE_MANAGER] Page Error Rate: {:.2e}\n",
      ErrorPageManager::get_instance().get_page_error_rate());
    fmt::print("[ERROR_PAGE_MANAGER] Page Size: {} bits\n",
      ErrorPageManager::get_instance().get_page_size_bits());
  } else if(ErrorPageManager::get_instance().get_mode() == ErrorPageManagerMode::CYCLE) {
    fmt::print("[ERROR_PAGE_MANAGER] Cycle-based error modeling enabled\n");
    fmt::print("[ERROR_PAGE_MANAGER] Errors per interval: {}\n",
      ErrorPageManager::get_instance().get_errors_per_interval());
    fmt::print("[ERROR_PAGE_MANAGER] Error cycle interval: {} cycles\n",
      ErrorPageManager::get_instance().get_error_cycle_interval());
  } else {
    fmt::print("[ERROR_PAGE_MANAGER] Error pages off\n");
  }

  // Set references for dynamic error latency calculation
  for (auto& chan : channels) {
    chan.set_vmem(vmem);
    chan.set_ptws(ptws);
    chan.set_caches(caches);
  }
}

void DRAM_CHANNEL::initialize() {}

void MEMORY_CONTROLLER::begin_phase()
{
  std::size_t chan_idx = 0;
  for (auto& chan : channels) {
    DRAM_CHANNEL::stats_type new_stats;
    new_stats.name = "Channel " + std::to_string(chan_idx++);
    chan.sim_stats = new_stats;
    chan.warmup = warmup;
  }

  for (auto* ul : queues) {
    channel_type::stats_type ul_new_roi_stats;
    channel_type::stats_type ul_new_sim_stats;
    ul->roi_stats = ul_new_roi_stats;
    ul->sim_stats = ul_new_sim_stats;
  }
}

void DRAM_CHANNEL::begin_phase() {}

void MEMORY_CONTROLLER::end_phase(unsigned cpu)
{
  for (auto& chan : channels) {
    chan.end_phase(cpu);
  }
  
  // Print Error Page Statistics
  auto& error_manager = ErrorPageManager::get_instance();
  fmt::print("\n=== ERROR PAGE STATISTICS ===\n");
  fmt::print("Mode: ");
  if (error_manager.get_mode() == ErrorPageManagerMode::CYCLE) {
    fmt::print("CYCLE\n");
    fmt::print("Error Cycle Interval: {} CPU cycles\n", error_manager.get_error_cycle_interval());
  } else if (error_manager.get_mode() == ErrorPageManagerMode::RANDOM) {
    fmt::print("RANDOM (BER-based)\n");
    fmt::print("Bit Error Rate: {:.2e}\n", error_manager.get_bit_error_rate());
    fmt::print("Page Error Rate: {:.2e}\n", error_manager.get_page_error_rate());
  } else if (error_manager.get_mode() == ErrorPageManagerMode::ALL_ON) {
    fmt::print("ALL_ON\n");
  } else {
    fmt::print("OFF\n");
  }
  fmt::print("Total Error Accesses: {}\n", error_manager.get_total_error_count());
  fmt::print("==============================\n");
}

void DRAM_CHANNEL::end_phase(unsigned /*cpu*/) { roi_stats = sim_stats; }

bool DRAM_ADDRESS_MAPPING::is_collision(champsim::address a, champsim::address b) const
{
  // collision if everything but offset matches
  champsim::data::bits offset_bits = champsim::data::bits{champsim::size(get<SLICER_OFFSET_IDX>(address_slicer))};
  return (a.slice_upper(offset_bits) == b.slice_upper(offset_bits));
}

void DRAM_CHANNEL::check_write_collision()
{
  for (auto wq_it = std::begin(WQ); wq_it != std::end(WQ); ++wq_it) {
    if (wq_it->has_value() && !wq_it->value().forward_checked) {
      auto checker = [addr_map = address_mapping, check_val = wq_it->value().address](const auto& pkt) {
        return pkt.has_value() && addr_map.is_collision(pkt.value().address, check_val);
      };

      auto found = std::find_if(std::begin(WQ), wq_it, checker); // Forward check
      if (found == wq_it) {
        found = std::find_if(std::next(wq_it), std::end(WQ), checker); // Backward check
      }

      if (found != std::end(WQ)) {
        wq_it->reset();
      } else {
        wq_it->value().forward_checked = true;
      }
    }
  }
}

void DRAM_CHANNEL::check_read_collision()
{
  for (auto rq_it = std::begin(RQ); rq_it != std::end(RQ); ++rq_it) {
    if (rq_it->has_value() && !rq_it->value().forward_checked) {
      auto checker = [addr_map = address_mapping, check_val = rq_it->value().address](const auto& x) {
        return x.has_value() && addr_map.is_collision(x.value().address, check_val);
      };
      // write forward
      if (auto wq_it = std::find_if(std::begin(WQ), std::end(WQ), checker); wq_it != std::end(WQ)) {
        response_type response{rq_it->value().address, rq_it->value().v_address, wq_it->value().data, rq_it->value().pf_metadata,
                               rq_it->value().instr_depend_on_me};
        for (auto* ret : rq_it->value().to_return) {
          ret->push_back(response);
        }

        rq_it->reset();

      }
      // backwards check
      else if (auto found = std::find_if(std::begin(RQ), rq_it, checker); found != rq_it) {
        auto instr_copy = std::move(found->value().instr_depend_on_me);
        auto ret_copy = std::move(found->value().to_return);

        std::set_union(std::begin(instr_copy), std::end(instr_copy), std::begin(rq_it->value().instr_depend_on_me), std::end(rq_it->value().instr_depend_on_me),
                       std::back_inserter(found->value().instr_depend_on_me));
        std::set_union(std::begin(ret_copy), std::end(ret_copy), std::begin(rq_it->value().to_return), std::end(rq_it->value().to_return),
                       std::back_inserter(found->value().to_return));

        rq_it->reset();

      }
      // forwards check
      else if (found = std::find_if(std::next(rq_it), std::end(RQ), checker); found != std::end(RQ)) {
        auto instr_copy = std::move(found->value().instr_depend_on_me);
        auto ret_copy = std::move(found->value().to_return);

        std::set_union(std::begin(instr_copy), std::end(instr_copy), std::begin(rq_it->value().instr_depend_on_me), std::end(rq_it->value().instr_depend_on_me),
                       std::back_inserter(found->value().instr_depend_on_me));
        std::set_union(std::begin(ret_copy), std::end(ret_copy), std::begin(rq_it->value().to_return), std::end(rq_it->value().to_return),
                       std::back_inserter(found->value().to_return));

        rq_it->reset();
      } else {
        rq_it->value().forward_checked = true;
      }
    }
  }
}

void MEMORY_CONTROLLER::initiate_requests()
{
  // Initiate read requests
  for (auto* ul : queues) {
    for (auto q : {std::ref(ul->RQ), std::ref(ul->PQ)}) {
      auto [begin, end] = champsim::get_span_p(std::cbegin(q.get()), std::cend(q.get()), [ul, this](const auto& pkt) { return this->add_rq(pkt, ul); });
      q.get().erase(begin, end);
    }

    // Initiate write requests
    auto [wq_begin, wq_end] = champsim::get_span_p(std::cbegin(ul->WQ), std::cend(ul->WQ), [this](const auto& pkt) { return this->add_wq(pkt); });
    ul->WQ.erase(wq_begin, wq_end);
  }
}

DRAM_CHANNEL::request_type::request_type(const typename champsim::channel::request_type& req)
    : pf_metadata(req.pf_metadata), cpu(req.cpu), type(req.type), address(req.address), v_address(req.v_address), data(req.data), instr_depend_on_me(req.instr_depend_on_me)
{
  asid[0] = req.asid[0];
  asid[1] = req.asid[1];
}

champsim::chrono::clock::duration DRAM_CHANNEL::calculate_dynamic_error_latency(uint32_t cpu_num, champsim::address paddr,
                                                                                std::optional<champsim::address> vaddr_hint)
{
  if (debug_dynamic_error_latency) {
    fmt::print("[ERR_LAT] begin emulate_ptw cpu={} paddr=0x{:x} hint_vaddr={}\n",
               cpu_num, paddr.to<uint64_t>(), vaddr_hint.has_value() ? "yes" : "no");
  }

  // Check if references are available
  if (!vmem || ptws.empty() || caches.empty() || cpu_num >= ptws.size()) {
    // Fallback to fixed latency if references not available
    if (debug_dynamic_error_latency) {
      fmt::print("[ERR_LAT] fallback fixed latency (missing refs) = {} cycles\n",
                 to_cpu_cycles(ErrorPageManager::get_instance().get_error_latency()));
    }
    return ErrorPageManager::get_instance().get_error_latency();
  }

  champsim::page_number vpage{};
  const char* vaddr_source = "reverse-map";
  if (vaddr_hint.has_value()) {
    vpage = champsim::page_number{*vaddr_hint};
    vaddr_source = "hint";
  } else {
    // Get physical page number
    champsim::page_number ppage{paddr};

    // Reverse lookup: physical page → virtual page
    auto vpage_opt = vmem->get_vpage_for_ppage(cpu_num, ppage);
    if (!vpage_opt.has_value()) {
      // If no mapping found, use fixed latency
      if (debug_dynamic_error_latency) {
        fmt::print("[ERR_LAT] fallback fixed latency (reverse-map miss) = {} cycles\n",
                   to_cpu_cycles(ErrorPageManager::get_instance().get_error_latency()));
      }
      return ErrorPageManager::get_instance().get_error_latency();
    }
    vpage = vpage_opt.value();
  }

  champsim::address vaddr{vpage};
  PageTableWalker* ptw = ptws[cpu_num];
  if (debug_dynamic_error_latency) {
    fmt::print("[ERR_LAT] vaddr source={} vpage=0x{:x}\n", vaddr_source, vpage.to<uint64_t>());
  }

  // Check PSC to determine starting level
  std::size_t start_level = vmem->pt_levels;
  auto psc_level = ptw->get_psc_cached_level(vaddr);
  if (psc_level.has_value()) {
    // PSC hit: start from the cached level (skip higher levels)
    start_level = psc_level.value();
  }
  // Guard invalid PSC-derived levels.
  start_level = std::max<std::size_t>(1, std::min<std::size_t>(start_level, vmem->pt_levels));
  if (debug_dynamic_error_latency) {
    if (psc_level.has_value()) {
      fmt::print("[ERR_LAT] PSC hit -> start_level={} (pt_levels={})\n", start_level, vmem->pt_levels);
    } else {
      fmt::print("[ERR_LAT] PSC miss -> start_level={} (full walk, pt_levels={})\n", start_level, vmem->pt_levels);
    }
  }

  // Calculate latency for each page table level
  // Start from PSC-determined level down to level 1
  champsim::chrono::clock::duration total_latency = champsim::chrono::clock::duration::zero();
  auto cpu_period = ErrorPageManager::get_instance().get_cpu_clock_period();
  if (cpu_period.count() == 0) {
    cpu_period = clock_period;
  }
  const champsim::chrono::clock::duration DRAM_LATENCY = 200 * cpu_period;

  for (std::size_t level = start_level; level > 0; --level) {
    // Probe only existing PTE state. This latency model must not allocate new mappings.
    auto pte_paddr = vmem->get_pte_pa_if_present(cpu_num, vpage, level);
    if (!pte_paddr.has_value()) {
      total_latency += DRAM_LATENCY;
      if (debug_dynamic_error_latency) {
        fmt::print("[ERR_LAT] level {}: PTE unmapped -> DRAM (+200), total={} cycles\n", level, to_cpu_cycles(total_latency));
      }
      continue;
    }

    // Order-independent cache hierarchy check:
    // use the minimum hit latency among caches that currently contain the PTE line.
    champsim::chrono::clock::duration level_latency = DRAM_LATENCY;
    const char* hit_cache = nullptr;
    for (CACHE* cache : caches) {
      if (cache->is_address_in_cache(*pte_paddr)) {
        if (cache->HIT_LATENCY < level_latency) {
          level_latency = cache->HIT_LATENCY;
          hit_cache = cache->NAME.c_str();
        }
      }
    }

    total_latency += level_latency;
    if (debug_dynamic_error_latency) {
      if (hit_cache != nullptr) {
        fmt::print("[ERR_LAT] level {}: cache hit({}) +{} cycles, total={} cycles\n",
                   level, hit_cache, to_cpu_cycles(level_latency), to_cpu_cycles(total_latency));
      } else {
        fmt::print("[ERR_LAT] level {}: cache miss -> DRAM (+200), total={} cycles\n", level, to_cpu_cycles(total_latency));
      }
    }
  }

  if (debug_dynamic_error_latency) {
    fmt::print("[ERR_LAT] final dynamic error latency={} cycles\n", to_cpu_cycles(total_latency));
  }
  return total_latency;
}

bool MEMORY_CONTROLLER::add_rq(const request_type& packet, champsim::channel* ul)
{
  auto& channel = channels[address_mapping.get_channel(packet.address)];

  if (auto rq_it = std::find_if_not(std::begin(channel.RQ), std::end(channel.RQ), [this](const auto& pkt) { return pkt.has_value(); });
      rq_it != std::end(channel.RQ)) {
    *rq_it = DRAM_CHANNEL::request_type{packet};
    rq_it->value().forward_checked = false;
    rq_it->value().scheduled = false;
    rq_it->value().ready_time = current_time;
    if (packet.response_requested)
      rq_it->value().to_return = {&ul->returned};

    return true;
  }

  return false;
}

bool MEMORY_CONTROLLER::add_wq(const request_type& packet)
{
  auto& channel = channels[address_mapping.get_channel(packet.address)];

  // search for the empty index
  if (auto wq_it = std::find_if_not(std::begin(channel.WQ), std::end(channel.WQ), [](const auto& pkt) { return pkt.has_value(); });
      wq_it != std::end(channel.WQ)) {
    *wq_it = DRAM_CHANNEL::request_type{packet};
    wq_it->value().forward_checked = false;
    wq_it->value().scheduled = false;
    wq_it->value().ready_time = current_time;

    return true;
  }

  ++channel.sim_stats.WQ_FULL;
  return false;
}

unsigned long DRAM_ADDRESS_MAPPING::swizzle_bits(champsim::address address, unsigned long segment_size, champsim::data::bits segment_offset,
                                                 unsigned long field, unsigned long field_bits) const
{
  champsim::address_slice row{get<SLICER_ROW_IDX>(address_slicer), address};
  unsigned long permute_field = field;

  for (champsim::dynamic_extent subextent{champsim::data::bits{0}, segment_size}; subextent.upper <= row.upper_extent();
       subextent = champsim::dynamic_extent{subextent.upper, segment_size}) {
    permute_field ^= row.slice(subextent).slice(champsim::dynamic_extent{segment_offset, field_bits}).to<unsigned long>();
  }
  return permute_field;
}

unsigned long DRAM_ADDRESS_MAPPING::get_channel(champsim::address address) const
{
  unsigned long channel = std::get<SLICER_CHANNEL_IDX>(address_slicer(address)).to<unsigned long>();
  // channel bits should be xor'd with each row bit
  unsigned long c_bits = champsim::size(get<SLICER_CHANNEL_IDX>(address_slicer));
  return (swizzle_bits(address, 1, champsim::data::bits{0}, channel, c_bits));
}
unsigned long DRAM_ADDRESS_MAPPING::get_rank(champsim::address address) const { return std::get<SLICER_RANK_IDX>(address_slicer(address)).to<unsigned long>(); }
unsigned long DRAM_ADDRESS_MAPPING::get_bankgroup(champsim::address address) const
{
  unsigned long bankgroup = std::get<SLICER_BANKGROUP_IDX>(address_slicer(address)).to<unsigned long>();

  unsigned long bg_bits = champsim::size(get<SLICER_BANKGROUP_IDX>(address_slicer));
  unsigned long bk_bits = champsim::size(get<SLICER_BANK_IDX>(address_slicer));
  return (swizzle_bits(address, bg_bits + bk_bits, champsim::data::bits{0}, bankgroup, bg_bits));
}
unsigned long DRAM_ADDRESS_MAPPING::get_bank(champsim::address address) const
{
  unsigned long bank = std::get<SLICER_BANK_IDX>(address_slicer(address)).to<unsigned long>();

  unsigned long bg_bits = champsim::size(get<SLICER_BANKGROUP_IDX>(address_slicer));
  unsigned long bk_bits = champsim::size(get<SLICER_BANK_IDX>(address_slicer));
  // bank bits should be xor'd with select row bits

  return (swizzle_bits(address, bg_bits + bk_bits, champsim::data::bits{bg_bits}, bank, bk_bits));
}
unsigned long DRAM_ADDRESS_MAPPING::get_row(champsim::address address) const { return std::get<SLICER_ROW_IDX>(address_slicer(address)).to<unsigned long>(); }
unsigned long DRAM_ADDRESS_MAPPING::get_column(champsim::address address) const
{
  return std::get<SLICER_COLUMN_IDX>(address_slicer(address)).to<unsigned long>();
}

champsim::data::bytes MEMORY_CONTROLLER::size() const { return champsim::data::bytes{(1ll << address_mapping.address_slicer.bit_size())}; }
champsim::data::bytes DRAM_CHANNEL::density() const
{
  return champsim::data::bytes{(long long)(address_mapping.rows() * address_mapping.columns() * address_mapping.banks() * address_mapping.bankgroups())};
}

std::size_t DRAM_ADDRESS_MAPPING::rows() const { return std::size_t{1} << champsim::size(get<SLICER_ROW_IDX>(address_slicer)); }
std::size_t DRAM_ADDRESS_MAPPING::columns() const { return prefetch_size << champsim::size(get<SLICER_COLUMN_IDX>(address_slicer)); }
std::size_t DRAM_ADDRESS_MAPPING::ranks() const { return std::size_t{1} << champsim::size(get<SLICER_RANK_IDX>(address_slicer)); }
std::size_t DRAM_ADDRESS_MAPPING::bankgroups() const { return std::size_t{1} << champsim::size(get<SLICER_BANKGROUP_IDX>(address_slicer)); }
std::size_t DRAM_ADDRESS_MAPPING::banks() const { return std::size_t{1} << champsim::size(get<SLICER_BANK_IDX>(address_slicer)); }
std::size_t DRAM_ADDRESS_MAPPING::channels() const { return std::size_t{1} << champsim::size(get<SLICER_CHANNEL_IDX>(address_slicer)); }
std::size_t DRAM_CHANNEL::bank_request_capacity() const { return std::size(bank_request); }
std::size_t DRAM_CHANNEL::bankgroup_request_capacity() const { return std::size(bankgroup_readytime); };

// LCOV_EXCL_START Exclude the following function from LCOV
void MEMORY_CONTROLLER::print_deadlock()
{
  int j = 0;
  for (auto& chan : channels) {
    fmt::print("DRAM Channel {}\n", j++);
    chan.print_deadlock();
  }
}

void DRAM_CHANNEL::print_deadlock()
{
  std::string_view q_writer{"address: {} forward_checked: {} scheduled: {}"};
  auto q_entry_pack = [](const auto& entry) {
    return std::tuple{entry->address, entry->forward_checked, entry->scheduled};
  };

  champsim::range_print_deadlock(RQ, "RQ", q_writer, q_entry_pack);
  champsim::range_print_deadlock(WQ, "WQ", q_writer, q_entry_pack);
}
// LCOV_EXCL_STOP
