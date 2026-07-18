#include <catch.hpp>

#include <algorithm>

#include "care_ecc_cache.h"

namespace
{
// Distinct 64B-aligned line addresses. The set is no longer derived from the
// address (paper III.B.3: the caller composes it from DRAM coordinates), so
// tests pass the set explicitly; the salt only makes tags unique.
constexpr uint64_t line_tag(uint64_t salt) { return salt << 6; }
constexpr uint64_t PAGE_2MB = 1ULL << 21;
} // namespace

TEST_CASE("An untracked line is invisible to the CARE ECC cache")
{
  CareEccCache ecc{4, 2};

  auto rd = ecc.on_read(line_tag(0), 0);
  REQUIRE_FALSE(rd.tracked);
  REQUIRE_FALSE(rd.retire);
  REQUIRE_FALSE(ecc.on_write(line_tag(0), 0));
  REQUIRE(ecc.occupancy() == 0);
  REQUIRE(ecc.stats().decode_reads == 0);
}

TEST_CASE("An error registers a line in S1 and reads keep it in S1")
{
  CareEccCache ecc{4, 2};
  const uint64_t line = line_tag(1);
  const std::size_t set = 1;

  REQUIRE(ecc.on_error(line, set) == CareEccCache::RegisterOutcome::REGISTERED);
  REQUIRE(ecc.is_tracked(line, set));
  REQUIRE(ecc.state_of(line, set) == CareEccCache::State::S1);
  REQUIRE(ecc.stats().registered == 1);

  for (int i = 0; i < 5; ++i) {
    auto rd = ecc.on_read(line, set);
    REQUIRE(rd.tracked);
    REQUIRE_FALSE(rd.retire);
  }
  REQUIRE(ecc.state_of(line, set) == CareEccCache::State::S1); // only a write confirms
  REQUIRE(ecc.stats().decode_reads == 5);
}

TEST_CASE("The full hard-error trajectory: error -> write -> read -> read retires")
{
  CareEccCache ecc{4, 2};
  const uint64_t line = line_tag(2);
  const std::size_t set = 2;

  REQUIRE(ecc.on_error(line, set) == CareEccCache::RegisterOutcome::REGISTERED);

  REQUIRE(ecc.on_write(line, set)); // S1 -> S2
  REQUIRE(ecc.state_of(line, set) == CareEccCache::State::S2);

  auto rd1 = ecc.on_read(line, set); // S2 -> S3 (hard error re-detected)
  REQUIRE(rd1.tracked);
  REQUIRE(rd1.promoted_s3);
  REQUIRE_FALSE(rd1.retire);
  REQUIRE(ecc.state_of(line, set) == CareEccCache::State::S3);

  auto rd2 = ecc.on_read(line, set); // S3 read -> retire signal
  REQUIRE(rd2.tracked);
  REQUIRE(rd2.retire);
  REQUIRE(ecc.stats().retires == 1);
}

TEST_CASE("Writes in S2 and S3 are no-ops")
{
  CareEccCache ecc{4, 2};
  const uint64_t line = line_tag(3);
  const std::size_t set = 3;

  ecc.on_error(line, set);
  ecc.on_write(line, set); // S1 -> S2
  REQUIRE_FALSE(ecc.on_write(line, set));
  REQUIRE(ecc.state_of(line, set) == CareEccCache::State::S2);

  ecc.on_read(line, set); // S2 -> S3
  REQUIRE_FALSE(ecc.on_write(line, set));
  REQUIRE(ecc.state_of(line, set) == CareEccCache::State::S3);
  REQUIRE(ecc.stats().writes_s1_to_s2 == 1);
}

TEST_CASE("An injected error on a tracked line changes nothing but the stat")
{
  CareEccCache ecc{4, 2};
  const uint64_t line = line_tag(4);
  const std::size_t set = 0;

  ecc.on_error(line, set);
  ecc.on_write(line, set); // S2

  REQUIRE(ecc.on_error(line, set) == CareEccCache::RegisterOutcome::ALREADY_TRACKED);
  REQUIRE(ecc.state_of(line, set) == CareEccCache::State::S2);
  REQUIRE(ecc.stats().registered == 1);
  REQUIRE(ecc.stats().errors_on_tracked == 1);
}

TEST_CASE("Pseudocode 1 degenerates to insert-only-on-free-way under single-error registration")
{
  CareEccCache ecc{4, 2};

  // Fill both ways of set 0.
  REQUIRE(ecc.on_error(line_tag(10), 0) == CareEccCache::RegisterOutcome::REGISTERED);
  REQUIRE(ecc.on_error(line_tag(11), 0) == CareEccCache::RegisterOutcome::REGISTERED);
  REQUIRE(ecc.occupancy() == 2);

  // Newcomer (err_count 1) never beats residents (err_count >= 1): dropped.
  REQUIRE(ecc.on_error(line_tag(12), 0) == CareEccCache::RegisterOutcome::DROPPED);
  REQUIRE(ecc.stats().dropped == 1);
  REQUIRE_FALSE(ecc.is_tracked(line_tag(12), 0));

  // Residents with grown counts are even safer.
  ecc.on_read(line_tag(10), 0);
  REQUIRE(ecc.on_error(line_tag(13), 0) == CareEccCache::RegisterOutcome::DROPPED);
  REQUIRE(ecc.stats().dropped == 2);

  // A different set is unaffected.
  REQUIRE(ecc.on_error(line_tag(14), 1) == CareEccCache::RegisterOutcome::REGISTERED);
}

TEST_CASE("An S3 entry in the set blocks replacement but not free-way insertion")
{
  CareEccCache ecc{4, 2};
  const uint64_t s3_line = line_tag(20);
  const std::size_t set = 0;

  // Drive one entry to S3.
  ecc.on_error(s3_line, set);
  ecc.on_write(s3_line, set); // S1 -> S2
  ecc.on_read(s3_line, set);  // S2 -> S3
  REQUIRE(ecc.state_of(s3_line, set) == CareEccCache::State::S3);

  // A free way in the same set still accepts a newcomer.
  REQUIRE(ecc.on_error(line_tag(21), set) == CareEccCache::RegisterOutcome::REGISTERED);

  // Set now full with an S3 present: Pseudocode 1 forbids replacement, and the
  // S3 entry pending retirement must survive untouched.
  REQUIRE(ecc.on_error(line_tag(22), set) == CareEccCache::RegisterOutcome::DROPPED);
  REQUIRE(ecc.is_tracked(s3_line, set));
  REQUIRE(ecc.state_of(s3_line, set) == CareEccCache::State::S3);
}

TEST_CASE("Page retirement invalidates every entry of the page and frees ways")
{
  CareEccCache ecc{4, 2};

  // Two lines of page 0 land in different sets; one line of page 1 shares set 0.
  const uint64_t page0_a = line_tag(30);
  const uint64_t page0_b = line_tag(31);
  const uint64_t page1_a = PAGE_2MB + line_tag(30);

  ecc.on_error(page0_a, 0);
  ecc.on_error(page0_b, 1);
  ecc.on_error(page1_a, 0);
  REQUIRE(ecc.occupancy() == 3);

  REQUIRE(ecc.invalidate_page(0) == 2);
  REQUIRE_FALSE(ecc.is_tracked(page0_a, 0));
  REQUIRE_FALSE(ecc.is_tracked(page0_b, 1));
  REQUIRE(ecc.is_tracked(page1_a, 0));
  REQUIRE(ecc.stats().invalidated_entries == 2);

  // Freed way accepts a fresh registration (retire-then-reinject artifact, D5).
  REQUIRE(ecc.on_error(page0_a, 0) == CareEccCache::RegisterOutcome::REGISTERED);
  REQUIRE(ecc.state_of(page0_a, 0) == CareEccCache::State::S1);
}

TEST_CASE("The error count saturates instead of wrapping")
{
  CareEccCache ecc{4, 2};
  const uint64_t line = line_tag(40);
  const std::size_t set = 0;

  ecc.on_error(line, set);
  for (int i = 0; i < 300; ++i)
    ecc.on_read(line, set);
  // 300 reads in S1: no retirement without the write confirmation, no wrap crash.
  REQUIRE(ecc.state_of(line, set) == CareEccCache::State::S1);
  REQUIRE(ecc.stats().decode_reads == 300);
}

TEST_CASE("Explicit set indexing separates identical-capacity sets")
{
  CareEccCache ecc{2, 1}; // 2 sets x 1 way

  REQUIRE(ecc.on_error(line_tag(50), 0) == CareEccCache::RegisterOutcome::REGISTERED);
  REQUIRE(ecc.on_error(line_tag(51), 1) == CareEccCache::RegisterOutcome::REGISTERED); // different set: fits despite 1 way
  REQUIRE(ecc.on_error(line_tag(52), 0) == CareEccCache::RegisterOutcome::DROPPED);    // set 0 full, dropped
  REQUIRE(ecc.num_sets() == 2);
  REQUIRE(ecc.num_ways() == 1);
  REQUIRE(ecc.occupancy() == 2);
}

namespace
{
// Drive one full hard-fault confirmation sequence to retirement:
// error(register, S1) -> write(S2) -> read(S3) -> read(retire).
// err_count at retirement = 3, so each retirement contributes exactly
// LOCAL_CONTRIB_CAP (3) to its chip's global counter.
CareEccCache::ReadOutcome retire_sequence(CareEccCache& ecc, uint64_t line, std::size_t set, uint8_t chip)
{
  REQUIRE(ecc.on_error(line, set, chip) == CareEccCache::RegisterOutcome::REGISTERED);
  REQUIRE(ecc.on_write(line, set));
  REQUIRE(ecc.on_read(line, set).promoted_s3);
  return ecc.on_read(line, set);
}
} // namespace

TEST_CASE("Proactive: five same-chip retirements saturate and trigger; counters reset")
{
  CareEccCache ecc{1, 8, /*proactive_enabled=*/true};

  for (int i = 0; i < 4; ++i) {
    auto out = retire_sequence(ecc, line_tag(60 + i), 0, /*chip=*/0);
    REQUIRE(out.retire);
    REQUIRE_FALSE(out.proactive); // counter at 3*(i+1) <= 12 < 15
    ecc.invalidate_page(line_tag(60 + i) & CareEccCache::PAGE_BASE_MASK);
  }
  REQUIRE(ecc.global_counter(0, 0) == 12);

  auto out = retire_sequence(ecc, line_tag(64), 0, /*chip=*/0);
  REQUIRE(out.retire);
  REQUIRE(out.proactive); // counter saturates at 15; bias 15-0 >= 12
  REQUIRE(out.biased_chip == 0);
  REQUIRE(out.bias == 15);
  REQUIRE(ecc.stats().proactive_triggers == 1);
  REQUIRE(ecc.global_counter(0, 0) == 0); // round closed: counters reset
  REQUIRE(ecc.stats().gc_resets == 1);
  REQUIRE(ecc.stats().gc_peak_value == 15);
  REQUIRE(ecc.stats().gc_peak_bias == 15);
}

TEST_CASE("Proactive: per-retirement contribution is capped at the 2-bit local maximum")
{
  CareEccCache ecc{1, 8, /*proactive_enabled=*/true};
  const uint64_t line = line_tag(70);

  REQUIRE(ecc.on_error(line, 0, /*chip=*/2) == CareEccCache::RegisterOutcome::REGISTERED);
  for (int i = 0; i < 10; ++i)
    ecc.on_read(line, 0); // S1 reads inflate err_count well past the cap
  REQUIRE(ecc.on_write(line, 0));
  REQUIRE(ecc.on_read(line, 0).promoted_s3);
  auto out = ecc.on_read(line, 0);
  REQUIRE(out.retire);
  REQUIRE(out.entry_chip == 2);
  REQUIRE_FALSE(out.proactive);
  REQUIRE(ecc.global_counter(0, 2) == CareEccCache::LOCAL_CONTRIB_CAP); // 3, not 13
}

TEST_CASE("Proactive disabled: retirements leave global counters untouched")
{
  CareEccCache ecc{1, 8}; // default: proactive off

  auto out = retire_sequence(ecc, line_tag(80), 0, /*chip=*/0);
  REQUIRE(out.retire);
  REQUIRE_FALSE(out.proactive);
  REQUIRE(ecc.global_counter(0, 0) == 0);
  REQUIRE(ecc.stats().gc_accumulations == 0);
}

TEST_CASE("Proactive victim list: every observed-error page of the region, dropped included")
{
  CareEccCache ecc{1, 1, /*proactive_enabled=*/true}; // 1 way: second registration drops
  const uint64_t page_a = 0;
  const uint64_t page_b = PAGE_2MB;
  const uint64_t page_c = 2 * PAGE_2MB;

  REQUIRE(ecc.on_error(line_tag(90), 0, 0) == CareEccCache::RegisterOutcome::REGISTERED);
  // Dropped block: no ECC entry, but its page is still region evidence.
  REQUIRE(ecc.on_error(PAGE_2MB + line_tag(91), 0, 1) == CareEccCache::RegisterOutcome::DROPPED);
  REQUIRE(ecc.on_error(2 * PAGE_2MB + line_tag(92), 0, 2) == CareEccCache::RegisterOutcome::DROPPED);

  auto pages = ecc.region_error_pages(0);
  REQUIRE(pages.size() == 3);
  REQUIRE(std::find(pages.begin(), pages.end(), page_a) != pages.end());
  REQUIRE(std::find(pages.begin(), pages.end(), page_b) != pages.end());
  REQUIRE(std::find(pages.begin(), pages.end(), page_c) != pages.end());

  // Retirement forgets the page: it must not be re-victimized later.
  ecc.invalidate_page(page_b);
  auto pages_after = ecc.region_error_pages(0);
  REQUIRE(pages_after.size() == 2);
  REQUIRE(std::find(pages_after.begin(), pages_after.end(), page_b) == pages_after.end());
}

TEST_CASE("Proactive OR variant: four same-chip retirements trigger via bias alone")
{
  CareEccCache ecc{1, 8, /*proactive_enabled=*/true, /*or_trigger=*/true};

  for (int i = 0; i < 3; ++i) {
    auto out = retire_sequence(ecc, line_tag(100 + i), 0, /*chip=*/0);
    REQUIRE(out.retire);
    REQUIRE_FALSE(out.proactive); // counter at 3*(i+1) <= 9 < 12
    ecc.invalidate_page(line_tag(100 + i) & CareEccCache::PAGE_BASE_MASK);
  }
  REQUIRE(ecc.global_counter(0, 0) == 9);

  auto out = retire_sequence(ecc, line_tag(103), 0, /*chip=*/0);
  REQUIRE(out.retire);
  REQUIRE(out.proactive); // 12: bias 12-0 >= 12 fires without saturation (OR)
  REQUIRE(ecc.stats().proactive_triggers == 1);
  REQUIRE(ecc.global_counter(0, 0) == 0); // trigger closes the round
}

TEST_CASE("Proactive AND default: bias at 12 without saturation does not trigger")
{
  CareEccCache ecc{1, 8, /*proactive_enabled=*/true}; // paper AND condition

  for (int i = 0; i < 4; ++i) {
    auto out = retire_sequence(ecc, line_tag(110 + i), 0, /*chip=*/0);
    REQUIRE_FALSE(out.proactive);
    ecc.invalidate_page(line_tag(110 + i) & CareEccCache::PAGE_BASE_MASK);
  }
  REQUIRE(ecc.global_counter(0, 0) == 12); // biased but not saturated: no trigger, no reset
}
