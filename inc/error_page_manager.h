/*
 * Error Page Manager for ChampSim
 * Manages error pages that require additional latency when accessed
 *
 * Error Address Tracking:
 *   - Records exact error cache line addresses (set by MC CE detection)
 *   - Page Error Counter: page_base → error count (up to retirement_threshold)
 *   - Page Retirement: retirement_threshold-th error → page offline emulation
 *
 * ECT (Error Counter Table): structure only, for paper completeness
 */

#ifndef ERROR_PAGE_MANAGER_H
#define ERROR_PAGE_MANAGER_H

#include <unordered_set>
#include <unordered_map>
#include <map>
#include <utility>
#include <array>
#include <vector>
#include <random>
#include <memory>
#include <algorithm>
#include <cstdint>
#include "address.h"
#include "chrono.h"
#include "champsim.h"
#include "care_ecc_cache.h"

enum class ErrorPageManagerMode {
    ALL_ON,
    RANDOM,
    CYCLE,
    OFF,
};

// Spatial placement of CYCLE-mode injected errors.
//   UNIFORM   — legacy: an error attaches to whatever read packet is serviced
//               next, so locations mirror the (bank-interleaved) access stream.
//   CLUSTERED — Poisson cluster model: error events belong to persistent
//               FaultDomains (cell/row/bank) so repeated errors concentrate
//               in the same line/row/bank, as hard faults do in the field.
enum class ErrorSpatialModel {
    UNIFORM,
    CLUSTERED,
    STICKY,     // access-driven CE at persistent fault regions, per-mode line
                // density (doc 10). Poisson births faults; a bad line errors on
                // every access. No Poisson CE budget, no starvation widening.
};

// DRAM fault granularity, following field-study fault taxonomies
// (Sridharan & Liberty, SC'12): a fault is a persistent defect region;
// every manifestation is one injected CE inside that region.
enum class FaultMode {
    CELL,   // single cell  -> repeats on one cache line
    ROW,    // wordline     -> repeats across lines of one (bank, row)
    BANK,   // bank circuitry -> repeats anywhere in one bank
};

// record_error() return values
enum class ErrorRecordResult {
    FIRST_ERROR,      // first error on this page
    ADDED_ERROR,      // additional error recorded
    ALREADY_KNOWN,    // already registered error position
    PAGE_RETIRED,     // retirement threshold reached
};

// ECT Entry: structure only (paper completeness)
struct ECTEntry {
    uint64_t tag{0};       // page base PA
    uint8_t counter{0};    // CE count
    bool valid{false};
};

// Per-CPU error attribution (multicore mix interpretation).
// An error is attributed to the CPU whose DRAM read packet consumed it.
struct PerCpuErrorStats {
    uint64_t errors_absorbed{0};      // total CYCLE errors consumed by this CPU's packets
    uint64_t first_errors{0};         // FIRST_ERROR results (pinning ON)
    uint64_t added_errors{0};         // ADDED_ERROR results (pinning ON)
    uint64_t already_known{0};        // ALREADY_KNOWN results (pinning ON)
    uint64_t retirements{0};          // PAGE_RETIRED results (pinning ON)
    uint64_t baseline_retirements{0}; // retirements triggered via baseline path (pinning OFF)
    uint64_t care_registered{0};      // CARE: new ECC cache registrations (scheme == care)
    uint64_t care_dropped{0};         // CARE: errors refused by full ECC cache set
    uint64_t care_retirements{0};     // CARE: page retirements triggered by S3 reads
};

class ErrorPageManager {
// Global Private Variables
private:
    std::unordered_set<uint64_t> error_pages;  // Page 단위 error (기존 호환용)
    std::unordered_set<uint64_t> current_ppage;
    ErrorPageManagerMode mode;
    champsim::chrono::clock::duration error_latency_penalty{};
    champsim::chrono::clock::duration pte_error_latency_penalty{};
    static std::unique_ptr<ErrorPageManager> instance;

// Error Address Tracking (replaces ETT bloom filter — exact tracking via MC CE_flag)
private:
    // Page error counters: page_base → error count
    std::unordered_map<uint64_t, uint32_t> page_error_counters;
    // Exact error addresses (cache-line aligned, set by MC CE detection)
    std::unordered_set<uint64_t> error_addresses;
    // Cache-line addresses that were removed from error_addresses by page retirement.
    // Unique-cl semantics: same PA retiring multiple times still counts as one entry.
    // Used by baseline Protection Coverage metric (snapshot, working-set bounded).
    std::unordered_set<uint64_t> retired_error_addresses;
    size_t retirement_threshold{32};

    // Pending LLC page retirements (page_base values)
    std::vector<uint64_t> pending_retirement_pages;

// ECT (Error Counter Table) — structure only, paper completeness
private:
    std::vector<ECTEntry> ect;  // 1024 entries default
    size_t ect_num_entries{1024};

// Error Recording Statistics
private:
    uint64_t stat_first_error_count{0};    // first error recordings
    uint64_t stat_added_error_count{0};    // additional error recordings
    uint64_t stat_retirement_count{0};     // pages retired
    uint64_t stat_already_known_count{0};  // duplicate error accesses

    // Retirement detail
    uint64_t stat_retirement_invalidated_lines{0};  // total cache lines invalidated by retirement sweeps

    // Per-CPU error attribution (ordered map for stable print order)
    std::map<uint32_t, PerCpuErrorStats> per_cpu_error_stats;

//For Random Error Injection
private:
    std::mt19937 gen{54321};
    std::uniform_real_distribution<double> prob_dist{0.0, 1.0};
    std::exponential_distribution<double> exp_dist{1.0};  // For exponential interval
    uint32_t errors_per_interval{1};

// Monte Carlo Simulation Results
private:
    double bit_error_rate{0.0};
    double page_error_rate{0.0};
    uint64_t page_size_bits{0};

// Cycle-based Error Injection
private:
    uint64_t error_cycle_interval{0};
    champsim::chrono::picoseconds cpu_clock_period{};
    uint64_t last_error_cycle{0};  // Track the last cycle when error was triggered
    uint64_t pending_error_count{0};  // Counter for pending errors
    int debug{1};  // Debug flag: 1 to enable debug logs, 0 to disable

// Spatial fault model (CLUSTERED). All state below is unused in UNIFORM mode,
// so legacy configs keep the exact same RNG stream and behavior.
private:
    // A persistent fault region. Created unanchored; the first read that
    // consumes one of its manifestations fixes its coordinates.
    struct FaultDomain {
        FaultMode mode;
        bool anchored{false};
        bool dead{false};        // killed by page retirement (CELL/ROW only)
        uint8_t chip{0};         // x8 device (byte lane 0-7) the defect lives in
        uint64_t bank_key{0};    // (dram channel << 32) | bank_request_index
        uint64_t row{0};         // DRAM row within the bank (ROW mode match)
        uint64_t anchor_cl{0};   // cache-line address (CELL mode match)
        uint64_t manifest_count{0};
        uint64_t salt{0};        // STICKY: per-fault hash basis for BANK line density
        // Co-location (doc 11): a co-located fault only anchors to a read inside
        // its target region (parent's bank[, row-group]), inheriting the parent's
        // chip -> models defect spatial correlation (multiple faults on one weak
        // bank/set on one lane). target_rowgroup used only for "set" scope.
        bool colocated{false};
        uint64_t target_bank_key{0};
        uint64_t target_rowgroup{0};
    };
    // One Poisson arrival waiting to be consumed by a matching read.
    // Starvation widens the match region in stages so a stalled manifestation
    // first stays inside its fault's bank (clustering preserved) and only then
    // falls back to any read (count preservation):
    //   widen 0: exact fault region   (after error_starvation_cycles) ->
    //   widen 1: fault's bank         (after 2x error_starvation_cycles) ->
    //   widen 2: any read
    struct PendingManifest {
        size_t fault_idx;
        uint64_t fire_cycle;
        uint8_t widen{0};
    };
    ErrorSpatialModel spatial_model{ErrorSpatialModel::UNIFORM};
    uint64_t error_seed{54321};
    // Mode mix only (normalized by sum): CARE Table II permanent-fault FIT
    // (Sridharan field study) — single-bit 18.6 / single-row 8.2 / single-bank
    // 10.0. The absolute FIT rate is NOT used: the temporal rate stays on the
    // accelerated error_cycle_interval scale (1e-5..1e-8 sweeps).
    double fault_weight_cell{18.6};
    double fault_weight_row{8.2};
    double fault_weight_bank{10.0};
    double fault_reuse_prob{0.7};
    uint64_t error_starvation_cycles{1000000};
    // STICKY: fraction of a BANK fault's accessed lines that are physically bad
    // (single-bank fault = scattered subset, NOT the whole bank). CELL/ROW = 1.0.
    double fault_density_bank{0.01};
    // Co-location (doc 11): probability a new fault clusters into an existing
    // fault's region (defect spatial correlation). 0 => independent (current).
    // scope_set=false: same bank+chip; true: same bank+row-group+chip (per-set).
    double fault_colocate_prob{0.0};
    bool fault_colocate_scope_set{false};
    std::mt19937_64 temporal_rng{54321};  // inter-arrival sampling (CLUSTERED)
    std::mt19937_64 spatial_rng{54321};   // fault creation/reuse sampling
    bool injection_initialized{false};
    uint64_t next_error_cycle{0};
    std::vector<FaultDomain> faults;
    std::vector<size_t> live_fault_indices;       // reuse-sampling pool (dead excluded)
    // --- STICKY hot-path acceleration (behavior-preserving) ----------------
    // consume_sticky_error() runs on every DRAM read and originally scanned the
    // whole live_fault_indices list twice (anchor loop + match loop), an O(N)
    // cost that grows with the (never-pruned) BANK-fault population. These two
    // secondary indices remove that cost WITHOUT changing which fault "wins":
    //   * sticky_unanchored: live faults not yet anchored, in birth order. The
    //     anchor loop scans only these (anchoring removes the fault from here).
    //   * sticky_anchored_by_bank: anchored live faults bucketed by bank_key,
    //     each bucket kept sorted ascending by fault index (== birth order ==
    //     the order a full scan of live_fault_indices would visit them). Every
    //     match condition (CELL/ROW/BANK) implies bank_key equality, so the
    //     match loop only needs the current read's bucket and still returns the
    //     same first match. Maintained only under STICKY; empty otherwise.
    std::vector<size_t> sticky_unanchored;
    std::unordered_map<uint64_t, std::vector<size_t>> sticky_anchored_by_bank;
    std::vector<PendingManifest> pending_manifests;
    // Pages permanently retired (hard-fault semantics): errors are never
    // recorded against a retired page again — its PA now stands for the
    // migrated-to healthy frame. CLUSTERED only; uniform keeps legacy behavior.
    std::unordered_set<uint64_t> clustered_retired_pages;
    // Clustered-mode statistics
    uint64_t stat_faults_created[3]{0, 0, 0};   // indexed by FaultMode
    uint64_t stat_manifests[3]{0, 0, 0};        // indexed by FaultMode
    uint64_t stat_anchor_manifests{0};          // manifestations that anchored a fault
    uint64_t stat_colocated_faults{0};          // faults born via co-location (doc 11)
    uint64_t stat_widened_bank{0};              // starvation: widened to fault's bank
    uint64_t stat_widened_any{0};               // starvation: widened to any read
    uint64_t stat_faults_killed[3]{0, 0, 0};    // faults dead via page retirement
    uint64_t stat_resampled_manifests{0};       // pending events reassigned off dead faults
    size_t stat_pending_peak{0};
    // Error location histograms (bank / row / line granularity). Filled on
    // every consumed error in BOTH spatial models (negligible cost: one map
    // increment per rare error event); printed as a fixed-size summary —
    // always under CLUSTERED, only with error_location_stats under UNIFORM
    // (keeping legacy output byte-identical by default).
    std::map<uint64_t, uint64_t> bank_manifest_hist;                        // bank_key -> errors
    std::map<std::pair<uint64_t, uint64_t>, uint64_t> row_manifest_hist;    // (bank_key, row) -> errors
    std::map<uint64_t, uint64_t> line_manifest_hist;                        // cl_addr -> errors
    bool location_stats_enabled{false};

// Cache Pinning (Error Way Partitioning)
private:
    bool cache_pinning_enabled{false};  // Enable/disable cache pinning feature
    bool dynamic_error_latency_enabled{true};  // true: emulate PTW(PSC+cache), false: fixed error_latency_penalty
    uint32_t max_error_ways_per_set{8};  // Maximum number of pinned/error ways per LLC set

// Baseline Page Retirement (no pinning)
private:
    size_t baseline_retirement_threshold{1};  // retire (reset) page after this many errors
    std::unordered_map<uint64_t, uint32_t> baseline_page_error_counts;  // page_base → error count
    uint64_t stat_baseline_retirement_count{0};

// CARE (HPCA'21) comparison scheme — reactive-only, hard-error-only (see care_ecc_cache.h)
private:
    bool care_enabled{false};
    // Demand-scrub model: the CE-detecting read is followed by an MC corrective
    // write (paper fleet runs memory scrubbing, CARE p.533 fn.1), so registration
    // immediately drives the S1->S2 hard-error-confirmation step. OFF reproduces
    // the app-writeback-gated behavior of the paper's gem5 evaluation.
    bool care_demand_scrub{false};
    // Proactive retirement (paper III.C): full-CARE structure. Under uniform
    // cell-fault injection the trigger provably never fires (see care_ecc_cache.h);
    // peak-margin stats are printed as the measured evidence.
    bool care_proactive{false};
    // Proactive trigger condition. true (default, user decision 2026-07-16):
    // saturation OR bias — fires when one counter reaches 15 or max-min >= 12.
    // false: the paper's literal AND condition, which needs ~5 same-chip
    // retirements landing in one set and never fired in full-scale probes.
    bool care_proactive_or{true};
    // Retire at S2->S3 confirmation instead of the next S3 read (mimic mode,
    // rationale in care_ecc_cache.h). Default ON: without it the accelerated-
    // injection pipeline starves (observed 98% drops, proactive never fires).
    bool care_retire_on_confirm{true};
    uint32_t care_bch_decode_cycles{30};  // for stat printing; latency below is authoritative
    champsim::chrono::clock::duration care_bch_decode_latency{};
    size_t care_ecc_sets{1024};
    size_t care_ecc_ways{2};
    std::unique_ptr<CareEccCache> care_cache;
    // Paper set-index geometry (III.B.3): set = global_bank_id * row_groups + row_group.
    // Configured from MEMORY_CONTROLLER::initialize; zero row_groups = not initialized.
    uint64_t care_banks_per_channel{0};   // ranks * bankgroups * banks
    uint64_t care_total_banks{0};         // channels * banks_per_channel
    uint64_t care_row_groups{0};          // care_ecc_sets / total_banks
    uint64_t care_row_group_shift{0};     // row_bits - log2(row_groups)
    uint64_t care_row_bit_offset{0};      // PA bit position of the row field (plain slice)
    uint64_t care_row_count{0};           // number of rows (mask = care_row_count - 1)
    // Proactive victim mode. false (default): evidence-based — pages with observed
    // errors in the region. true: paper-literal — every ALLOCATED page whose row
    // range overlaps the set's row-group (with 2MB pages + fine interleaving this
    // retires ~2GB per trigger; see 07_care_design_analysis.md §2).
    bool care_region_victims{false};
    // Chip (byte lane) of the most recently consumed injected error — handoff
    // from consume_cycle_error to care_on_injected_error (same service call).
    uint8_t last_consumed_chip{0};
    uint64_t stat_care_retirement_count{0};
    uint64_t stat_care_proactive_page_count{0};  // pages retired by proactive batches

// Error Statistics
private:
    uint64_t total_error_count{0};

public:
    // Singleton pattern
    static ErrorPageManager& get_instance() {
        if (!instance) {
            instance = std::make_unique<ErrorPageManager>();
        }
        return *instance;
    }

    void set_mode(ErrorPageManagerMode new_mode) { mode = new_mode; }

    ErrorPageManagerMode get_mode() const {
        return mode;
    }

    // Error page management (기존 방식 - 호환용)
    void add_error_page(champsim::page_number page) { error_pages.insert(page.to<uint64_t>()); }
    void remove_error_page(champsim::page_number page) { error_pages.erase(page.to<uint64_t>()); }
    bool is_error_page(champsim::page_number page) const { return error_pages.find(page.to<uint64_t>()) != error_pages.end(); }

    // ============================================================
    // Error Recording API (MC CE_flag based — no bloom filter)
    // ============================================================

    // Record a new error at physical address (64B aligned).
    // Returns the result indicating which case was triggered.
    ErrorRecordResult record_error(uint64_t pa);

    // Check if the given physical address is a known error address
    bool is_error_address(uint64_t pa) const {
        return error_addresses.count(pa & ~0x3FULL) > 0;  // cache-line aligned
    }

    // Get snapshot of all known error addresses (for protection coverage stats)
    const std::unordered_set<uint64_t>& get_error_addresses() const { return error_addresses; }

    // Snapshot of cl_addrs that left error_addresses via page retirement (unique).
    const std::unordered_set<uint64_t>& get_retired_error_addresses() const { return retired_error_addresses; }
    size_t get_retired_error_address_count() const { return retired_error_addresses.size(); }

    // Get page error counter (0 if not tracked)
    uint32_t get_page_error_counter(uint64_t page_base) const {
        auto it = page_error_counters.find(page_base);
        return (it != page_error_counters.end()) ? it->second : 0;
    }

    // Drain pending LLC page retirements (called from LLC operate())
    std::vector<uint64_t> drain_pending_retirements() {
        std::vector<uint64_t> result;
        result.swap(pending_retirement_pages);
        return result;
    }
    bool has_pending_retirements() const { return !pending_retirement_pages.empty(); }
    void requeue_retirement_page(uint64_t page_base) { pending_retirement_pages.push_back(page_base); }

    // Get number of tracked error pages
    size_t get_error_page_counter_count() const { return page_error_counters.size(); }

    // Configuration
    void set_retirement_threshold(size_t threshold) { retirement_threshold = threshold; }
    size_t get_retirement_threshold() const { return retirement_threshold; }

    // Statistics
    uint64_t get_stat_first_error_count() const { return stat_first_error_count; }
    uint64_t get_stat_added_error_count() const { return stat_added_error_count; }
    uint64_t get_stat_retirement_count() const { return stat_retirement_count; }
    uint64_t get_stat_already_known_count() const { return stat_already_known_count; }
    void add_retirement_invalidated_lines(uint64_t count) { stat_retirement_invalidated_lines += count; }
    void print_error_stats() const;

    // Per-CPU error attribution (stats only, no behavioral effect)
    void record_error_result_cpu(uint32_t cpu_idx, ErrorRecordResult result) {
        auto& s = per_cpu_error_stats[cpu_idx];
        s.errors_absorbed++;
        switch (result) {
            case ErrorRecordResult::FIRST_ERROR:   s.first_errors++; break;
            case ErrorRecordResult::ADDED_ERROR:   s.added_errors++; break;
            case ErrorRecordResult::ALREADY_KNOWN: s.already_known++; break;
            case ErrorRecordResult::PAGE_RETIRED:  s.retirements++; break;
        }
    }
    void record_baseline_error_cpu(uint32_t cpu_idx, bool retired) {
        auto& s = per_cpu_error_stats[cpu_idx];
        s.errors_absorbed++;
        if (retired) s.baseline_retirements++;
    }
    const std::map<uint32_t, PerCpuErrorStats>& get_per_cpu_error_stats() const { return per_cpu_error_stats; }
    void print_per_cpu_error_stats() const;

    // ============================================================
    // Existing API (unchanged)
    // ============================================================

    // Monte Carlo Simulation for page error rate
    void init_page_error_rate(double bit_error_rate);

    // Latency management
    void set_error_latency(champsim::chrono::clock::duration latency) { error_latency_penalty = latency; }
    champsim::chrono::clock::duration get_error_latency() const { return error_latency_penalty; }
    void set_pte_error_latency(champsim::chrono::clock::duration latency) { pte_error_latency_penalty = latency; }
    champsim::chrono::clock::duration get_pte_error_latency() const { return pte_error_latency_penalty; }

    // Random error injection settings
    void set_errors_per_interval(uint32_t count) { errors_per_interval = count; }
    uint32_t get_errors_per_interval() const { return errors_per_interval; }

    // Monte Carlo simulation results
    void set_bit_error_rate(double ber) { bit_error_rate = ber; }
    double get_bit_error_rate() const { return bit_error_rate; }
    double get_page_error_rate() const { return page_error_rate; }
    uint64_t get_page_size_bits() const { return page_size_bits; }

    // Check if error occurs for current DRAM access based on Page Error Rate
    bool check_page_error() { return prob_dist(gen) < page_error_rate; }

    // Cycle-based error injection setters/getters
    void set_error_cycle_interval(uint64_t interval) {
        error_cycle_interval = interval;
        // Initialize exponential distribution with rate = 1/mean_interval
        if (interval > 0) {
            exp_dist = std::exponential_distribution<double>(1.0 / static_cast<double>(interval));
            // Initialize first error cycle with exponential sample
            last_error_cycle = static_cast<uint64_t>(exp_dist(gen));
        }
    }
    uint64_t get_error_cycle_interval() const { return error_cycle_interval; }
    void set_cpu_clock_period(champsim::chrono::picoseconds period) { cpu_clock_period = period; }
    champsim::chrono::picoseconds get_cpu_clock_period() const { return cpu_clock_period; }

    // Debug mode setter/getter
    void set_debug(int debug_mode) { debug = debug_mode; }
    int get_debug() const { return debug; }

    // Cache Pinning setter/getter
    void set_cache_pinning_enabled(bool enabled) { cache_pinning_enabled = enabled; }
    bool is_cache_pinning_enabled() const { return cache_pinning_enabled; }

    // Dynamic/Fixed error latency mode setter/getter
    void set_dynamic_error_latency_enabled(bool enabled) { dynamic_error_latency_enabled = enabled; }
    bool is_dynamic_error_latency_enabled() const { return dynamic_error_latency_enabled; }

    // Cache pinning capacity setter/getter
    void set_max_error_ways_per_set(uint32_t ways) { max_error_ways_per_set = std::max<uint32_t>(1, ways); }
    uint32_t get_max_error_ways_per_set() const { return max_error_ways_per_set; }

    // Baseline retirement threshold setter/getter
    void set_baseline_retirement_threshold(size_t threshold) { baseline_retirement_threshold = threshold; }
    size_t get_baseline_retirement_threshold() const { return baseline_retirement_threshold; }

    // Baseline page retirement: returns true if this error triggers retirement.
    // Tracks cl_addr in error_addresses (for snapshot Protection Coverage metric)
    // and delegates to shared retire_page() helper on threshold hit.
    bool record_baseline_error(uint64_t pa);
    uint64_t get_stat_baseline_retirement_count() const { return stat_baseline_retirement_count; }

    // ============================================================
    // CARE scheme API (called from DRAM_CHANNEL::service_packet)
    // ============================================================

    void set_care_enabled(bool enabled) { care_enabled = enabled; }
    bool is_care_enabled() const { return care_enabled; }
    void set_care_bch_decode_cycles(uint32_t cycles) { care_bch_decode_cycles = cycles; }
    uint32_t get_care_bch_decode_cycles() const { return care_bch_decode_cycles; }
    void set_care_bch_decode_latency(champsim::chrono::clock::duration latency) { care_bch_decode_latency = latency; }
    champsim::chrono::clock::duration get_care_bch_decode_latency() const { return care_bch_decode_latency; }
    void set_care_ecc_geometry(size_t sets, size_t ways) { care_ecc_sets = sets; care_ecc_ways = ways; }
    void set_care_demand_scrub(bool enabled) { care_demand_scrub = enabled; }
    bool is_care_demand_scrub() const { return care_demand_scrub; }
    void set_care_proactive(bool enabled) { care_proactive = enabled; }
    bool is_care_proactive() const { return care_proactive; }
    void set_care_proactive_or(bool enabled) { care_proactive_or = enabled; }
    bool is_care_proactive_or() const { return care_proactive_or; }
    void set_care_retire_on_confirm(bool enabled) { care_retire_on_confirm = enabled; }
    bool is_care_retire_on_confirm() const { return care_retire_on_confirm; }
    size_t get_care_ecc_sets() const { return care_ecc_sets; }
    size_t get_care_ecc_ways() const { return care_ecc_ways; }

    // Construct the ECC cache after all config setters ran (MEMORY_CONTROLLER::initialize)
    void init_care_cache();

    // Paper set-index geometry, from MEMORY_CONTROLLER::initialize (before any access).
    // row_bit_offset = PA bit position of the (unswizzled) row field.
    void set_care_dram_geometry(uint64_t channels, uint64_t banks_per_channel, uint64_t rows,
                                uint64_t row_bit_offset);
    void set_care_region_victims(bool enabled) { care_region_victims = enabled; }
    // set = global_bank_id * row_groups + row-MSB group (paper III.B.3 layout)
    size_t care_set_index(uint64_t bank_key, uint64_t row) const {
        uint64_t global_bank_id = (bank_key >> 32) * care_banks_per_channel + (bank_key & 0xFFFFFFFFULL);
        return static_cast<size_t>(global_bank_id * care_row_groups + (row >> care_row_group_shift));
    }

    // Every DRAM read (first service of the packet): decode latency / retirement decision.
    CareEccCache::ReadOutcome care_on_read(uint64_t pa, uint32_t cpu_idx, uint64_t bank_key, uint64_t row);
    // Every DRAM write (first service): S1→S2 confirmation.
    void care_on_write(uint64_t pa, uint64_t bank_key, uint64_t row);
    // Injected error consumed by a read packet: registration attempt (no latency).
    // Chip comes from the consumed fault (clustered) or an address hash (uniform).
    void care_on_injected_error(uint64_t pa, uint32_t cpu_idx, uint64_t bank_key, uint64_t row);

    uint64_t get_stat_care_retirement_count() const { return stat_care_retirement_count; }
    void print_care_stats() const;

    // Update cycle error counter (called from operate() every cycle)
    void update_cycle_errors(champsim::chrono::clock::time_point current_time) {
        if (error_cycle_interval == 0 || cpu_clock_period.count() == 0) {
            return;
        }

        uint64_t current_cycle = current_time.time_since_epoch().count() / cpu_clock_period.count();

        if (spatial_model == ErrorSpatialModel::CLUSTERED) {
            update_clustered_errors(current_cycle);
            return;
        }
        if (spatial_model == ErrorSpatialModel::STICKY) {
            update_sticky_faults(current_cycle);   // Poisson births faults (reuses error_cycle_interval)
            return;
        }

        // last_error_cycle is now used as "next_error_cycle"
        // If current cycle reaches the next scheduled error cycle, trigger error
        if (current_cycle >= last_error_cycle) {
            pending_error_count++;

            // Sample next interval from exponential distribution
            double next_interval = exp_dist(gen);
            last_error_cycle = current_cycle + static_cast<uint64_t>(next_interval);

            // Debug output - only show when debug=1
            if (debug == 1) {
                fmt::print("[ERROR_CYCLE] Error added at CPU cycle {}, next at {}, pending count: {}\n",
                           current_cycle, last_error_cycle, pending_error_count);
            }
        }
    }

    // Consume one error for the read currently being serviced (service_packet).
    // UNIFORM: any read drains the counter (legacy). CLUSTERED: the read must
    // fall inside a pending manifestation's fault region (or anchor a new fault).
    // bank_key = (dram channel << 32) | bank_request_index, row = DRAM row.
    bool consume_cycle_error(uint64_t pa, uint64_t bank_key, uint64_t row) {
        if (spatial_model == ErrorSpatialModel::CLUSTERED) {
            return consume_clustered_error(get_cache_line_addr(pa), bank_key, row);
        }
        if (spatial_model == ErrorSpatialModel::STICKY) {
            return consume_sticky_error(get_cache_line_addr(pa), bank_key, row);
        }
        if (pending_error_count > 0) {
            pending_error_count--;
            record_error_location(get_cache_line_addr(pa), bank_key, row);
            // Uniform errors carry no fault identity: derive the byte lane
            // (chip) deterministically from the line address.
            last_consumed_chip = static_cast<uint8_t>(((pa >> 6) * 0x9E3779B97F4A7C15ULL) >> 61);
            return true;
        }
        return false;
    }

    // Spatial fault model configuration
    void set_error_spatial_model(ErrorSpatialModel m) { spatial_model = m; }
    ErrorSpatialModel get_error_spatial_model() const { return spatial_model; }
    void set_error_seed(uint64_t seed) { error_seed = seed; }
    uint64_t get_error_seed() const { return error_seed; }
    void set_fault_mode_weights(double cell, double row, double bank) {
        fault_weight_cell = cell; fault_weight_row = row; fault_weight_bank = bank;
    }
    void set_fault_reuse_prob(double p) { fault_reuse_prob = p; }
    void set_error_starvation_cycles(uint64_t cycles) { error_starvation_cycles = cycles; }
    void set_fault_density_bank(double d) { fault_density_bank = d; }
    void set_fault_colocate(double prob, bool set_scope) { fault_colocate_prob = prob; fault_colocate_scope_set = set_scope; }
    // Prints the clustered-model section when active (no-op under UNIFORM,
    // keeping legacy output byte-identical). Safe to call from any stats path.
    void print_spatial_fault_stats() const;
    // Opt-in location histogram printing for UNIFORM runs (comparison data).
    void set_location_stats_enabled(bool enabled) { location_stats_enabled = enabled; }

    // Extract page number from physical address
    static champsim::page_number get_page_number(champsim::address addr) {
        return champsim::page_number{addr};
    }

    // Physical Page Management
    void add_current_ppage(champsim::page_number page) { current_ppage.insert(page.to<uint64_t>()); }
    void remove_current_ppage(champsim::page_number page) { current_ppage.erase(page.to<uint64_t>()); }
    bool is_current_ppage(champsim::page_number page) const { return current_ppage.find(page.to<uint64_t>()) != current_ppage.end(); }

    // Utility functions
    size_t get_error_page_count() const { return error_pages.size(); }
    size_t get_current_ppage_count() const { return current_ppage.size(); }
    void clear_all_error_pages() { error_pages.clear(); }
    void clear_current_ppage() { current_ppage.clear(); }

    // Inject Error at All Pages
    void all_error_pages_on(uint64_t page_num);

    // Error Statistics
    void record_error_access(void) {
        total_error_count++;
    }
    uint64_t get_total_error_count() const { return total_error_count; }
    void reset_error_stats() {
        total_error_count = 0;
    }

    // For debugging
    void print_error_pages() const;

private:
    // CARE region-victim internals (error_page_manager.cc)
    uint64_t care_row_of_pa(uint64_t pa) const {
        return (pa >> care_row_bit_offset) & (care_row_count - 1);
    }
    std::vector<uint64_t> care_region_victim_pages(uint64_t row_group) const;

    // Spatial fault model internals (error_page_manager.cc)
    void update_clustered_errors(uint64_t current_cycle);
    bool consume_clustered_error(uint64_t cl_addr, uint64_t bank_key, uint64_t row);
    void spawn_manifest(uint64_t fire_cycle);
    size_t select_fault_for_manifest();
    void on_page_retired_clustered(uint64_t page_base);
    // STICKY model (doc 10): Poisson births faults; access to a bad line = CE.
    void update_sticky_faults(uint64_t current_cycle);
    void birth_fault();
    bool consume_sticky_error(uint64_t cl_addr, uint64_t bank_key, uint64_t row);
    bool is_bad_line(const FaultDomain& f, uint64_t cl_addr) const;
    void print_sticky_stats() const;
    void record_error_location(uint64_t cl_addr, uint64_t bank_key, uint64_t row) {
        bank_manifest_hist[bank_key]++;
        row_manifest_hist[{bank_key, row}]++;
        line_manifest_hist[cl_addr]++;
    }
    void print_location_histograms() const;
    void print_clustered_stats() const;

    // Internal helpers.
    // queue_llc_sweep=false: CARE has no LLC error ways and the sweep consumer
    // (cache.cc) is pinning-gated — queueing would only grow the vector unbounded.
    void retire_page(uint64_t page_base, bool queue_llc_sweep = true);
    static uint64_t get_page_base_pa(uint64_t pa) {
        // 2MB aligned (single source of the page-base mask: care_ecc_cache.h)
        return pa & CareEccCache::PAGE_BASE_MASK;
    }
    static uint64_t get_cache_line_addr(uint64_t pa) {
        // Cache-line aligned: clear lower 6 bits
        return pa & ~0x3FULL;
    }
};

#endif // ERROR_PAGE_MANAGER_H
