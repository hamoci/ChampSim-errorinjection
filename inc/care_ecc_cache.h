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
 *     With retire_on_confirm, the S2 read raises the retire signal at S3
 *     entry; S3 becomes transient (never resident across calls, so the
 *     Pseudocode 1 S3-blocking branch never binds). See deviations below.
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
 *   - contention-free confirmation ("celog" paths, driven by
 *     ErrorPageManager): a repeat CE on an UNTRACKED line confirms hard and
 *     retires without ECC cache admission. Rationale: every CE's address and
 *     syndrome already passes through the MC in CARE's own design (Fig. 5
 *     read path); what the 2-way set bounds is RETENTION, and the paper
 *     sizes that retention to its p_b design point (5e-13..5e-10, Fig. 4a).
 *     Both of the paper's evaluation tracks run where set contention is ~0 —
 *     FaultSim at field FIT rates, and gem5 with one-week/one-year FIT error
 *     maps (IV.A.3, a handful of faults) — so the drop path effectively
 *     never executes in the paper's own evaluation. Under our accelerated
 *     injection (p_b ~6-9 orders above design point) it dominates: 94-99%
 *     drops, retirement starved, proactive never fed. This mimic therefore
 *     models the CONFIRMATION pipeline at the contention-free point the
 *     paper's evaluation assumes (same abstraction family as
 *     retire_on_confirm below), while PROTECTION (BCH attachment and its
 *     decode latency) stays bounded by the paper's real 1024x2 hardware.
 *     With demand scrubbing the corrective write after the first CE is
 *     admission-independent, so the repeat CE is a post-rewrite recurrence —
 *     exactly the evidence the S1->S2->S3 walk collects (III.B.2); inside
 *     the paper's evaluated regime this path is behaviorally
 *     indistinguishable from residency-based confirmation.
 *     confirm_untracked() accumulates the global counters with the same
 *     lane/cap arithmetic as a tracked retirement so the proactive trigger
 *     sees both paths identically.
 *   - retire_on_confirm (mimic mode, default off): the S2->S3 confirming read
 *     raises the retire signal immediately instead of waiting for one more S3
 *     read. Rationale: confirmation is complete at S3 entry by the paper's own
 *     text (Fig. 3 labels S3 "Ready for Page Retirement"; p.537 "the data
 *     block is confirmed to contain hard errors"); the subsequent read is a
 *     trigger of convenience ("we CHOOSE to retire ... when the data block
 *     sees another read access"), not evidence. That extra read is access-
 *     dependent — a limitation the paper itself reports (p.541: unaccessed
 *     regions "get corrupted silently"; scrubbing is suggested only as a
 *     complementary remedy, not modeled) — and under accelerated injection it
 *     starves the pipeline (observed: 98% drops, S3 squatters freeze their
 *     sets via Pseudocode 1 branch 1, proactive never fires). Retiring at
 *     confirmation approximates the prompt-observation abstraction under
 *     which the paper's reliability claims are produced (FaultSim track,
 *     Fig. 6) and matches its responsive-retirement intent (IV.B.2). The
 *     evidence chain (register -> repair write -> re-detect) is untouched.
 *   - Single per-entry error counter instead of 8x2-bit column counters
 *     (per-retirement global-counter contribution capped at 3 to compensate).
 *     In retire_on_confirm mode the contribution is fixed AT the cap: the
 *     compressed pipeline gives a retiring block exactly 2 observations
 *     (register + confirming read) where the paper's flow accumulates >= 3,
 *     so min(err_count, 3) would silently change the paper's trigger
 *     arithmetic (15/3 = 5 same-chip retirements per proactive) to 15/2 = 8.
 *   - Random tie-break of Pseudocode 1 replaced by lowest-index pick for
 *     determinism (branch unreachable under the degenerate replacement above).
 *   - Transient errors unmodeled (hard-only): no S2 -> S0 soft-repair path.
 *
 * Pure logic: no ChampSim dependencies, unit-testable standalone.
 */

#ifndef CARE_ECC_CACHE_H
#define CARE_ECC_CACHE_H

#include <algorithm>
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
    uint64_t retires_celog{0};          // retire signals raised by contention-free confirm (untracked repeat CE)
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
  // retire_on_confirm collapses S3 into the confirming read (mimic mode,
  // header rationale above).
  CareEccCache(std::size_t num_sets, std::size_t num_ways, bool proactive_enabled = false,
               bool or_trigger = false, bool retire_on_confirm = false);

  // Every DRAM read of this 64B-aligned line (first service only).
  // set = caller-composed paper index (channel|rank/bank fold|row MSBs).
  ReadOutcome on_read(uint64_t line_addr, std::size_t set);

  // Every DRAM write of this line: S1 -> S2 confirmation step.
  // Returns true if the S1->S2 transition happened.
  bool on_write(uint64_t line_addr, std::size_t set);

  // Injected error on this line: register (S1) if untracked. chip picks the
  // proactive global counter (x8 device / byte lane the fault lives in).
  RegisterOutcome on_error(uint64_t line_addr, std::size_t set, uint8_t chip = 0);

  // Contention-free confirmation (header rationale above): the caller
  // observed a REPEAT CE on an untracked line of this set — confirmed hard.
  // Returns a retire outcome and accumulates the set's global counters with
  // the same lane/cap arithmetic as a tracked retirement (proactive fields
  // filled when the trigger fires). The caller retires the page.
  ReadOutcome confirm_untracked(std::size_t set, uint8_t chip);

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

  // Accumulate a retirement into its set's global counters (contrib into the
  // chip's lane); fills the outcome's proactive/biased_chip/bias fields when
  // the trigger fires. Shared by tracked (S3 read) and celog retirements.
  void account_retirement(std::size_t set, uint8_t chip_idx, uint32_t contrib, ReadOutcome& out);
  // Global-counter contribution of a retiring block. retire_on_confirm (and
  // celog): the compressed pipeline observes a retiring block exactly twice
  // (register + confirming read) where the paper's flow accumulates >= 3 —
  // contribute the full 2-bit cap so the paper's trigger arithmetic
  // (15/3 = 5 same-chip retirements per proactive) is preserved instead of
  // silently becoming 15/2 = 8.
  uint32_t retire_contrib(uint32_t err_count) const
  {
    return retire_on_confirm_ ? LOCAL_CONTRIB_CAP : std::min(err_count, LOCAL_CONTRIB_CAP);
  }

  std::size_t sets_;
  std::size_t ways_;
  bool proactive_enabled_;
  bool or_trigger_;
  bool retire_on_confirm_;
  std::vector<Entry> entries_; // sets_ x ways_, row-major
  std::vector<std::array<uint8_t, NUM_GLOBAL_COUNTERS>> gcounters_; // per set
  // Pages with observed errors per set (proactive victim evidence). Bounded
  // by the number of distinct erroneous pages; pages leave on retirement.
  std::vector<std::unordered_set<uint64_t>> observed_pages_;
  Stats stats_{};
};

#endif // CARE_ECC_CACHE_H
