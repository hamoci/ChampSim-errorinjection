# ETT Bloom Filter 구현 검증 보고서

**일자**: 2026-03-19
**Config**: `sim_configs/only_for_test/_2MBLLC_2MBPage_DRAM_Error_1e-8_psc_thrash.json`
**Trace**: `test_traces/du_sh_trace.chamsim`
**로그 파일**: `ept_test_output.txt`

두 가지 config로 검증:
1. **기본 config**: ett_entries=64, bloom_filter_size=256, k=4, retirement_threshold=32, max_error_ways=8
2. **포화 stress config**: ett_entries=**4**, max_error_ways=**1** (ETT/LLC 포화 강제 유발)

아래 로그는 포화 stress config(ETT=4, max_error_ways=1) 실행 결과이며, 모든 edge case를 포함.

---

## 1. CYCLE 모드 에러 주입

Exponential distribution 기반으로 DRAM 에러가 주입되고, `pending_error_count`가 정확히 추적되는지 확인.

```
[ERROR_CYCLE] Error added at CPU cycle 102640, next at 131807, pending count: 1
[ERROR_CYCLE] Error added at CPU cycle 131807, next at 370022, pending count: 1
[ERROR_CYCLE] Error added at CPU cycle 370022, next at 769933, pending count: 1
[ERROR_CYCLE] Error added at CPU cycle 769934, next at 774261, pending count: 1
[ERROR_CYCLE] Error added at CPU cycle 774262, next at 995596, pending count: 2
```

- cycle 간격이 exponential distribution을 따름 (29167, 238215, 399911, 4328, ...)
- pending count가 누적되고, `consume_cycle_error()`에 의해 소비됨
- 두 error가 짧은 간격으로 발생 시 pending_count=2까지 누적 (cycle 769934, 774262)

---

## 2. ETT Entry 할당 및 Bloom Filter Insert

첫 error 발생 시 ETT entry 할당 + H3 hash로 bloom filter bit 설정.

```
[ETT] ---- record_error(pa=0x1a696290) ----
[ETT]   page_base=0x1a600000  cl_index=9610
[ETT]   counter: 0 -> 1  (threshold=32)
[ETT]   ETT entry ALLOCATED: ETT[0] for page 0x1a600000
[ETT]   H3 hash(cl_index=9610) -> positions=[128,194,201,45]
[ETT]   bloom bits before: [bit[128]=0, bit[194]=0, bit[201]=0, bit[45]=0]
[ETT]   bloom bits after insert: 4/256 bits set (1.6%)
[ETT]   => FIRST_ERROR
```

- PA에서 page_base(2MB aligned)와 cl_index(PA[20:6])가 정확히 추출됨
- counter가 0→1 증가
- H3 hash가 cl_index로부터 k=4개의 독립 bit position 생성 (128, 194, 201, 45)
- Insert 전 해당 bit들이 모두 0, insert 후 4/256 bits set (1.6%)

---

## 3. 동일 Page 추가 Error (Bloom Filter 누적)

같은 page에 두 번째 error 발생 시 기존 ETT entry를 재사용하고, bloom filter bit가 누적됨.

```
[ETT] ---- record_error(pa=0x2c117f298) ----
[ETT]   page_base=0x2c1000000  cl_index=24522
[ETT]   counter: 1 -> 2  (threshold=32)
[ETT]   ETT entry EXISTS: ETT[0]
[ETT]   H3 hash(cl_index=24522) -> positions=[53,153,24,78]
[ETT]   bloom bits before: [bit[53]=0, bit[153]=1, bit[24]=0, bit[78]=0]
[ETT]   bloom bits after insert: 7/256 bits set (2.7%)
[ETT]   => ADDED_ERROR (count=2)
```

- `ETT entry EXISTS: ETT[0]` — 기존 entry 재사용
- `bit[153]=1` — 이전 error(cl_index=24512)의 hash position과 겹침 (bloom filter 특성상 정상)
- insert 후 4→7 bits set (겹친 bit[153]은 이미 1이므로 +3만 추가)

---

## 4. Dynamic Error Latency (HW PTW 비용)

CE 감지 시 HW PTW로 PDE counter를 갱신하는 비용. PSC/cache hit 여부에 따라 latency 변동.

**Case A: PSC hit + L1D cache hit (최소 latency)**
```
[ERR_LAT] PSC hit -> start_level=2 (pt_levels=4)
[ERR_LAT] level 2: cache hit(cpu0_L1D) +2 cycles, total=2 cycles
[ERR_LAT] level 1: cache hit(cpu0_L1D) +2 cycles, total=4 cycles
[ERR_LAT] final dynamic error latency=4 cycles
[ERR_LAT][CYCLE][DYNAMIC][FIRST] type=LOAD addr=0x1a696290 cpu=0 latency=4 cycles
```
- PSC에서 level 2까지 hit → level 2, 1만 walk
- 모두 L1D hit → 2+2 = 4 cycles

**Case B: PSC partial hit + LLC hit (중간 latency)**
```
[ERR_LAT] PSC hit -> start_level=4 (pt_levels=4)
[ERR_LAT] level 4: cache hit(cpu0_L2C) +5 cycles, total=5 cycles
[ERR_LAT] level 3: cache hit(cpu0_L2C) +5 cycles, total=10 cycles
[ERR_LAT] level 2: cache hit(LLC) +10 cycles, total=20 cycles
[ERR_LAT] level 1: cache hit(LLC) +10 cycles, total=30 cycles
[ERR_LAT] final dynamic error latency=30 cycles
[ERR_LAT][CYCLE][DYNAMIC][FIRST] type=LOAD addr=0x642a6eb50 cpu=0 latency=30 cycles
```
- PSC에서 level 4까지만 hit → 4개 level walk 필요
- L2C hit(5 cycles) × 2 + LLC hit(10 cycles) × 2 = 30 cycles

**Case C: Retirement (page migration latency)**
```
[ERR_LAT][CYCLE][RETIRED] addr=0x2c1180dd0 cpu=0 latency=454568 cycles
```
- 2MB page migration 비용: 454,568 cycles

---

## 5. LLC Error Way 할당

첫 error data가 LLC에 fill될 때 error way 할당.

```
[LLC] ALLOC_NEW: Set 1418 triggering Way 15 allocation (count: 0→1)
[LLC] ALLOC_OK: Way 15 allocated (count now 1)
```

- Way 15(최상위 index)부터 할당 시작
- 전체 set에 걸쳐 Way 15가 error way로 전환됨
- max_error_ways=1이므로 이후 EXPAND 없음 (로그에 EXPAND 미출현으로 확인)

---

## 6. LLC Error Way LRU Eviction

max_error_ways=1에서 같은 set에 두 번째 error data가 pin되어야 할 때 LRU victim 선택.

```
[ERR_LAT][CYCLE][DYNAMIC][ADDED] type=LOAD addr=0x2c11c3e80 cpu=0 latency=30 cycles
[LLC] LRU_VICTIM: Set 249 evicting Way 15 (addr=0x2c11e3e40) for new error data
```

- Set 249의 Way 15에 이미 addr=0x2c11e3e40이 pin된 상태
- 새 error data(0x2c11c3e80)가 같은 set에 pin 필요 → Way 15를 LRU evict하고 새 data pin
- max=1이므로 확장 불가 → Case 4(LRU victim) 경로로 정상 진입

---

## 7. ETT Eviction (LRU, ETT=4 포화)

ETT가 4/4로 꽉 찬 상태에서 5번째 page error 발생.

```
[ETT] ---- record_error(pa=0x40c28f0f8) ----
[ETT]   page_base=0x40c200000  cl_index=9155
[ETT]   counter: 0 -> 1  (threshold=32)
[ETT] EVICT: entry=0 page=0x1a600000
[ETT]   ETT entry ALLOCATED: ETT[0] for page 0x40c200000
[ETT]   H3 hash(cl_index=9155) -> positions=[171,226,69,73]
[ETT]   bloom bits before: [bit[171]=0, bit[226]=0, bit[69]=0, bit[73]=0]
[ETT]   bloom bits after insert: 4/256 bits set (1.6%)
[ETT]   => FIRST_ERROR
```

- ETT[0]~[3] 모두 valid → LRU entry(ETT[0], page 0x1a600000) evict
- Evict된 page의 bloom filter 유실, 새 page 0x40c200000으로 교체
- Evict된 page의 `page_error_counters`는 유지됨 (counter=1 보존)
- 이미 LLC error way에 pin된 cache line은 그대로 남음 (lazy)

전체 5회 eviction 관찰:
```
[ETT] EVICT: entry=0 page=0x1a600000       → ETT[0] = 0x40c200000
[ETT] EVICT: entry=1 page=0x3f5200000      → ETT[1] = 0x192000000
[ETT] EVICT: entry=2 page=0x1e6c00000      → ETT[2] = 0x743600000
[ETT] EVICT: entry=0 page=0x40c200000      → ETT[0] = 0x2c1000000
[ETT] EVICT: entry=3 page=0x3a3e00000      → ETT[3] = 0x73e00000
```

---

## 8. Page Retirement (threshold=32 도달)

page 0x2c1000000이 31개 error를 누적한 후, 32번째 error에서 retirement 트리거.

```
[ETT] ---- record_error(pa=0x2c1180dd0) ----
[ETT]   page_base=0x2c1000000  cl_index=24631
[ETT]   counter: 31 -> 32  (>= threshold 32)
[ETT]   ETT[0] bloom filter before retire: 100/256 bits set (39.1%)
[ETT]   RETIRE page=0x2c1000000:
[ETT]     1. page_error_counters: erased
[ETT]     2. ETT[0]: cleared (had 100/256 bloom bits set)
[ETT]     3. pending_retirement_pages: queued (total pending=1)
[ETT]   => PAGE_RETIRED
[ERR_LAT][CYCLE][RETIRED] addr=0x2c1180dd0 cpu=0 latency=454568 cycles
```

- counter 31→32로 threshold 도달
- Bloom filter 상태: 31개 unique error로 100/256 bits set (39.1%) — 이론적 k×n = 4×31 = 124 시도, collision 감안하면 100 합리적
- Retirement 절차: (1) counter 삭제 (2) ETT entry clear (3) LLC sweep 큐잉
- Retirement latency: 454,568 cycles 적용

---

## 9. LLC Sweep (Retirement 시 Error Way Invalidation)

Retirement된 page의 error way를 page boundary 기반으로 sweep.

```
[LLC_SWEEP] invalidate set=3 way=15 addr=0x2c11e00c0 (page=0x2c1000000)
[LLC_SWEEP] invalidate set=60 way=15 addr=0x2c1180f10 (page=0x2c1000000)
[LLC_SWEEP] invalidate set=69 way=15 addr=0x2c1181150 (page=0x2c1000000)
  ... (중략) ...
[LLC_SWEEP] invalidate set=1984 way=15 addr=0x2c117f008 (page=0x2c1000000)
[LLC_SWEEP] invalidate set=1994 way=15 addr=0x2c117f298 (page=0x2c1000000)
[LLC_SWEEP] invalidate set=2007 way=15 addr=0x2c117f5c0 (page=0x2c1000000)
[LLC_SWEEP] page=0x2c1000000 sweep complete: 67 cache lines invalidated from error ways [15-16)
```

- Error way 범위 [15-16) (max_error_ways=1이므로 way 15만)
- 2048개 set을 순회하며 page 0x2c1000000에 속하는 cache line 67개 invalidate
- 31개 unique error인데 67개 invalidate된 이유: bloom filter false positive로 정상 cache line도 error way에 pin되었기 때문
- Invalidated slot은 이후 새 error data pin 시 빈 슬롯으로 재사용 가능

---

## 10. Retirement 후 정상 동작 복귀

Retired page의 ETT entry가 해제된 후, 새 page에 대해 정상적으로 ETT entry가 재할당되는지 확인.

```
[ETT] ---- record_error(pa=0x642a6eb50) ----
[ETT]   page_base=0x642a00000  cl_index=7085
[ETT]   counter: 0 -> 1  (threshold=32)
[ETT]   ETT entry ALLOCATED: ETT[0] for page 0x642a00000
[ETT]   H3 hash(cl_index=7085) -> positions=[172,242,0,252]
[ETT]   bloom bits before: [bit[172]=0, bit[242]=0, bit[0]=0, bit[252]=0]
[ETT]   bloom bits after insert: 4/256 bits set (1.6%)
[ETT]   => FIRST_ERROR
```

- Retirement으로 비워진 ETT[0]이 새 page 0x642a00000에 재할당됨
- Bloom filter가 깨끗한 상태(0 bits)에서 시작 → 정상

---

## 11. Pinning ON/OFF 분리

코드 경로 검증 (로그가 아닌 소스 코드 추적):

| 코드 위치 | Guard 조건 | Pinning OFF 시 동작 |
|---|---|---|
| `dram_controller.cc:392` | `epm.is_cache_pinning_enabled()` | `record_baseline_error()` 호출 (단순 counter) |
| `cache.cc:187` (handle_fill) | `epm.is_cache_pinning_enabled() && is_error_data()` | 항상 `find_normal_way()` 경로 |
| `cache.cc:253` (error way timestamp) | `epm.is_cache_pinning_enabled()` | 건너뜀 |
| `cache.cc:335` (error way hit timestamp) | `epm.is_cache_pinning_enabled()` | 건너뜀 |
| `cache.cc:489` (LLC sweep) | `epm.is_cache_pinning_enabled()` | 건너뜀 |

→ Pinning OFF 시 ETT, bloom filter, error way 관련 코드가 일절 실행되지 않음.

---

## 12. 최종 통계 일관성

```
LLC Error Way Statistics:
  Allocated Error Ways per Set: 1
  Total Error Way Slots: 2048 (= 2048 Sets × 1 Ways)
  Used Error Way Slots: 23 (1.12%)
  Unused Error Way Slots: 2025 (98.88%)

[ETT] ========== Error Tracking Table Statistics ==========
[ETT] [Configuration]
[ETT]   ETT Entries:                    4
[ETT]   Bloom Filter Size (m):          256 bits
[ETT]   Hash Functions (k):             4
[ETT]   Retirement Threshold:           32
[ETT] [DRAM Error Events]
[ETT]   Total DRAM Error Events:        55
[ETT]     New Error Recordings:         54
[ETT]       First Error (per page):     10
[ETT]       Additional Errors:          44
[ETT]     Page Retirements (32th err): 1
[ETT]     Already Known (bloom hit):    0
[ETT] [Page Status]  (after retirement, page resets to clean)
[ETT]   Active Pages (tracked):         9
[ETT]     Single-error pages:           6
[ETT]     Multi-error pages:            3
[ETT] [ETT Table Usage]
[ETT]   ETT Entries Used:               4 / 4
[ETT]   ETT Evictions:                  5
```

**수치 일관성 검증:**
- First(10) + Added(44) + Retirement(1) + AlreadyKnown(0) = **55** = Total ✅
- Retired page(0x2c1000000)에서 31개 error + retirement trigger 1개 = 32. 나머지 9 page에서 23개 = 총 55 ✅
- Used Error Way Slots(23) = 전체 54개 recording - retired page의 31개 ✅
- ETT Entries Used(4/4) = stress config에서 4 entry 모두 사용 중 ✅
- ETT Evictions(5) = 10개 page가 등장했으나 4 entry만 가용 → 5회 eviction ✅
