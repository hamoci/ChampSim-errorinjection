# LLC Pinning Implementation Status

Last updated: 2026-03-19

## Overview

ChampSim 시뮬레이터에서 LLC Pinning을 구현하는 프로젝트.
Hardware-based LLC Pinning architecture로, 2MB huge page에서 memory error를 64B cache line 단위로 격리한다.
CE 감지 시 HW PTW로 PDE counter를 갱신하고, ETT bloom filter에 error position을 기록하며, 이후 LLC fill 시 bloom filter를 조회하여 error way에 pin한다.

---

## Architecture

### 설계 핵심 원칙

1. **CE 감지와 LLC Pinning을 분리한다** — CE 감지 시점에는 기록만, 실제 pinning은 이후 LLC fill 시 수행
2. **OS를 최대한 거치지 않는다** — CE 감지 시 HW PTW로 직접 PDE counter를 갱신 (OS 개입 없음)
3. **MC → LLC controller 간 별도 pin 신호가 필요 없다** — CE 감지 시 MC는 기존 data 반환 경로에 CE_flag(1bit)를 태울 뿐
4. **기존 cache hierarchy의 동작 흐름을 최소한으로 수정한다**
5. **완벽한 시스템을 설계하지 않는다** — threshold 기반으로 합리적 시점에 retirement

### Building Blocks

| 자원 | 위치 | 역할 | 접근 빈도 |
|---|---|---|---|
| PDE counter (6bit) | Page table → TLB에 캐싱 | Per-page CE count + threshold 판단 + ETT lookup trigger | 매 TLB lookup마다 (읽기), CE 감지 시 (쓰기) |
| ETT (Error Tracking Table) | LLC controller 내부 SRAM | Bloom filter 기반 error cache line 위치 판별 | PDE counter > 0인 page에서 LLC fill 시 |
| ECT (Error Counter Table) | MC 내부 SRAM | Physical page별 CE counter의 persistent 저장소 | CE 감지 시 EDAC 경로로 갱신, page 할당 시 lookup |
| LLC error way | LLC | Pin된 error cache line의 정상 data 저장 | Pin 이후 해당 주소 접근 시 (LLC hit) |

### Hardware Overhead

| 구성 요소 | 크기 (m=256) | 크기 (m=512) | 위치 |
|---|---|---|---|
| ETT (64 entries) | ~2.2KB | ~4.2KB | LLC controller 내부 SRAM |
| ECT (1024 entries × ~4B) | ~4KB | ~4KB | MC 내부 SRAM |
| LLC error way | 기존 LLC way 재활용 | 기존 LLC way 재활용 | LLC (제어 로직만 추가) |
| PDE counter (6bit) | 기존 ignored bit 재활용 | 기존 ignored bit 재활용 | Page table (추가 면적 없음) |
| **총 SRAM overhead** | **~6.2KB** | **~8.2KB** | |

---

## Implementation Details

### 1. ETT (Error Tracking Table) — Bloom Filter 기반

**파일**: `inc/error_page_manager.h`, `src/error_page_manager.cc`

ETT는 2MB page 단위로 error cache line의 위치를 bloom filter로 추적한다.

**구조체:**
- `ETTEntry`: tag(page base PA) + bloom_filter(m bits) + lru_counter + valid
- `H3Hash`: k개의 독립 hash 함수, XOR 기반 random bit matrix (seed 54321 고정, 재현 가능)
- `page_error_counters`: `unordered_map<uint64_t, uint8_t>` — page별 CE count

**핵심 동작:**
- `record_error(pa)`: bloom filter로 duplicate check → counter++ → bloom filter insert → threshold 도달 시 retirement
- `is_error_position(pa)`: counter==0 fast path + bloom filter query (LLC fill 시 pin 판단에 사용)
- `retire_page()`: counter 제거 + ETT entry clear + LLC sweep 큐잉

**ETT Eviction (LRU):**
- ETT가 꽉 차면 LRU entry를 evict
- Eviction 시 bloom filter만 유실, `page_error_counters`는 유지
- 이미 LLC error way에 pin된 cache line은 그대로 남음 (lazy) — error way hit으로 보호 지속
- 해당 page에 다시 error 발생 시 ETT entry 재할당, bloom filter 0부터 재구축
- LRU가 적합한 이유: 오래 접근 안 된 page는 LLC에서도 evict되었을 가능성이 높아 bloom filter 유지 가치가 낮음

### 2. LLC Error Way 할당 및 Pinning

**파일**: `src/cache.cc`, `inc/cache.h`

LLC의 high index way (way 15 → 14 → 13...)를 error way로 전용 할당하여 error data를 pin한다.

**핵심 동작:**
- `handle_fill()`: `is_cache_pinning_enabled() && is_error_data(addr)` 조건에서 error way에 fill
- `find_error_way()`: 4단계 탐색 — (1) 첫 error way 할당 (2) 빈 슬롯 찾기 (3) way 확장 (4) LRU victim eviction
- `find_normal_way()`: error way를 제외한 범위에서 일반 replacement policy 적용
- `is_error_data()`: `page_error_counter > 0` fast path + `ett_query()` bloom filter

**LLC Error Way 포화 시:**
- 같은 set에서 모든 error way가 valid → `find_error_victim()`으로 LRU eviction
- `max_error_ways_per_set`에 도달하면 확장 불가, LRU victim 선택으로 처리
- Invalidated slot (retirement sweep 후)은 바로 재사용 가능 (`find_if_not(valid)`)

### 3. Page Retirement 및 LLC Sweep

**파일**: `src/error_page_manager.cc`, `src/cache.cc`

CE count가 threshold에 도달하면 page retirement을 수행한다. Page migration을 에뮬레이션하여 해당 page의 모든 tracking을 초기화한다.

**Retirement 절차:**
1. `page_error_counters` 삭제 (counter 초기화)
2. ETT entry clear (bloom filter 초기화)
3. `pending_retirement_pages`에 page_base 큐잉
4. LLC `operate()`에서 `invalidate_page_error_ways()` 호출 — error way만 sweep하여 해당 page의 pin된 cache line invalidate (no writeback)

**Bloom filter에서 exact position을 추출할 수 없으므로**, retirement 시 error way 전체를 page boundary 기반으로 sweep한다. Error way 수 × NUM_SET 비교이지만 retirement는 드문 이벤트이므로 overhead 무시 가능.

### 4. Error Latency 모델

**파일**: `src/dram_controller.cc`

CE 감지 시 HW PTW로 PDE counter를 갱신하는 비용을 모델링한다. OS를 거치지 않고 HW가 직접 PTW를 수행하므로, PSC/cache hit 여부에 따라 latency가 결정된다.

| Error Case | Latency | 의미 |
|---|---|---|
| FIRST_ERROR / ADDED_ERROR | Dynamic PTW (4~35 cycles) | CE 감지 → HW PTW로 PDE counter++ 비용 (PSC/cache 상태 의존) |
| ALREADY_KNOWN | 0 cycles | bloom filter hit으로 이미 기록된 position, 추가 작업 없음 |
| PAGE_RETIRED | 454,568 cycles | 2MB page migration 비용 (TLB shootdown + data migration) |

**Dynamic latency**: `calculate_dynamic_error_latency()`가 PSC hit 여부, 각 page table level의 cache hit/miss를 확인하여 PTW 비용을 산출. PSC miss면 DRAM까지 접근하므로 200+ cycles.

### 5. Config 시스템

**파일**: `config/defaults.py`, `config/instantiation_file.py`

모든 ETT/pinning 파라미터는 JSON config에서 설정 가능하며, sensitivity sweep을 위해 설계됨.

```json
"error_page_manager": {
    "mode": "CYCLE",
    "error_cycle_interval": 144000,
    "cache_pinning": true,
    "dynamic_error_latency": true,
    "error_latency_penalty": 454568,
    "ett_entries": 64,
    "bloom_filter_size": 256,
    "bloom_filter_k": 4,
    "retirement_threshold": 32,
    "max_error_ways_per_set": 8,
    "baseline_retirement_threshold": 6
}
```

| 파라미터 | 기본값 | 역할 | Sweep 범위 |
|---|---|---|---|
| `cache_pinning` | false | LLC pinning 전체 on/off | true/false |
| `ett_entries` | 64 | ETT entry 수 | 32/64/128 |
| `bloom_filter_size` | 256 | Bloom filter bit 수 (m) | 128/256/512 |
| `bloom_filter_k` | 4 | Hash 함수 수 | 2/3/4/5 |
| `retirement_threshold` | 32 | Page retirement CE 임계값 | 16/32/64 |
| `max_error_ways_per_set` | 8 | Set당 최대 error way 수 | 1/2/4/8 |
| `dynamic_error_latency` | true | Dynamic PTW latency on/off | true/false |
| `error_latency_penalty` | 454568 | Retirement latency (cycles) | - |

**`cache_pinning: false`일 때**: ETT/bloom filter/error way 전체가 비활성화됨. DRAM controller에서 `record_error()` 대신 `record_baseline_error()`만 호출하여 단순 page 단위 retirement만 수행.

### 6. ECT (Error Counter Table) — 구조만 추가

**파일**: `inc/error_page_manager.h`

`ECTEntry` struct (tag + counter + valid, 1024 entries)가 정의됨. 실제 동작 연동은 후속 작업. 논문 completeness를 위한 구조.

---

## Verification Results

### 검증 1: ETT 기본 동작 (2026-03-19)

**Config**: ett_entries=64, bloom_filter_size=256, k=4, retirement_threshold=32, max_error_ways=8
**Trace**: `du_sh_trace.chamsim` (짧은 trace, 빠른 검증용)

**검증 항목 및 결과:**

- **Bloom filter insert/query**: H3 hash가 cl_index에서 k=4개의 bit position을 생성하고, insert 시 해당 bit 설정, query 시 모든 bit 확인. 로그로 bit position과 before/after 상태 확인 완료
- **Counter 증가**: 0→1→2→...→32까지 정확히 1씩 증가, threshold 도달 시 retirement 트리거
- **Retirement**: page 0x2c1000000이 count=32에서 정상 retire. ETT entry clear (100/256 bits → 0), counter 삭제, LLC sweep 실행
- **LLC sweep**: error way [14-16) 범위에서 68개 cache line invalidate (31개 unique error + bloom filter false positive로 추가 pin된 정상 cache line)
- **통계 일관성**: First(10) + Added(44) + Retirement(1) + AlreadyKnown(0) = Total(55) ✅
- **Error way slot 수**: retirement 후 23개 = 전체 54개 recording - retired page의 31개. 정확히 일치

### 검증 2: ETT/LLC 포화 시 동작 (2026-03-19)

**Config**: ett_entries=**4**, max_error_ways=**1** (강제 포화)

**ETT 포화:**
- 4/4 entry가 차면 LRU eviction 발생 (5회 확인)
- Evict된 page의 counter는 유지, bloom filter만 유실
- Evict된 page의 이미 pin된 cache line은 LLC error way에 그대로 남음 (lazy)

**LLC error way 포화:**
- max=1이므로 way 15만 사용, 같은 set에 충돌 시 LRU victim eviction 발생 (1회 확인)
- EXPAND 로그 없음 = max 제한 정상 동작
- Invalidated slot은 바로 재사용 (retirement 후 ALLOC/EXPAND 없이 빈 슬롯 활용)

### 검증 3: Pinning ON/OFF 분리 (2026-03-19)

`cache_pinning: true`일 때만 ETT/bloom filter/error way가 동작하는지 코드 경로 확인:

| 위치 | Guard | 상태 |
|---|---|---|
| DRAM `record_error()` 호출 | `is_cache_pinning_enabled()` | ✅ |
| DRAM pinning OFF 경로 | `record_baseline_error()` | ✅ |
| cache.cc `handle_fill` pin 분기 | `is_cache_pinning_enabled()` | ✅ |
| cache.cc error way timestamp | `is_cache_pinning_enabled()` | ✅ |
| cache.cc LLC sweep | `is_cache_pinning_enabled()` | ✅ (방어적 가드 추가) |
| `is_error_data()` | 호출부에서 가드 | ✅ |

### 검증 4: Error Latency 적용 (2026-03-19)

DRAM controller에서 CE case별 latency가 정상 적용되는지 로그 확인:

- **FIRST/ADDED**: Dynamic PTW latency 적용 (4~35 cycles, PSC/cache 상태 의존). PSC hit → 4 cycles, cache miss 포함 시 30+ cycles
- **ALREADY_KNOWN**: latency 0 (break, 아무 추가 없음)
- **RETIRED**: `error_latency_penalty` = 454,568 cycles 적용
- HW PTW latency는 CE 감지 시 OS 없이 HW가 PDE counter를 갱신하는 비용을 모델링한 것

---

## Known Issues / Notes

### ISSUE-2: error_way_count 영구 증가
- **상태**: 설계상 의도적 (해결 불필요)
- **설명**: `error_way_count`는 `allocate_error_way()`에서 증가만 하고 감소하지 않음
- **판단**: 실제 HW에서도 error way partition은 한번 할당되면 유지하는 것이 합리적. Retirement 후 invalidated slot은 새 error data에 재사용되므로 낭비 아님. Error가 완전히 사라지는 시나리오는 실질적으로 발생하지 않음 (DRAM aging은 비가역적)

### ISSUE-3: debug flag — 해결됨 ✅
- **해결**: JSON config `"debug": 0/1`로 제어 가능. 기본값 0 (OFF)
- **범위**: ETT, DRAM latency, LLC pinning 디버그 로그 전부 통합 제어. ChampSim 원래 `champsim::debug_print`와 독립

### ISSUE-6: ECT 동작 연동
- **상태**: 구조만 추가됨 (해결 불필요)
- **설명**: `ECTEntry` struct 정의됨. 시뮬레이션에서는 `page_error_counters`가 동일 역할을 수행하므로 별도 연동 불필요. 논문에서 HW 설계 completeness를 위해 구조만 제시

---

## Key Files

| 파일 | 역할 |
|------|------|
| `inc/error_page_manager.h` | ETTEntry, H3Hash, ECTEntry 구조체, ErrorPageManager 클래스 정의 |
| `src/error_page_manager.cc` | ETT bloom filter 구현 (record_error, retire_page, H3 hash, etc.) |
| `src/dram_controller.cc` | CYCLE 모드 에러 주입, CE case별 latency 적용 |
| `src/cache.cc` | LLC error way 할당/관리, is_error_data (bloom filter query), invalidate_page_error_ways |
| `inc/cache.h` | Cache 클래스 (error_way_count, invalidate_page_error_ways 등) |
| `src/ptw.cc` | PSC 확인, dynamic error latency 계산 |
| `config/defaults.py` | Error page manager 기본값 |
| `config/instantiation_file.py` | Config JSON → C++ 초기화 코드 생성 |
| `llc_pinning_flow.md` | LLC Pinning 설계 상세 정리 (설계 확정 문서) |

## Design References

| 논문 | 활용 내용 |
|------|----------|
| PT-Guard [DSN 2023] | PFN unused bits 재활용 정당화 |
| Perforated Page [ISCA 2020] | 2MB PDE의 unused bits를 metadata로 재정의한 선례 |
| FatPTE [TU Graz 2024] | PTE spare bit 고갈 문제 인식, 확장 방안 |
| Intel MPK | PTE bits를 새로운 HW 기능으로 재정의한 산업 사례 |
| BlockHammer [HPCA 2021] | H3 hash, k=4 bloom filter 선례 |
| Hydra [ISCA 2022] | MC 근처 SRAM overhead 정당화 (56.5KB) |
| DREAM [ISCA 2025] | MC SRAM overhead 정당화 (1KB/bank) |
| SHiP / Mockingjay | LLC controller 내부 SRAM 테이블 정당화 (6~32KB) |
