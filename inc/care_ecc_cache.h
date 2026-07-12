/*
 * CARE (HPCA'21) ECC cache model — reactive-only, hard-error-only simplification.
 *
 * Models the memory-controller-resident "ECC cache" of CARE (Chen et al.,
 * "CARE: Coordinated Augmentation for Elastic Resilience on DRAM Errors in
 * Data Centers", HPCA 2021, Section III) at the granularity needed for IPC
 * comparison:
 *   - Tracks 64B blocks that have seen a (correctable) DRAM error.
 *   - Block state machine (paper Fig. 3), S0 represented by absence:
 *       error       -> S1 (BCH-augmented protection)
 *       S1 --write--> S2 (hard-error confirming)
 *       S2 --read---> S3 (hard error: every read of a faulty block re-detects)
 *       S3 --read---> retire signal (caller retires the containing page)
 *   - Replacement follows paper Pseudocode 1. With single-error registration
 *     (new block err_count == 1) and resident err_count >= 1, it degenerates
 *     to "insert only into a free way" — fixed by unit test.
 *
 * Deliberate deviations (paper text records these; see EXPANSION_PLAN B-0):
 *   - Set index is a plain address-bit slice, not channel/rank/bank/partial-row
 *     (physical clustering only matters for proactive retirement, not modeled).
 *   - Single per-entry error counter instead of 8x2-bit column counters.
 *   - Random tie-break of Pseudocode 1 replaced by lowest-index pick for
 *     determinism (branch unreachable under the degenerate replacement above).
 *
 * Pure logic: no ChampSim dependencies, unit-testable standalone.
 */

#ifndef CARE_ECC_CACHE_H
#define CARE_ECC_CACHE_H

#include <cstddef>
#include <cstdint>
#include <vector>

class CareEccCache
{
public:
  enum class State : uint8_t { S1 = 1, S2 = 2, S3 = 3 };

  struct ReadOutcome {
    bool tracked{false};      // hit: BCH decode latency applies
    bool promoted_s3{false};  // S2 -> S3 transition happened on this read
    bool retire{false};       // read in S3: caller must retire the page
  };

  enum class RegisterOutcome : uint8_t {
    REGISTERED,      // new entry inserted (S1)
    ALREADY_TRACKED, // error landed on a tracked block: no state/count change
    DROPPED,         // set full (Pseudocode 1 refused): block stays unprotected
  };

  struct Stats {
    uint64_t registered{0};        // new entries inserted (S1)
    uint64_t dropped{0};           // erroneous block refused (set full, Pseudocode 1)
    uint64_t errors_on_tracked{0}; // injected error landed on an already-tracked block
    uint64_t decode_reads{0};      // reads of tracked blocks (BCH decode charged)
    uint64_t writes_s1_to_s2{0};
    uint64_t reads_s2_to_s3{0};
    uint64_t retires{0};                // retire signals raised (S3 read)
    uint64_t invalidated_entries{0};    // entries removed by page retirement
  };

  CareEccCache(std::size_t num_sets, std::size_t num_ways);

  // Every DRAM read of this 64B-aligned line (first service only).
  ReadOutcome on_read(uint64_t line_addr);

  // Every DRAM write of this line: S1 -> S2 confirmation step.
  // Returns true if the S1->S2 transition happened.
  bool on_write(uint64_t line_addr);

  // Injected error on this line: register (S1) if untracked.
  RegisterOutcome on_error(uint64_t line_addr);

  // Page retirement: drop every entry inside the 2MB page. Returns count.
  std::size_t invalidate_page(uint64_t page_base);

  // Introspection (stats printing / unit tests)
  bool is_tracked(uint64_t line_addr) const;
  State state_of(uint64_t line_addr) const; // precondition: is_tracked()
  std::size_t occupancy() const;
  std::size_t num_sets() const { return sets_; }
  std::size_t num_ways() const { return ways_; }
  const Stats& stats() const { return stats_; }

  // 2MB page base mask — must match ErrorPageManager::get_page_base_pa.
  static constexpr uint64_t PAGE_BASE_MASK = ~((1ULL << 21) - 1);

private:
  struct Entry {
    uint64_t line_addr{0}; // 64B-aligned physical address (full tag)
    uint32_t err_count{0}; // saturating
    State state{State::S1};
    bool valid{false};
  };

  std::size_t set_index(uint64_t line_addr) const { return (line_addr >> 6) & (sets_ - 1); }
  Entry* find(uint64_t line_addr);
  const Entry* find(uint64_t line_addr) const;
  Entry* pick_victim(std::size_t set); // paper Pseudocode 1; nullptr = no replacement

  static constexpr uint32_t ERR_COUNT_CAP = 255;

  std::size_t sets_;
  std::size_t ways_;
  std::vector<Entry> entries_; // sets_ x ways_, row-major
  Stats stats_{};
};

#endif // CARE_ECC_CACHE_H
