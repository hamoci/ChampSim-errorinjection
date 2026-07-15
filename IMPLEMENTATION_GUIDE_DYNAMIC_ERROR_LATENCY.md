# Dynamic Error Latency Implementation Guide

## Overview

이 문서는 ChampSim에서 동적 Error Latency 계산 기능을 구현한 내용을 상세하게 기록합니다.
LLC Pinning 사용 시 에러가 발생하면 PTE의 Unused bit에 에러 정보를 기록하기 위해 Page Table Walk(PTW)를 수행해야 하며, 이 PTW의 latency가 Error Latency입니다.

## Quick Start (Current: 1e-8)

### 최신 only_for_test 구성 파일

- `sim_configs/only_for_test/_2MBLLC_2MBPage_DRAM_Error_1e-8.json`
- `sim_configs/only_for_test/_2MBLLC_2MBPage_DRAM_Error_baseline.json`
- `sim_configs/only_for_test/_2MBLLC_4KBPage_DRAM_Error_1e-8.json`
- `sim_configs/only_for_test/_2MBLLC_4KBPage_DRAM_Error_baseline.json`

### 최신 실행 절차

```bash
cd /home/hamoci/Study/ChampSim
./build_only_for_test.sh
./run_only_for_test_du_sh_trace.sh
```

### 최신 기준 핵심 포인트

- 동적/정적 latency 로그는 모두 CPU cycle 기준으로 출력
- 동적 PTW의 DRAM miss 모델은 level당 `+200 CPU cycles`
- `[ERROR_OCCUR]`의 `Total Errors`는 실제 누적 에러 수(`record_error_access`)를 의미
- `[ERROR_OCCUR]`의 `PinnedLines`는 cacheline(64B) 기준 고유 등록 개수

## 구현된 요구사항

### 요구사항 1: Dynamic Error Latency 계산 (PSC + Cache Hierarchy 기반)

**목표:**
- 에러 발생 시점의 PSC와 Cache 상태를 확인하여 동적으로 Error Latency 계산
- PTE 접근: 동적/정적 모드 선택 가능 (동적 모드에서는 PTW 모사)
- 데이터 접근: 동적 PTW (예: 5-level 기준 최대 1000 cycles)

### 요구사항 2: Page Fault Latency 분리 (4KB vs 2MB)

**목표:**
- PTE allocation (항상 4KB): minor_fault_penalty
- Data page allocation (4KB/2MB): data_page_fault_4kb_penalty / data_page_fault_2mb_penalty

---

## 구현 상세

### 1. 역방향 매핑 추가 (Physical Page → Virtual Page)

#### 파일: `inc/vmem.h`

**위치:** Line 42-44 (private 섹션)

**추가 내용:**
```cpp
private:
  std::map<std::pair<uint32_t, champsim::page_number>, champsim::page_number> vpage_to_ppage_map;
  std::map<std::pair<uint32_t, champsim::page_number>, champsim::page_number> ppage_to_vpage_map; // Reverse mapping for error latency calculation
  std::map<std::tuple<uint32_t, uint32_t, champsim::address_slice<champsim::dynamic_extent>>, champsim::address> page_table;
```

**위치:** Line 138-146 (public 섹션, 함수 선언)

**추가 내용:**
```cpp
  /**
   * Get the virtual page number for a given physical page number (reverse lookup).
   *
   * :param cpu_num: The cpu index of the core making the request.
   * :param paddr: The physical page number to look up.
   *
   * :returns: An optional containing the virtual page number if found, otherwise empty.
   */
  std::optional<champsim::page_number> get_vpage_for_ppage(uint32_t cpu_num, champsim::page_number paddr) const;
```

#### 파일: `src/vmem.cc`

**위치:** Line 122-127 (va_to_pa 함수 내부)

**수정 내용:**
```cpp
  if (fault) {
    ppage_pop();
    ErrorPageManager::get_instance().add_current_ppage(ppage->second); //Hamoci's Addition
    // Add reverse mapping for error latency calculation
    ppage_to_vpage_map[{cpu_num, ppage->second}] = champsim::page_number{vaddr};
  }
```

**위치:** Line 210-217 (파일 끝부분, 새 함수 구현)

**추가 내용:**
```cpp
std::optional<champsim::page_number> VirtualMemory::get_vpage_for_ppage(uint32_t cpu_num, champsim::page_number paddr) const
{
  auto it = ppage_to_vpage_map.find({cpu_num, paddr});
  if (it != ppage_to_vpage_map.end()) {
    return it->second;
  }
  return std::nullopt;
}
```

---

### 2. Page Fault Latency 분리 (4KB vs 2MB)

#### 파일: `inc/vmem.h`

**위치:** Line 47-52 (public 섹션)

**수정 내용:** (기존 단일 penalty를 3개로 분리)
```cpp
public:
  const champsim::chrono::clock::duration minor_fault_penalty;  // PTE allocation (always 4KB)
  const champsim::chrono::clock::duration data_page_fault_4kb_penalty;  // Data page allocation (4KB)
  const champsim::chrono::clock::duration data_page_fault_2mb_penalty;  // Data page allocation (2MB)
  const std::size_t pt_levels;
  const pte_entry pte_page_size; // Size of a PTE page
```

**위치:** Line 82-91 (생성자 선언)

**수정 내용:**
```cpp
  VirtualMemory(champsim::data::bytes page_table_page_size, std::size_t page_table_levels,
                champsim::chrono::clock::duration minor_penalty,
                champsim::chrono::clock::duration data_4kb_penalty,
                champsim::chrono::clock::duration data_2mb_penalty,
                MEMORY_CONTROLLER& dram_);
  VirtualMemory(champsim::data::bytes page_table_page_size, std::size_t page_table_levels,
                champsim::chrono::clock::duration minor_penalty,
                champsim::chrono::clock::duration data_4kb_penalty,
                champsim::chrono::clock::duration data_2mb_penalty,
                MEMORY_CONTROLLER& dram_, std::optional<uint64_t> randomization_seed_);
```

#### 파일: `src/vmem.cc`

**위치:** Line 28-54 (생성자 구현)

**수정 내용:**
```cpp
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
  // ... (나머지 동일)
}
```

**위치:** Line 56-63 (두 번째 생성자)

**수정 내용:**
```cpp
VirtualMemory::VirtualMemory(champsim::data::bytes page_table_page_size, std::size_t page_table_levels,
                             champsim::chrono::clock::duration minor_penalty,
                             champsim::chrono::clock::duration data_4kb_penalty,
                             champsim::chrono::clock::duration data_2mb_penalty,
                             MEMORY_CONTROLLER& dram_)
    : VirtualMemory(page_table_page_size, page_table_levels, minor_penalty, data_4kb_penalty, data_2mb_penalty, dram_, {})
{
}
```

**위치:** Line 129-138 (va_to_pa 함수 내부)

**수정 내용:**
```cpp
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
```

#### 파일: `config/instantiation_file.py`

**위치:** Line 26

**수정 내용:**
```python
vmem_fmtstr = 'champsim::data::bytes{{{pte_page_size}}}, {num_levels}, champsim::chrono::picoseconds{{{clock_period}*{minor_fault_penalty}}}, champsim::chrono::picoseconds{{{clock_period}*{data_page_fault_4kb}}}, champsim::chrono::picoseconds{{{clock_period}*{data_page_fault_2mb}}}, {dram_name}, {_randomization}'
```

#### 파일: `config/parse.py`

**위치:** Line 347

**수정 내용:**
```python
{ 'pte_page_size': int_or_prefixed_size("4kB"), 'num_levels': 5, 'minor_fault_penalty': 200, 'data_page_fault_4kb': 3956, 'data_page_fault_2mb': 109200, 'randomization': 1}
```

---

### 3. DRAM request에 access_type과 cpu 정보 추가

#### 파일: `inc/dram_controller.h`

**위치:** Line 93-95 (forward declarations 추가)

**추가 내용:**
```cpp
class VirtualMemory;
class PageTableWalker;
class CACHE;
```

**위치:** Line 98-118 (DRAM_CHANNEL::request_type 구조체)

**수정 내용:**
```cpp
  struct request_type {
    bool scheduled = false;
    bool forward_checked = false;

    uint8_t asid[2] = {std::numeric_limits<uint8_t>::max(), std::numeric_limits<uint8_t>::max()};

    uint32_t pf_metadata = 0;
    uint32_t cpu = std::numeric_limits<uint32_t>::max();

    access_type type{access_type::LOAD};

    champsim::address address{};
    champsim::address v_address{};
    champsim::address data{};
    champsim::chrono::clock::time_point ready_time = champsim::chrono::clock::time_point::max();

    std::vector<uint64_t> instr_depend_on_me{};
    std::vector<std::deque<response_type>*> to_return{};

    explicit request_type(const typename champsim::channel::request_type& req);
  };
```

**위치:** Line 100-105 (DRAM_CHANNEL 클래스 내부)

**추가 내용:**
```cpp
  const DRAM_ADDRESS_MAPPING address_mapping;

  // References for dynamic error latency calculation
  VirtualMemory* vmem = nullptr;
  std::vector<PageTableWalker*> ptws;
  std::vector<CACHE*> caches;
```

**위치:** Line 181-186 (DRAM_CHANNEL public 함수)

**추가 내용:**
```cpp
  void set_vmem(VirtualMemory* vm) { vmem = vm; }
  void set_ptws(std::vector<PageTableWalker*> p) { ptws = p; }
  void set_caches(std::vector<CACHE*> c) { caches = c; }

  // Calculate dynamic error latency for data access
  champsim::chrono::clock::duration calculate_dynamic_error_latency(uint32_t cpu_num, champsim::address paddr, std::optional<champsim::address> vaddr_hint = std::nullopt);
```

**위치:** Line 222-225 (MEMORY_CONTROLLER 클래스 내부)

**추가 내용:**
```cpp
  // References for dynamic error latency calculation
  VirtualMemory* vmem = nullptr;
  std::vector<PageTableWalker*> ptws;
  std::vector<CACHE*> caches;
```

**위치:** Line 241-243 (MEMORY_CONTROLLER public 함수)

**추가 내용:**
```cpp
  void set_vmem(VirtualMemory* vm) { vmem = vm; }
  void set_ptws(std::vector<PageTableWalker*> p) { ptws = p; }
  void set_caches(std::vector<CACHE*> c) { caches = c; }
```

#### 파일: `src/dram_controller.cc`

**위치:** Line 31-33 (헤더 추가)

**추가 내용:**
```cpp
#include "vmem.h"      // For dynamic error latency calculation
#include "ptw.h"       // For PSC access
#include "cache.h"     // For cache lookup
```

**위치:** Line 638-643 (request_type 생성자)

**수정 내용:**
```cpp
DRAM_CHANNEL::request_type::request_type(const typename champsim::channel::request_type& req)
    : pf_metadata(req.pf_metadata), cpu(req.cpu), type(req.type), address(req.address), v_address(req.v_address), data(req.data), instr_depend_on_me(req.instr_depend_on_me)
{
  asid[0] = req.asid[0];
  asid[1] = req.asid[1];
}
```

**위치:** Line 504-509 (MEMORY_CONTROLLER::initialize() 내부)

**추가 내용:**
```cpp
  // Set references for dynamic error latency calculation
  for (auto& chan : channels) {
    chan.set_vmem(vmem);
    chan.set_ptws(ptws);
    chan.set_caches(caches);
  }
```

**위치:** Line 662-720 (새 함수 구현)

**추가 내용:**
```cpp
champsim::chrono::clock::duration DRAM_CHANNEL::calculate_dynamic_error_latency(uint32_t cpu_num, champsim::address paddr, std::optional<champsim::address> vaddr_hint = std::nullopt)
{
  // Check if references are available
  if (!vmem || ptws.empty() || caches.empty() || cpu_num >= ptws.size()) {
    // Fallback to fixed latency if references not available
    return ErrorPageManager::get_instance().get_error_latency();
  }

  // Get physical page number
  champsim::page_number ppage{paddr};

  // Reverse lookup: physical page → virtual page
  auto vpage_opt = vmem->get_vpage_for_ppage(cpu_num, ppage);
  if (!vpage_opt.has_value()) {
    // If no mapping found, use fixed latency
    return ErrorPageManager::get_instance().get_error_latency();
  }

  champsim::page_number vpage = vpage_opt.value();
  champsim::address vaddr{vpage};
  PageTableWalker* ptw = ptws[cpu_num];

  // Check PSC to determine starting level
  std::size_t start_level = vmem->pt_levels;
  auto psc_level = ptw->get_psc_cached_level(vaddr);
  if (psc_level.has_value()) {
    // PSC hit: start from the cached level (skip higher levels)
    start_level = psc_level.value();
  }

  // Calculate latency for each page table level
  // Start from PSC-determined level down to level 1
  champsim::chrono::clock::duration total_latency = champsim::chrono::clock::duration::zero();
  const champsim::chrono::clock::duration DRAM_LATENCY = 200 * clock_period;

  for (std::size_t level = start_level; level > 0; --level) {
    // Probe only existing PTE state (read-only)
    auto pte_paddr = vmem->get_pte_pa_if_present(cpu_num, vpage, level);
    if (!pte_paddr.has_value()) {
      total_latency += DRAM_LATENCY;
      continue;
    }

    // Order-independent cache hierarchy check
    champsim::chrono::clock::duration level_latency = DRAM_LATENCY;

    for (CACHE* cache : caches) {
      if (cache->is_address_in_cache(*pte_paddr)) {
        level_latency = std::min(level_latency, cache->HIT_LATENCY);
      }
    }

    total_latency += level_latency;
  }

  return total_latency;
}
```

**위치:** Line 370-378 (RANDOM 모드 에러 처리)

**수정 내용:**
```cpp
      // RANDOM mode: BER-based error check
      if (ErrorPageManager::get_instance().get_mode() == ErrorPageManagerMode::RANDOM &&
          ErrorPageManager::get_instance().check_page_error()) {
        // Select latency based on access type
        if (pkt->value().type == access_type::TRANSLATION) {
          // PTE access: use simplified model (levels × 150)
          error_latency = ErrorPageManager::get_instance().get_pte_error_latency();
        } else {
          // Data access: use dynamic PTW latency calculation
          error_latency = calculate_dynamic_error_latency(pkt->value().cpu, pkt->value().address);
        }
        ErrorPageManager::get_instance().record_error_access();
```

**위치:** Line 400-408 (CYCLE 모드 에러 처리)

**수정 내용:**
```cpp
        // Cache Pinning 비활성화 또는 새로운 캐시 라인일 때 latency 부여
        if (!already_registered) {
          // Select latency based on access type
          if (pkt->value().type == access_type::TRANSLATION) {
            // PTE access: use simplified model (levels × 150)
            error_latency = ErrorPageManager::get_instance().get_pte_error_latency();
          } else {
            // Data access: use dynamic PTW latency calculation
            error_latency = calculate_dynamic_error_latency(pkt->value().cpu, pkt->value().address);
          }
        }
```

---

### 4. ErrorPageManager에 PTE error latency 추가

#### 파일: `inc/error_page_manager.h`

**위치:** Line 30-31 (private 멤버)

**추가 내용:**
```cpp
    champsim::chrono::clock::duration error_latency_penalty{};
    champsim::chrono::clock::duration pte_error_latency_penalty{};
```

**위치:** Line 93-97 (public 함수)

**추가 내용:**
```cpp
    // Latency management
    void set_error_latency(champsim::chrono::clock::duration latency) { error_latency_penalty = latency; }
    champsim::chrono::clock::duration get_error_latency() const { return error_latency_penalty; }
    void set_pte_error_latency(champsim::chrono::clock::duration latency) { pte_error_latency_penalty = latency; }
    champsim::chrono::clock::duration get_pte_error_latency() const { return pte_error_latency_penalty; }
```

#### 파일: `config/defaults.py`

**위치:** Line 95-103

**수정 내용:**
```python
def error_page_manager_defaults():
    ''' Generate the default error page manager configuration '''
    return {
        'mode': 'OFF',
        'error_latency_penalty': 0,
        'pte_error_latency_penalty': 0,
        'bit_error_rate': 0.0,
        'errors_per_interval': 1,
        'error_cycle_interval': 0,
        'cache_pinning': False
    }
```

#### 파일: `config/instantiation_file.py`

**위치:** Line 410-411 (error_page_manager 설정 부분)

**추가 내용:**
```python
    if 'pte_error_latency_penalty' in error_page_manager:
        yield f'  epm.set_pte_error_latency(champsim::chrono::picoseconds{{{error_page_manager["pte_error_latency_penalty"] * global_clock_period}}});'
```

**위치:** Line 432-442 (생성자 끝 부분)

**추가 내용:**
```python
    # Set DRAM references for dynamic error latency calculation
    yield ''
    yield '  // Set DRAM references for dynamic error latency calculation'
    yield '  std::vector<PageTableWalker*> ptw_ptrs;'
    yield '  for (auto& ptw : ptws) { ptw_ptrs.push_back(&ptw); }'
    yield '  std::vector<CACHE*> cache_ptrs;'
    yield '  for (auto& cache : caches) { cache_ptrs.push_back(&cache); }'
    yield '  DRAM.set_vmem(&vmem);'
    yield '  DRAM.set_ptws(ptw_ptrs);'
    yield '  DRAM.set_caches(cache_ptrs);'
    yield '}'
```

---

### 5. lru_table에 peek() 함수 추가

#### 파일: `inc/msl/lru_table.h`

**위치:** Line 168-180 (invalidate() 함수 이후)

**추가 내용:**
```cpp
  // Read-only check without updating LRU state
  // Returns the cached value if found, otherwise std::nullopt
  std::optional<value_type> peek(const value_type& elem) const
  {
    auto [set_begin, set_end] = const_cast<lru_table*>(this)->get_set_span(elem);
    auto hit = std::find_if(set_begin, set_end, const_cast<lru_table*>(this)->match_func(elem));

    if (hit == set_end) {
      return std::nullopt;
    }

    return hit->data;
  }
```

---

### 6. PTW에 PSC helper 함수 추가

#### 파일: `inc/ptw.h`

**위치:** Line 101-104 (public 함수 선언)

**추가 내용:**
```cpp
  // Helper function for dynamic error latency calculation
  // Returns the lowest cached level in PSC for the given virtual address
  // Returns std::nullopt if no level is cached
  [[nodiscard]] std::optional<std::size_t> get_psc_cached_level(champsim::address vaddr) const;
```

#### 파일: `src/ptw.cc`

**위치:** Line 244-270 (파일 끝 부분)

**추가 내용:**
```cpp
std::optional<std::size_t> PageTableWalker::get_psc_cached_level(champsim::address vaddr) const
{
  std::optional<std::size_t> lowest_level;

  // Check each PSC level for this virtual address
  for (const auto& pscl_cache : pscl) {
    // Create a dummy entry with the virtual address we're looking for
    // The level field will be checked when we find a match
    pscl_entry dummy_entry{vaddr, champsim::address{}, vmem->pt_levels};

    // Use peek() for read-only check (doesn't update LRU state)
    auto cached = pscl_cache.peek(dummy_entry);

    if (cached.has_value()) {
      // Found a match in this PSC level
      std::size_t cached_level = cached.value().level;

      // Track the lowest (most specific) level found
      if (!lowest_level.has_value() || cached_level < lowest_level.value()) {
        lowest_level = cached_level;
      }
    }
  }

  return lowest_level;
}
```

---

### 7. CACHE에 helper 함수 추가

#### 파일: `inc/cache.h`

**위치:** Line 332-334 (public 섹션)

**추가 내용:**
```cpp
  // Helper function for dynamic error latency calculation
  // Returns true if the given address is present in this cache (read-only check)
  [[nodiscard]] bool is_address_in_cache(champsim::address addr) const;
```

#### 파일: `src/cache.cc`

**위치:** Line 897-906 (initialize() 함수 이전)

**추가 내용:**
```cpp
bool CACHE::is_address_in_cache(champsim::address addr) const
{
  auto [set_begin, set_end] = get_set_span(addr);
  auto target = addr.slice_upper(OFFSET_BITS);
  for (auto it = set_begin; it != set_end; ++it) {
    if (it->valid && it->address.slice_upper(OFFSET_BITS) == target) {
      return true;
    }
  }
  return false;
}
```

---

### 8. Config 파일 예시

#### 파일: `sim_configs/only_for_test/_2MBLLC_2MBPage_DRAM_Error_1e-8.json`

**위치:** Line 182-197

**설정 예시:**
```json
  "virtual_memory": {
    "pte_page_size": 4096,
    "num_levels": 4,
    "minor_fault_penalty": 3956,
    "data_page_fault_4kb": 3956,
    "data_page_fault_2mb": 109201,
    "randomization": 1
  },

  "error_page_manager": {
    "mode": "CYCLE",
    "error_latency_penalty": 800,
    "pte_error_latency_penalty": 600,
    "error_cycle_interval": 144000,
    "cache_pinning": true,
    "dynamic_error_latency": true
  }
```

---

## 동작 방식

### 에러 발생 시 처리 흐름

1. **DRAM에서 에러 감지** (dram_controller.cc:service_packet)

2. **Access Type 확인 + 모드 확인**
   - `dynamic_error_latency = true`
     - `TRANSLATION`과 데이터 access 모두 동적 경로 사용
     - `TRANSLATION`은 `v_address` hint를 우선 사용해 PTW 근사
   - `dynamic_error_latency = false`
     - `TRANSLATION` → `pte_error_latency_penalty`
     - 데이터 access → `error_latency_penalty`

### calculate_dynamic_error_latency() 상세 동작

```
Step 1: Physical Page → Virtual Page 역매핑 (또는 hint 사용)
  - 기본: vmem->get_vpage_for_ppage(cpu_num, ppage)
  - TRANSLATION 경로: DRAM request의 vaddr hint 우선 사용

Step 2: PSC 확인하여 시작 level 결정
  - ptw->get_psc_cached_level(vaddr)
  - PSC Hit at Level 3 → start_level = 3 (Level 4 skip)
  - PSC Hit at Level 2 → start_level = 2 (Level 4,3 skip)
  - PSC Miss → start_level = 4 (모든 level 탐색)

Step 3: 각 Page Table Level 탐색 (start_level → 1)
  For each level:
    3a. PTE Physical Address 계산
        - vmem->get_pte_pa_if_present(cpu_num, vpage, level)
        - 존재하지 않으면 해당 level은 DRAM miss로 처리 (+200 cycles)

    3b. 모든 Cache에서 PTE 검색
        For each cache:
          - cache->is_address_in_cache(pte_paddr)
          - Hit → level_latency = min(level_latency, cache->HIT_LATENCY)
          - Cache 순서와 무관하게 최소 hit latency 선택

    3c. Cache Miss 처리
        - level_latency = 200 * cpu_clock_period (DRAM latency model)

    3d. Total에 누적
        - total_latency += level_latency

Step 4: Total Latency 반환
  - return total_latency
```

### Latency 범위

**최소 (~100 cycles):**
- PSC Hit at Level 2
- 모든 PTE가 L1D Cache에 있음
- 2 levels × ~5 cycles (L1D latency) = ~10 cycles
- + PSC overhead

**최대 (예: ~1000 cycles):**
- PSC Miss (최상위 level부터 시작)
- 모든 PTE가 DRAM에 있음
- 5 levels × 200 cycles = 1000 cycles (pt_levels=5 설정 예시)

**실제:**
- PSC와 Cache 상태, 그리고 `pt_levels` 설정에 따라 동적 변화
- 워크로드와 메모리 접근 패턴에 따라 달라짐

---

## 핵심 설계 원칙

### 1. Read-Only 접근
- 모든 helper 함수는 read-only
- PSC: `peek()` 사용 (LRU 상태 변경 안함)
- Cache: `is_address_in_cache()` 사용 (const 함수)
- PTE 조회: `get_pte_pa_if_present()` 사용 (page table 상태 변경 없음)

### 2. Fallback 메커니즘
- 참조가 없거나 실패 시 고정값 사용
- `ErrorPageManager::get_instance().get_error_latency()` 반환

### 3. 모듈화
- 각 컴포넌트에 독립적인 helper 함수
- lru_table, PTW, CACHE 각각 독립적

### 4. 확장성
- 새로운 Cache level 추가 가능
- 새로운 access_type 추가 가능

---

## 테스트 및 검증

### 빌드 확인
```bash
cd /home/hamoci/Study/ChampSim
./build_only_for_test.sh
```

### 실행 확인
- 에러 발생 시 latency가 동적으로 계산되는지 확인
- PSC Hit/Miss 시나리오 테스트
- Cache Hit/Miss 조합 테스트

```bash
cd /home/hamoci/Study/ChampSim
./run_only_for_test_du_sh_trace.sh
```

---

## 참고사항

### PTE vs 데이터 구분 이유

**PTE 접근 (access_type::TRANSLATION):**
- PTE 자체에 에러 발생
- 동적 모드(`dynamic_error_latency=true`)에서는 `v_address` hint를 사용해 동적 PTW 근사 수행
- 정적 모드(`dynamic_error_latency=false`)에서는 `pte_error_latency_penalty` 사용

**데이터 접근:**
- 일반 데이터 페이지에 에러 발생
- 가상 주소 존재 (역매핑 가능)
- PTW 수행 가능
- 동적 모드에서는 PSC + Cache 상태 기반
- 정적 모드에서는 `error_latency_penalty` 사용

### 성능 고려사항

- 역매핑: O(log n) map lookup
- PSC 조회: O(PSC_LEVELS × WAYS)
- Cache 조회: O(CACHE_COUNT × WAY)
- 전체: 매우 낮은 오버헤드 (에러 발생 시에만 실행)

---

## 2026-02-13 추가 반영

### 구현 상세 (실행 경로)

### DRAM 에러 처리 분기 (`src/dram_controller.cc:service_packet`)

1. 에러 트리거
- `RANDOM`: BER 기반 `check_page_error()`
- `CYCLE`: `consume_cycle_error()`

2. 캐시 핀닝 등록
- `cache_pinning=true`면 `aligned_addr = addr >> 6` 기준으로 등록/중복 확인
- `already_registered=true`면 해당 요청의 추가 latency는 생략 가능

3. latency 선택
- `dynamic_error_latency=true`
  - `calculate_dynamic_error_latency(cpu, paddr, vaddr_hint)` 호출
- `dynamic_error_latency=false`
  - `type=TRANSLATION` -> `pte_error_latency_penalty`
  - 그 외 -> `error_latency_penalty`

4. 통계 및 로그
- `record_error_access()`로 총 에러 이벤트 누적
- `[ERROR_OCCUR]`:
  - `Total Errors`: 누적 에러 이벤트 수
  - `PinnedLines`: 64B line 기준 고유 등록 수

### 동적 PTW latency 계산 (`calculate_dynamic_error_latency`)

1. `vaddr_hint`가 있으면 우선 사용 (`type=TRANSLATION` 경로에서 주로 사용)
2. 없으면 reverse-map으로 `paddr -> vpage` 조회
3. PSC 조회로 `start_level` 결정
4. 각 level에 대해 read-only probe
- cache hit: 최소 `HIT_LATENCY` 채택
- cache miss/unmapped: `+200 CPU cycles`
5. 누적 latency 반환

### 단위(중요)

- config의 latency/interval은 **cycle** 단위로 입력
- 내부 duration은 `global_clock_period`를 곱해 `picoseconds`로 저장
- 디버그 로그 출력은 CPU cycle 기준으로 정규화

### PSC 레벨 매핑 보정 (중요 수정)

배경:
- 기존에는 PSC hit 레벨 해석이 PTW 내부 상대 레벨과 혼동될 여지가 있어, `start_level`이 비정상적으로 낮게 고정되는 현상이 관찰됨.

수정 파일:
- `inc/ptw.h`
- `src/ptw.cc`
- `src/dram_controller.cc`

수정 내용:
1. `PageTableWalker`에 `pscl_levels`(absolute PT level 매핑) 추가
- `pscl` 벡터 인덱스와 동일한 순서로 실제 PT level(`5/4/3/2`) 보관

2. `get_psc_cached_level()` 반환값 보정
- 기존: cached entry의 internal level을 그대로 사용
- 수정: `pscl_levels[idx]`를 우선 사용해 **absolute PT level** 반환

3. DRAM 동적 경로 방어 로직 추가
- `start_level`을 `[1, pt_levels]` 범위로 clamp
- PSC 로그에 `pt_levels` 동시 출력

효과:
- 2MB/4KB 구성 모두에서 PSC 결과가 absolute level 기준으로 해석됨
- `start_level`이 내부 상대 레벨로 잘못 고정되는 가능성 제거

### PTW-PSC 디버그 로그 추가

수정 파일:
- `src/ptw.cc`

스위치:
- `debug_ptw_psc` (`true/false` 직접 코드 수정)

출력 항목:
- `handle_read` 시 PSC miss/hit(레벨별)와 선택된 internal 시작 레벨
- `handle_fill` 시 어느 PSC 인덱스/레벨이 채워졌는지
- `get_psc_cached_level` query 결과(히트 인덱스/absolute level/최종 반환값)

해석 포인트:
- 에러 로그(`[ERR_LAT]`)의 PSC miss가 0이어도, PTW 전체에서 miss가 없다는 뜻은 아님
- 에러는 샘플링된 접근에서만 동적 계산 로그를 찍으므로, PSC warm-up 이후에는 hit 위주로 보일 수 있음
- PTW_PSC 로그로 “초기 miss -> fill -> 이후 hit” 흐름을 직접 검증 가능

---

### 운영 기준

### 1) 최신 스크립트 구성

- 통합 빌드 스크립트: `build_only_for_test.sh`
- 통합 실행 스크립트: `run_only_for_test_du_sh_trace.sh`
- 실행 스크립트는 `MAX_PARALLEL=4`로 4개 바이너리를 병렬 실행

### 2) 에러 로그 해설 (실전 확인용)

- `[ERR_LAT][CYCLE|RANDOM][DYNAMIC|FIXED] ...`
  - 에러 latency가 실제로 얼마로 적용되었는지 출력
  - `DYNAMIC`: PTW/PSC/cache 상태 기반 계산
  - `FIXED`: config penalty 고정값 적용

- `[ERR_LAT] begin emulate_ptw ... hint_vaddr=yes|no`
  - 동적 PTW 근사 계산 시작
  - `hint_vaddr=yes`: TRANSLATION 경로처럼 `v_address` 힌트를 직접 사용
  - `hint_vaddr=no`: reverse-map(`paddr -> vpage`) 경로 사용

- `[ERR_LAT] PSC hit|miss -> start_level=...`
  - PSC 결과로 PTW 시작 level 결정

- `[ERR_LAT] level ... cache hit(...) | cache miss -> DRAM (+200)`
  - 각 level별 지연 누적 과정

- `[ERR_LAT] final dynamic error latency=... cycles`
  - 최종 동적 latency 결과

- `[ERROR_OCCUR] Address ... Aligned ... (Total Errors: N) ... (PinnedLines: M)`
  - `Total Errors`: 실제 누적 에러 이벤트 수
  - `PinnedLines`: 64B cacheline 기준으로 등록된 고유 line 수
  - `(already registered)`는 에러가 없다는 뜻이 아니라, 이미 등록된 line이라는 뜻

- `[ERROR_WAY_ALLOC] Address ... Set ... Way ...`
  - LLC fill 단계에서 error line이 Error Way에 배치되었음을 의미
  - DRAM 에러 발생 로그와 시점이 다르므로 1:1로 바로 붙지 않아도 정상

### 3) `type=` 필드 의미

- `LOAD`: 일반 load 읽기
- `RFO`: write를 위한 ownership 획득 read (Read For Ownership)
- `PREFETCH`: prefetch 요청
- `WRITE`: writeback/쓰기 경로
- `TRANSLATION`: PTW/PTE 관련 접근

### 4) 현재 알려진 운영상 주의점

- `panic: IPC < ...` 메시지는 현재 경고 성격이며 즉시 종료 조건은 아님
- baseline(특히 2MB + fixed 큰 penalty)에서는 wall-clock 시간이 매우 길어질 수 있음
- CYCLE/FIT 유사 모델 특성상, Error Latency 증가로 elapsed cycle이 길어지면 같은 trace에서도 누적 error 개수가 더 많이 관측될 수 있음

---

## 2026-02-14 추가 반영

### 1) Debug 출력 운영 모드 정리

본실험용으로 기본 debug 출력을 모두 OFF로 변경:
- `src/dram_controller.cc`
  - `debug_dynamic_error_latency = false`
  - `[ERROR_OCCUR]` 출력용 local `debug_mode = false`
- `src/ptw.cc`
  - `debug_ptw_psc = false`
- `src/cache.cc`
  - pinning/eviction/LRU 관련 local `debug_mode = false`

주의:
- heartbeat의 `total_errors` 출력은 유지됨 (`src/ooo_cpu.cc`).

### 2) `real_final` config 트리 구성

원본 보존 원칙:
- `sim_configs/final_rev`는 수정하지 않음
- 실험용은 `sim_configs/real_final`에서만 관리

복사/구성:
- 포함: `error_hugepage`, `no_error_hugepage`
- 제외: `cache_sensitive`

### 3) `real_final/error_hugepage` 일괄 규칙

공통:
- PTW `lower_level` = `cpu0_L1D`
- `virtual_memory`:
  - `minor_fault_penalty = 3956`
  - `data_page_fault_4kb = 3956`
  - `data_page_fault_2mb = 109201`

PSC 레벨:
- 4KB Page: `pscl5/4/3/2 = (1,2)/(1,4)/(2,4)/(4,8)`
- 2MB Page: `pscl4/3/2 = (1,4)/(2,4)/(4,8)` (`pscl5` 제거)

error latency + mode 매핑 (only_for_test 기준):
- 4KB + cache_pinning:
  - `error_latency_penalty = 1000`
  - `pte_error_latency_penalty = 800`
  - `cache_pinning = true`, `dynamic_error_latency = true`
- 4KB + no_cache_pinning:
  - `error_latency_penalty = 16484`
  - `pte_error_latency_penalty = 16484`
  - `cache_pinning = false`, `dynamic_error_latency = false`
- 2MB + cache_pinning:
  - `error_latency_penalty = 800`
  - `pte_error_latency_penalty = 600`
  - `cache_pinning = true`, `dynamic_error_latency = true`
- 2MB + no_cache_pinning:
  - `error_latency_penalty = 454568`
  - `pte_error_latency_penalty = 16484`
  - `cache_pinning = false`, `dynamic_error_latency = false`

### 4) `real_final/no_error_hugepage` 보정

`mode: OFF` 유지하되 `virtual_memory`는 최신 기준으로 통일:
- `minor_fault_penalty = 3956`
- `data_page_fault_4kb = 3956`
- `data_page_fault_2mb = 109201`

참고:
- `mode: OFF`여도 page-fault penalty 선택(4KB/2MB)은 `vmem.cc::va_to_pa()`에서 PAGE_SIZE 기준으로 독립 적용됨.

### 5) 실험 자동화 스크립트

추가:
- `build_real_final.sh`
  - `sim_configs/real_final` 하위 모든 json 순회
  - 각 config마다 `./config.sh` 후 `make -j$(nproc)`

- `run_real_final_spec.sh`
  - SPEC trace만 사용: `test_traces/6*.champsimtrace.xz`
  - 실행 대상 config 필터:
    1. `no_cache_pinning`에서는 `1e-9` 제외 (4KB/2MB 공통)
    2. `no_cache_pinning + 2MBPage`에서는 `1e-8`도 제외
  - 필터된 config에서 `executable_name` 추출 후 `binary x trace` 조합 실행
  - 결과 저장: `results/real_final_spec/${binary}_${trace}.txt`
  - `MAX_PARALLEL`로 병렬 수 제어 (기본 4)
  - 전체 실험 종료 후 총 elapsed time 출력

### 6) 병렬 실행 이슈 수정

현상:
- `run_real_final_spec.sh`가 1개만 실행하고 종료되는 문제

원인:
- `set -e` 환경에서 `((running_jobs++))`가 초기값 0일 때 exit code 1을 반환

수정:
- `running_jobs=$((running_jobs + 1))`로 변경

결과:
- 설정한 `MAX_PARALLEL`만큼 정상 병렬 실행

---

## 작성자 노트

이 구현은 다음을 목표로 설계되었습니다:

1. **정확성**: 실제 HW PTW 동작을 최대한 모델링
2. **효율성**: Read-only 접근으로 시뮬레이션 상태 변경 최소화
3. **유지보수성**: 각 모듈이 독립적이고 명확한 인터페이스
4. **확장성**: 향후 추가 기능 통합 용이

이 문서는 향후 llc-pinning skill에 통합될 예정입니다.
