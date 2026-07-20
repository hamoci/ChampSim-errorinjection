#include "care_ecc_cache.h"

#include <algorithm>
#include <cassert>
#include <iterator>

CareEccCache::CareEccCache(std::size_t num_sets, std::size_t num_ways, bool proactive_enabled, bool or_trigger)
    : sets_(num_sets), ways_(num_ways), proactive_enabled_(proactive_enabled), or_trigger_(or_trigger), entries_(num_sets * num_ways),
      gcounters_(num_sets), observed_pages_(num_sets)
{
  assert(sets_ > 0 && (sets_ & (sets_ - 1)) == 0); // power of two (paper 10-bit index layout)
  assert(ways_ > 0);
}

CareEccCache::Entry* CareEccCache::find(uint64_t line_addr, std::size_t set)
{
  for (std::size_t w = 0; w < ways_; ++w) {
    auto& e = entries_[set * ways_ + w];
    if (e.valid && e.line_addr == line_addr)
      return &e;
  }
  return nullptr;
}

const CareEccCache::Entry* CareEccCache::find(uint64_t line_addr, std::size_t set) const
{
  return const_cast<CareEccCache*>(this)->find(line_addr, set);
}

CareEccCache::ReadOutcome CareEccCache::on_read(uint64_t line_addr, std::size_t set)
{
  ReadOutcome out{};
  Entry* e = find(line_addr, set);
  if (e == nullptr)
    return out;

  out.tracked = true;
  stats_.decode_reads++;
  if (e->err_count < ERR_COUNT_CAP)
    e->err_count++; // hard fault: every read of a tracked block re-detects the error

  switch (e->state) {
  case State::S1:
    break; // reads keep augmented protection; only a write confirms (S1->S2)
  case State::S2:
    e->state = State::S3;
    out.promoted_s3 = true;
    stats_.reads_s2_to_s3++;
    break;
  case State::S3:
    out.retire = true; // caller retires the page, then invalidate_page() drops this entry
    out.entry_chip = e->chip_idx;
    out.entry_err_count = e->err_count;
    stats_.retires++;
    if (proactive_enabled_)
      account_retirement(set, *e, out);
    break;
  }
  return out;
}

// Paper Section III.C: at each (reactive) retirement the block's local error
// counters accumulate into the set's global counters; when some counter
// saturates, a max-min bias >= 12 means the confirmed hard errors concentrate
// on one bank/chip -> proactive retirement of everything the set protects.
// Saturation without bias closes the accounting round (counters reset).
void CareEccCache::account_retirement(std::size_t set, const Entry& e, ReadOutcome& out)
{
  auto& gc = gcounters_[set];
  uint32_t contrib = std::min(e.err_count, LOCAL_CONTRIB_CAP);
  gc[e.chip_idx] = static_cast<uint8_t>(std::min<uint32_t>(GLOBAL_COUNTER_MAX, gc[e.chip_idx] + contrib));
  stats_.gc_accumulations++;

  auto [min_it, max_it] = std::minmax_element(gc.begin(), gc.end());
  uint8_t bias = static_cast<uint8_t>(*max_it - *min_it);
  stats_.gc_peak_value = std::max(stats_.gc_peak_value, *max_it);
  stats_.gc_peak_bias = std::max(stats_.gc_peak_bias, bias);

  bool saturated = *max_it >= GLOBAL_COUNTER_MAX;
  bool biased = bias >= PROACTIVE_BIAS_MIN;
  // Paper condition: saturated AND biased. Exploratory OR variant fires on
  // either signal alone (effectively lowering the same-counter requirement
  // from 5 to 4 retirements when the set's minimum counter is 0).
  bool triggered = or_trigger_ ? (saturated || biased) : (saturated && biased);

  if (!triggered && !saturated)
    return; // round still accumulating

  if (triggered) {
    stats_.proactive_triggers++;
    out.proactive = true;
    out.biased_chip = static_cast<uint8_t>(std::distance(gc.begin(), max_it));
    out.bias = bias;
  }
  gc.fill(0); // trigger, or saturation without bias: close the accounting round
  stats_.gc_resets++;
}

std::vector<uint64_t> CareEccCache::region_error_pages(std::size_t set) const
{
  // Registered blocks always insert into observed_pages_ first, so the
  // observed list is a superset of the resident entries' pages.
  std::vector<uint64_t> pages(observed_pages_[set].begin(), observed_pages_[set].end());
  std::sort(pages.begin(), pages.end()); // deterministic retirement order
  return pages;
}

bool CareEccCache::on_write(uint64_t line_addr, std::size_t set)
{
  Entry* e = find(line_addr, set);
  if (e == nullptr || e->state != State::S1)
    return false;

  e->state = State::S2;
  stats_.writes_s1_to_s2++;
  return true;
}

// Paper Pseudocode 1 (verified against CARE HPCA'21 Fig 2 / Pseudocode 1).
// - Any S3 block in the set -> no replacement (it retires on the next read and
//   frees its own way).
// - Otherwise replace the minimum-err_count block ONLY if that minimum is below
//   the newcomer's total error count Err(new); ties prefer the unique block in
//   state <= S1, else lowest index (deterministic stand-in for the paper's random
//   pick — see header).
//
// Err(new) is the newcomer's total error count over the 8 byte-column counters
// (paper Fig 2). It exceeds a resident's minimum only for MULTI-column errors
// (multiple chips bad in one line = multi-bank/rank faults, excluded here as UE).
// Our single-chip fault model produces single-column errors, so Err(new)=1 and
// this degenerates to insert-into-free-way-or-drop — exactly the paper's behavior
// for single-chip faults. Under realistic (sparse, R1Y-scale) intensity the 2-way
// set rarely fills (paper contention analysis, Fig 4a), so this is not a throughput
// limiter; it only bottlenecks under accelerated over-injection.
CareEccCache::Entry* CareEccCache::pick_victim(std::size_t set)
{
  constexpr uint32_t err_new = 1;

  Entry* base = &entries_[set * ways_];
  for (std::size_t w = 0; w < ways_; ++w) {
    if (base[w].valid && base[w].state == State::S3)
      return nullptr;
  }

  uint32_t err_min = ERR_COUNT_CAP + 1;
  for (std::size_t w = 0; w < ways_; ++w)
    err_min = std::min(err_min, base[w].err_count);

  if (err_min >= err_new)
    return nullptr;

  Entry* only_min = nullptr;
  std::size_t min_count = 0;
  for (std::size_t w = 0; w < ways_; ++w) {
    if (base[w].err_count == err_min) {
      min_count++;
      if (only_min == nullptr)
        only_min = &base[w];
    }
  }
  if (min_count == 1)
    return only_min;

  Entry* only_low_state = nullptr;
  std::size_t low_state_count = 0;
  for (std::size_t w = 0; w < ways_; ++w) {
    if (base[w].err_count == err_min && base[w].state == State::S1) {
      low_state_count++;
      if (only_low_state == nullptr)
        only_low_state = &base[w];
    }
  }
  if (low_state_count == 1)
    return only_low_state;

  return only_min; // lowest-index deterministic tie-break
}

CareEccCache::RegisterOutcome CareEccCache::on_error(uint64_t line_addr, std::size_t set, uint8_t chip)
{
  // Evidence for the proactive victim list: any observed error in this
  // region marks the page, whether or not the block wins an ECC entry.
  observed_pages_[set].insert(line_addr & PAGE_BASE_MASK);

  if (Entry* e = find(line_addr, set); e != nullptr) {
    stats_.errors_on_tracked++; // already faulty: no state/count change (D3)
    return RegisterOutcome::ALREADY_TRACKED;
  }

  Entry* slot = nullptr;
  for (std::size_t w = 0; w < ways_; ++w) {
    auto& e = entries_[set * ways_ + w];
    if (!e.valid) {
      slot = &e;
      break;
    }
  }
  if (slot == nullptr)
    slot = pick_victim(set);

  if (slot == nullptr) {
    stats_.dropped++;
    return RegisterOutcome::DROPPED;
  }

  *slot = Entry{line_addr, 1, State::S1, true, static_cast<uint8_t>(chip % NUM_GLOBAL_COUNTERS)};
  stats_.registered++;
  return RegisterOutcome::REGISTERED;
}

std::size_t CareEccCache::invalidate_page(uint64_t page_base)
{
  for (auto& op : observed_pages_) {
    op.erase(page_base);
  }
  std::size_t removed = 0;
  for (auto& e : entries_) {
    if (e.valid && (e.line_addr & PAGE_BASE_MASK) == page_base) {
      e = Entry{};
      removed++;
    }
  }
  stats_.invalidated_entries += removed;
  return removed;
}

bool CareEccCache::is_tracked(uint64_t line_addr, std::size_t set) const { return find(line_addr, set) != nullptr; }

CareEccCache::State CareEccCache::state_of(uint64_t line_addr, std::size_t set) const
{
  const Entry* e = find(line_addr, set);
  assert(e != nullptr);
  return e->state;
}

std::size_t CareEccCache::occupancy() const
{
  return static_cast<std::size_t>(std::count_if(entries_.begin(), entries_.end(), [](const Entry& e) { return e.valid; }));
}
