#include "care_ecc_cache.h"

#include <algorithm>
#include <cassert>

CareEccCache::CareEccCache(std::size_t num_sets, std::size_t num_ways) : sets_(num_sets), ways_(num_ways), entries_(num_sets * num_ways)
{
  assert(sets_ > 0 && (sets_ & (sets_ - 1)) == 0); // power of two (set_index masking)
  assert(ways_ > 0);
}

CareEccCache::Entry* CareEccCache::find(uint64_t line_addr)
{
  auto set = set_index(line_addr);
  for (std::size_t w = 0; w < ways_; ++w) {
    auto& e = entries_[set * ways_ + w];
    if (e.valid && e.line_addr == line_addr)
      return &e;
  }
  return nullptr;
}

const CareEccCache::Entry* CareEccCache::find(uint64_t line_addr) const { return const_cast<CareEccCache*>(this)->find(line_addr); }

CareEccCache::ReadOutcome CareEccCache::on_read(uint64_t line_addr)
{
  ReadOutcome out{};
  Entry* e = find(line_addr);
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
    stats_.retires++;
    break;
  }
  return out;
}

bool CareEccCache::on_write(uint64_t line_addr)
{
  Entry* e = find(line_addr);
  if (e == nullptr || e->state != State::S1)
    return false;

  e->state = State::S2;
  stats_.writes_s1_to_s2++;
  return true;
}

// Paper Pseudocode 1. New block arrives with err_count 1.
// - Any S3 block in the set -> no replacement (its page retires soon, freeing a way).
// - Otherwise replace only if the minimum resident error count is below the
//   newcomer's; ties prefer the unique block in state <= S1, else lowest index
//   (deterministic stand-in for the paper's random pick — see header).
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

CareEccCache::RegisterOutcome CareEccCache::on_error(uint64_t line_addr)
{
  if (Entry* e = find(line_addr); e != nullptr) {
    stats_.errors_on_tracked++; // already faulty: no state/count change (D3)
    return RegisterOutcome::ALREADY_TRACKED;
  }

  auto set = set_index(line_addr);
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

  *slot = Entry{line_addr, 1, State::S1, true};
  stats_.registered++;
  return RegisterOutcome::REGISTERED;
}

std::size_t CareEccCache::invalidate_page(uint64_t page_base)
{
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

bool CareEccCache::is_tracked(uint64_t line_addr) const { return find(line_addr) != nullptr; }

CareEccCache::State CareEccCache::state_of(uint64_t line_addr) const
{
  const Entry* e = find(line_addr);
  assert(e != nullptr);
  return e->state;
}

std::size_t CareEccCache::occupancy() const
{
  return static_cast<std::size_t>(std::count_if(entries_.begin(), entries_.end(), [](const Entry& e) { return e.valid; }));
}
