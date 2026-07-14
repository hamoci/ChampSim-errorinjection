#include <catch.hpp>

#include <algorithm>

#include "care_ecc_cache.h"

namespace
{
// Two lines in the same set of a 4-set cache: set index = (addr >> 6) & 3.
constexpr uint64_t line_in_set(std::size_t set, uint64_t salt = 0) { return ((salt * 4 + set) << 6); }
constexpr uint64_t PAGE_2MB = 1ULL << 21;
} // namespace

TEST_CASE("An untracked line is invisible to the CARE ECC cache")
{
  CareEccCache ecc{4, 2};

  auto rd = ecc.on_read(line_in_set(0));
  REQUIRE_FALSE(rd.tracked);
  REQUIRE_FALSE(rd.retire);
  REQUIRE_FALSE(ecc.on_write(line_in_set(0)));
  REQUIRE(ecc.occupancy() == 0);
  REQUIRE(ecc.stats().decode_reads == 0);
}

TEST_CASE("An error registers a line in S1 and reads keep it in S1")
{
  CareEccCache ecc{4, 2};
  const uint64_t line = line_in_set(1);

  REQUIRE(ecc.on_error(line) == CareEccCache::RegisterOutcome::REGISTERED);
  REQUIRE(ecc.is_tracked(line));
  REQUIRE(ecc.state_of(line) == CareEccCache::State::S1);
  REQUIRE(ecc.stats().registered == 1);

  for (int i = 0; i < 5; ++i) {
    auto rd = ecc.on_read(line);
    REQUIRE(rd.tracked);
    REQUIRE_FALSE(rd.retire);
  }
  REQUIRE(ecc.state_of(line) == CareEccCache::State::S1); // only a write confirms
  REQUIRE(ecc.stats().decode_reads == 5);
}

TEST_CASE("The full hard-error trajectory: error -> write -> read -> read retires")
{
  CareEccCache ecc{4, 2};
  const uint64_t line = line_in_set(2);

  REQUIRE(ecc.on_error(line) == CareEccCache::RegisterOutcome::REGISTERED);

  REQUIRE(ecc.on_write(line)); // S1 -> S2
  REQUIRE(ecc.state_of(line) == CareEccCache::State::S2);

  auto rd1 = ecc.on_read(line); // S2 -> S3 (hard error re-detected)
  REQUIRE(rd1.tracked);
  REQUIRE(rd1.promoted_s3);
  REQUIRE_FALSE(rd1.retire);
  REQUIRE(ecc.state_of(line) == CareEccCache::State::S3);

  auto rd2 = ecc.on_read(line); // S3 read -> retire signal
  REQUIRE(rd2.tracked);
  REQUIRE(rd2.retire);
  REQUIRE(ecc.stats().retires == 1);
}

TEST_CASE("Writes in S2 and S3 are no-ops")
{
  CareEccCache ecc{4, 2};
  const uint64_t line = line_in_set(3);

  ecc.on_error(line);
  ecc.on_write(line); // S1 -> S2
  REQUIRE_FALSE(ecc.on_write(line));
  REQUIRE(ecc.state_of(line) == CareEccCache::State::S2);

  ecc.on_read(line); // S2 -> S3
  REQUIRE_FALSE(ecc.on_write(line));
  REQUIRE(ecc.state_of(line) == CareEccCache::State::S3);
  REQUIRE(ecc.stats().writes_s1_to_s2 == 1);
}

TEST_CASE("An injected error on a tracked line changes nothing but the stat")
{
  CareEccCache ecc{4, 2};
  const uint64_t line = line_in_set(0);

  ecc.on_error(line);
  ecc.on_write(line); // S2

  REQUIRE(ecc.on_error(line) == CareEccCache::RegisterOutcome::ALREADY_TRACKED);
  REQUIRE(ecc.state_of(line) == CareEccCache::State::S2);
  REQUIRE(ecc.stats().registered == 1);
  REQUIRE(ecc.stats().errors_on_tracked == 1);
}

TEST_CASE("Pseudocode 1 degenerates to insert-only-on-free-way under single-error registration")
{
  CareEccCache ecc{4, 2};

  // Fill both ways of set 0.
  REQUIRE(ecc.on_error(line_in_set(0, 0)) == CareEccCache::RegisterOutcome::REGISTERED);
  REQUIRE(ecc.on_error(line_in_set(0, 1)) == CareEccCache::RegisterOutcome::REGISTERED);
  REQUIRE(ecc.occupancy() == 2);

  // Newcomer (err_count 1) never beats residents (err_count >= 1): dropped.
  REQUIRE(ecc.on_error(line_in_set(0, 2)) == CareEccCache::RegisterOutcome::DROPPED);
  REQUIRE(ecc.stats().dropped == 1);
  REQUIRE_FALSE(ecc.is_tracked(line_in_set(0, 2)));

  // Residents with grown counts are even safer.
  ecc.on_read(line_in_set(0, 0));
  REQUIRE(ecc.on_error(line_in_set(0, 3)) == CareEccCache::RegisterOutcome::DROPPED);
  REQUIRE(ecc.stats().dropped == 2);

  // A different set is unaffected.
  REQUIRE(ecc.on_error(line_in_set(1, 0)) == CareEccCache::RegisterOutcome::REGISTERED);
}

TEST_CASE("An S3 entry in the set blocks replacement but not free-way insertion")
{
  CareEccCache ecc{4, 2};
  const uint64_t s3_line = line_in_set(0, 0);

  // Drive one entry to S3.
  ecc.on_error(s3_line);
  ecc.on_write(s3_line); // S1 -> S2
  ecc.on_read(s3_line);  // S2 -> S3
  REQUIRE(ecc.state_of(s3_line) == CareEccCache::State::S3);

  // A free way in the same set still accepts a newcomer.
  REQUIRE(ecc.on_error(line_in_set(0, 1)) == CareEccCache::RegisterOutcome::REGISTERED);

  // Set now full with an S3 present: Pseudocode 1 forbids replacement, and the
  // S3 entry pending retirement must survive untouched.
  REQUIRE(ecc.on_error(line_in_set(0, 2)) == CareEccCache::RegisterOutcome::DROPPED);
  REQUIRE(ecc.is_tracked(s3_line));
  REQUIRE(ecc.state_of(s3_line) == CareEccCache::State::S3);
}

TEST_CASE("Page retirement invalidates every entry of the page and frees ways")
{
  CareEccCache ecc{4, 2};

  // Two lines of page 0 land in different sets; one line of page 1 shares set 0.
  const uint64_t page0_a = line_in_set(0, 0);
  const uint64_t page0_b = line_in_set(1, 0);
  const uint64_t page1_a = PAGE_2MB + line_in_set(0, 0);

  ecc.on_error(page0_a);
  ecc.on_error(page0_b);
  ecc.on_error(page1_a);
  REQUIRE(ecc.occupancy() == 3);

  REQUIRE(ecc.invalidate_page(0) == 2);
  REQUIRE_FALSE(ecc.is_tracked(page0_a));
  REQUIRE_FALSE(ecc.is_tracked(page0_b));
  REQUIRE(ecc.is_tracked(page1_a));
  REQUIRE(ecc.stats().invalidated_entries == 2);

  // Freed way accepts a fresh registration (retire-then-reinject artifact, D5).
  REQUIRE(ecc.on_error(page0_a) == CareEccCache::RegisterOutcome::REGISTERED);
  REQUIRE(ecc.state_of(page0_a) == CareEccCache::State::S1);
}

TEST_CASE("The error count saturates instead of wrapping")
{
  CareEccCache ecc{4, 2};
  const uint64_t line = line_in_set(0);

  ecc.on_error(line);
  for (int i = 0; i < 300; ++i)
    ecc.on_read(line);
  // 300 reads in S1: no retirement without the write confirmation, no wrap crash.
  REQUIRE(ecc.state_of(line) == CareEccCache::State::S1);
  REQUIRE(ecc.stats().decode_reads == 300);
}

TEST_CASE("Set indexing separates lines by address bits 6.. and honors geometry")
{
  CareEccCache ecc{2, 1}; // 2 sets x 1 way

  const uint64_t set0 = 0x0;  // (0x0 >> 6) & 1 == 0
  const uint64_t set1 = 0x40; // (0x40 >> 6) & 1 == 1

  REQUIRE(ecc.on_error(set0) == CareEccCache::RegisterOutcome::REGISTERED);
  REQUIRE(ecc.on_error(set1) == CareEccCache::RegisterOutcome::REGISTERED);      // different set: fits despite 1 way
  REQUIRE(ecc.on_error(0x80) == CareEccCache::RegisterOutcome::DROPPED); // maps back to set 0: full, dropped
  REQUIRE(ecc.num_sets() == 2);
  REQUIRE(ecc.num_ways() == 1);
  REQUIRE(ecc.occupancy() == 2);
}

namespace
{
// Drive one full hard-fault confirmation sequence to retirement:
// error(register, S1) -> write(S2) -> read(S3) -> read(retire).
// err_count at retirement = 3, so each retirement contributes exactly
// LOCAL_CONTRIB_CAP (3) to its bank's global counter.
CareEccCache::ReadOutcome retire_sequence(CareEccCache& ecc, uint64_t line, uint8_t bank)
{
  REQUIRE(ecc.on_error(line, bank) == CareEccCache::RegisterOutcome::REGISTERED);
  REQUIRE(ecc.on_write(line));
  REQUIRE(ecc.on_read(line).promoted_s3);
  return ecc.on_read(line);
}
} // namespace

TEST_CASE("Proactive: five same-bank retirements saturate and trigger; counters reset")
{
  CareEccCache ecc{1, 8, /*proactive_enabled=*/true};

  for (int i = 0; i < 4; ++i) {
    auto out = retire_sequence(ecc, line_in_set(0, i), /*bank=*/0);
    REQUIRE(out.retire);
    REQUIRE_FALSE(out.proactive); // counter at 3*(i+1) <= 12 < 15
    ecc.invalidate_page(line_in_set(0, i) & CareEccCache::PAGE_BASE_MASK);
  }
  REQUIRE(ecc.global_counter(0, 0) == 12);

  auto out = retire_sequence(ecc, line_in_set(0, 4), /*bank=*/0);
  REQUIRE(out.retire);
  REQUIRE(out.proactive); // counter saturates at 15; bias 15-0 >= 12
  REQUIRE(ecc.stats().proactive_triggers == 1);
  REQUIRE(ecc.global_counter(0, 0) == 0); // round closed: counters reset
  REQUIRE(ecc.stats().gc_resets == 1);
  REQUIRE(ecc.stats().gc_peak_value == 15);
  REQUIRE(ecc.stats().gc_peak_bias == 15);
}

TEST_CASE("Proactive: per-retirement contribution is capped at the 2-bit local maximum")
{
  CareEccCache ecc{1, 8, /*proactive_enabled=*/true};
  const uint64_t line = line_in_set(0);

  REQUIRE(ecc.on_error(line, /*bank=*/2) == CareEccCache::RegisterOutcome::REGISTERED);
  for (int i = 0; i < 10; ++i)
    ecc.on_read(line); // S1 reads inflate err_count well past the cap
  REQUIRE(ecc.on_write(line));
  REQUIRE(ecc.on_read(line).promoted_s3);
  auto out = ecc.on_read(line);
  REQUIRE(out.retire);
  REQUIRE_FALSE(out.proactive);
  REQUIRE(ecc.global_counter(0, 2) == CareEccCache::LOCAL_CONTRIB_CAP); // 3, not 13
}

TEST_CASE("Proactive disabled: retirements leave global counters untouched")
{
  CareEccCache ecc{1, 8}; // default: proactive off

  auto out = retire_sequence(ecc, line_in_set(0), /*bank=*/0);
  REQUIRE(out.retire);
  REQUIRE_FALSE(out.proactive);
  REQUIRE(ecc.global_counter(0, 0) == 0);
  REQUIRE(ecc.stats().gc_accumulations == 0);
}

TEST_CASE("Proactive victim list: distinct resident pages of the triggering set")
{
  CareEccCache ecc{1, 8, /*proactive_enabled=*/true};
  const uint64_t page_a = 0;          // lines below both fall in this 2MB page
  const uint64_t page_b = PAGE_2MB;

  REQUIRE(ecc.on_error(line_in_set(0, 0), 0) == CareEccCache::RegisterOutcome::REGISTERED);
  REQUIRE(ecc.on_error(line_in_set(0, 1), 1) == CareEccCache::RegisterOutcome::REGISTERED);
  REQUIRE(ecc.on_error(PAGE_2MB + line_in_set(0, 0), 2) == CareEccCache::RegisterOutcome::REGISTERED);

  auto pages = ecc.set_resident_pages(line_in_set(0, 0));
  REQUIRE(pages.size() == 2);
  REQUIRE(std::find(pages.begin(), pages.end(), page_a) != pages.end());
  REQUIRE(std::find(pages.begin(), pages.end(), page_b) != pages.end());
}

TEST_CASE("Proactive OR variant: four same-bank retirements trigger via bias alone")
{
  CareEccCache ecc{1, 8, /*proactive_enabled=*/true, /*or_trigger=*/true};

  for (int i = 0; i < 3; ++i) {
    auto out = retire_sequence(ecc, line_in_set(0, i), /*bank=*/0);
    REQUIRE(out.retire);
    REQUIRE_FALSE(out.proactive); // counter at 3*(i+1) <= 9 < 12
    ecc.invalidate_page(line_in_set(0, i) & CareEccCache::PAGE_BASE_MASK);
  }
  REQUIRE(ecc.global_counter(0, 0) == 9);

  auto out = retire_sequence(ecc, line_in_set(0, 3), /*bank=*/0);
  REQUIRE(out.retire);
  REQUIRE(out.proactive); // 12: bias 12-0 >= 12 fires without saturation (OR)
  REQUIRE(ecc.stats().proactive_triggers == 1);
  REQUIRE(ecc.global_counter(0, 0) == 0); // trigger closes the round
}

TEST_CASE("Proactive AND default: bias at 12 without saturation does not trigger")
{
  CareEccCache ecc{1, 8, /*proactive_enabled=*/true}; // paper AND condition

  for (int i = 0; i < 4; ++i) {
    auto out = retire_sequence(ecc, line_in_set(0, i), /*bank=*/0);
    REQUIRE_FALSE(out.proactive);
    ecc.invalidate_page(line_in_set(0, i) & CareEccCache::PAGE_BASE_MASK);
  }
  REQUIRE(ecc.global_counter(0, 0) == 12); // biased but not saturated: no trigger, no reset
}
