/*
 * CARE (HPCA'21) ECC cache model — reactive + proactive, hard-error-only.
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
 * Set indexing (paper III.B.3): the index is NOT derived from the line
 * address here. The caller (ErrorPageManager) composes it from DRAM
 * coordinates — channel | rank/bankgroup/bank | row MSBs — so one set
 * covers one (bank, row-region), exactly the paper's 10-bit layout
 * (6 bank-field bits + 4 partial-row bits with our 64-bank geometry).
 * Every lookup therefore takes an explicit set argument.
 *
 * Proactive retirement (paper Section III.C):
 *   - 8 saturating 4-bit global counters per set, one per x8 DEVICE (byte
 *     lane 0B..7B of the 64B block, paper Fig. 1/2b). The injected fault
 *     model assigns each fault a chip (0-7); a retiring entry accumulates
 *     its error count (capped at 3 = the paper's 2-bit local counter max)
 *     into the counter of its chip.
 *   - Trigger check at accumulation: some counter saturated (== 15) AND
 *     max - min >= 12 (paper's 95%-confidence bias bound) -> proactive:
 *     caller retires every page resident in the set (adaptation: the paper
 *     retires the set's whole region — all pages of one (bank, row-region);
 *     with 2MB pages interleaved across banks that region overlaps nearly
 *     every page, so we retire the pages the set actually tracks and keep
 *     the trigger count as the headline metric). Saturation without bias
 *     resets the set's counters for the next accounting round.
 *
 * Remaining deliberate deviations:
 *   - Single per-entry error counter instead of 8x2-bit column counters
 *     (per-retirement global-counter contribution capped at 3 to compensate).
 *   - Random tie-break of Pseudocode 1 replaced by lowest-index pick for
 *     determinism (branch unreachable under the degenerate replacement above).
 *   - Transient errors unmodeled (hard-only): no S2 -> S0 soft-repair path.
 *
 * Pure logic: no ChampSim dependencies, unit-testable standalone.
 */

#ifndef CARE_ECC_CACHE_H
#define CARE_ECC_CACHE_H

#include <array>
#include <cstddef>
#include <cstdint>
#include <unordered_set>
#include <vector>

class CareEccCache
{
public:
  enum class State : uint8_t { S1 = 1, S2 = 2, S3 = 3 };

  struct ReadOutcome {
    bool tracked{false};      // hit: BCH decode latency applies
    bool promoted_s3{false};  // S2 -> S3 transition happened on this read
    bool retire{false};       // read in S3: caller must retire the page
    bool proactive{false};    // retirement saturated a biased global counter:
                              // caller must also retire set_resident_pages()
    uint8_t entry_chip{0};    // retiring entry's chip (retirement log)
    uint32_t entry_err_count{0}; // retiring entry's error count (retirement log)
    uint8_t biased_chip{0};   // proactive only: the dominant counter's chip
    uint8_t bias{0};          // proactive only: max - min at the trigger
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
    // Proactive retirement (only move when proactive is enabled)
    uint64_t proactive_triggers{0};     // saturated + biased checks
    uint64_t gc_accumulations{0};       // reactive retirements accounted
    uint64_t gc_resets{0};              // accounting rounds closed (saturation)
    uint8_t gc_peak_value{0};           // highest counter value ever reached
    uint8_t gc_peak_bias{0};            // highest (max - min) seen at a check
  };

  static constexpr std::size_t NUM_GLOBAL_COUNTERS = 8;
  static constexpr uint8_t GLOBAL_COUNTER_MAX = 15;   // 4-bit saturating
  static constexpr uint8_t PROACTIVE_BIAS_MIN = 12;   // paper: 95% confidence bound
  static constexpr uint32_t LOCAL_CONTRIB_CAP = 3;    // paper: 2-bit local counters

  // or_trigger relaxes the paper's trigger (saturation AND bias) to
  // saturation OR bias — exploratory only, not the paper's condition.
  CareEccCache(std::size_t num_sets, std::size_t num_ways, bool proactive_enabled = false,
               bool or_trigger = false);

  // Every DRAM read of this 64B-aligned line (first service only).
  // set = caller-composed paper index (channel|rank/bank fold|row MSBs).
  ReadOutcome on_read(uint64_t line_addr, std::size_t set);

  // Every DRAM write of this line: S1 -> S2 confirmation step.
  // Returns true if the S1->S2 transition happened.
  bool on_write(uint64_t line_addr, std::size_t set);

  // Injected error on this line: register (S1) if untracked. chip picks the
  // proactive global counter (x8 device / byte lane the fault lives in).
  RegisterOutcome on_error(uint64_t line_addr, std::size_t set, uint8_t chip = 0);

  // Page retirement: drop every entry inside the 2MB page (and forget the
  // page in every set's observed-error list). Returns entry count.
  std::size_t invalidate_page(uint64_t page_base);

  // Proactive victim list: every page that has EVER shown an injected error
  // in this set's region (registered, already-tracked or dropped) and is not
  // yet retired. Rigorous adaptation of the paper's "all pages the set
  // protects": with 2MB pages fine-interleaved across banks, the literal
  // region (one bank x one row-group) intersects a thin slice of nearly
  // every page, so region-wide retirement is ill-defined here — we retire
  // the pages the region has evidence against instead.
  std::vector<uint64_t> region_error_pages(std::size_t set) const;

  // Introspection (stats printing / unit tests)
  bool is_tracked(uint64_t line_addr, std::size_t set) const;
  State state_of(uint64_t line_addr, std::size_t set) const; // precondition: is_tracked()
  std::size_t occupancy() const;
  std::size_t num_sets() const { return sets_; }
  std::size_t num_ways() const { return ways_; }
  const Stats& stats() const { return stats_; }
  uint8_t global_counter(std::size_t set, std::size_t idx) const { return gcounters_[set][idx]; }

  // 2MB page base mask — must match ErrorPageManager::get_page_base_pa.
  static constexpr uint64_t PAGE_BASE_MASK = ~((1ULL << 21) - 1);

private:
  struct Entry {
    uint64_t line_addr{0}; // 64B-aligned physical address (full tag)
    uint32_t err_count{0}; // saturating
    State state{State::S1};
    bool valid{false};
    uint8_t chip_idx{0};   // proactive global-counter index (x8 device 0-7)
  };

  Entry* find(uint64_t line_addr, std::size_t set);
  const Entry* find(uint64_t line_addr, std::size_t set) const;
  Entry* pick_victim(std::size_t set); // paper Pseudocode 1; nullptr = no replacement

  static constexpr uint32_t ERR_COUNT_CAP = 255;

  // Accumulate the retiring entry into its set's global counters; fills the
  // outcome's proactive/biased_chip/bias fields when the trigger fires.
  void account_retirement(std::size_t set, const Entry& e, ReadOutcome& out);

  std::size_t sets_;
  std::size_t ways_;
  bool proactive_enabled_;
  bool or_trigger_;
  std::vector<Entry> entries_; // sets_ x ways_, row-major
  std::vector<std::array<uint8_t, NUM_GLOBAL_COUNTERS>> gcounters_; // per set
  // Pages with observed errors per set (proactive victim evidence). Bounded
  // by the number of distinct erroneous pages; pages leave on retirement.
  std::vector<std::unordered_set<uint64_t>> observed_pages_;
  Stats stats_{};
};

#endif // CARE_ECC_CACHE_H
