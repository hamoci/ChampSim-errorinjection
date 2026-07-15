# Protected Line Metric — 구현 계획 (Snapshot-Only 최종안)

## 1. 배경

`2_retirement_threshold` 실험에서 conv(pinning OFF) vs proposed(pinning ON)의 안전성을 같은 metric으로 비교하려는 목적. 현재 `print_error_way_stats()` 의 Protection Coverage는 pinning ON 경우에만 출력되고, pinning OFF에선 출력 자체가 없음 — 따라서 baseline의 "page retirement에 의한 보호" 효과를 측정할 수단이 부재.

## 2. 정의 (Snapshot-Only)

긴 sim에서 누적 카운터가 dilution을 일으키는 문제를 회피하기 위해, **snapshot-only metric**으로 정의:

**Pinning OFF용 Protection Coverage**
```
분자 = |retired_error_addresses|         # unique cl_addr 단위, 시간에 무관
분모 = |retired_error_addresses| + |error_addresses|
       = 시뮬레이션 동안 본 unique faulty cl 총수 (working set으로 bounded)
Coverage(%) = 분자 / 분모 × 100
```

`retired_error_addresses` 는 `std::unordered_set`이므로 같은 PA가 여러 번 retire돼도 unique cl_addr 1개로 dedup됨. working set 크기 한계 내에서 유지되어 sim 길이에 안 흔들림.

**Pinning ON: 변경 없음**. 기존 출력 그대로 유지 (논문에선 별도 metric으로 비교).

## 3. 핵심 결정 사항

- **Counter 누적 안 함** (시간 dilution 회피)
- **`retired_error_addresses` set 추가** (unique cl 단위, snapshot)
- **Pinning ON 코드/출력은 손대지 않음**. retired_set은 pinning ON에서도 자동 채워지지만 출력에선 사용 안 함.
- **시나리오 C (LLC error-way eviction) 변경 없음**. evict된 cl_addr는 `error_addresses`에 남아 자연스럽게 unprotected bucket으로 분류됨.

## 4. 구현 변경 사항

### 4.1 `inc/error_page_manager.h`

추가:
```cpp
private:
    std::unordered_set<uint64_t> retired_error_addresses;

public:
    const std::unordered_set<uint64_t>& get_retired_error_addresses() const {
        return retired_error_addresses;
    }
    size_t get_retired_error_address_count() const {
        return retired_error_addresses.size();
    }
```

`record_baseline_error()` 본체를 `.cc` 로 옮기기 위해 헤더에서 선언만 남김:
```cpp
bool record_baseline_error(uint64_t pa);
```

### 4.2 `src/error_page_manager.cc`

**`retire_page()` 수정** — erase 루프에 한 줄 추가:
```cpp
for (auto it = error_addresses.begin(); it != error_addresses.end(); ) {
    if ((*it & page_mask) == page_base) {
        retired_error_addresses.insert(*it);    // ← 추가
        it = error_addresses.erase(it);
        removed++;
    } else {
        ++it;
    }
}
```

**`record_baseline_error()` 본체를 .cc로 이전 + cl_addr 추적**:
```cpp
bool ErrorPageManager::record_baseline_error(uint64_t pa) {
    uint64_t page_base = get_page_base_pa(pa);
    uint64_t cl_addr   = get_cache_line_addr(pa);

    error_addresses.insert(cl_addr);            // ← snapshot 원자료

    auto& count = baseline_page_error_counts[page_base];
    count++;
    if (count >= baseline_retirement_threshold) {
        retire_page(page_base);                  // ← 공통 helper
        stat_baseline_retirement_count++;
        // 기존 debug 출력 유지
        return true;
    }
    return false;
}
```

> 주의: `retire_page()` 가 `pending_retirement_pages.push_back()` 을 호출하지만, baseline 경로에선 LLC의 `invalidate_page_error_ways()` 가 `error_way_count == 0` 이므로 자동 no-op. 안전.

### 4.3 `src/cache.cc`

`print_error_way_stats()` 구조 변경:

```cpp
void CACHE::print_error_way_stats() const {
    auto& epm = ErrorPageManager::get_instance();
    if (NAME != "LLC") return;

    // -- Error Way Statistics 섹션: pinning ON 한정 (기존 그대로) --
    if (epm.is_cache_pinning_enabled() && error_way_count > 0) {
        // (기존 "Error Way Statistics" + 기존 "Protection Coverage" 출력 그대로)
        // ...
        return;
    }

    // -- Pinning OFF 용 Baseline Protection Coverage (신규) --
    {
        const auto& retired = epm.get_retired_error_addresses();
        const auto& live    = epm.get_error_addresses();
        size_t retired_n = retired.size();
        size_t live_n    = live.size();
        size_t total     = retired_n + live_n;
        double coverage  = (total > 0) ? (100.0 * retired_n / total) : 0.0;

        fmt::print("\n[LLC] ========== Baseline Protection Coverage ==========\n");
        fmt::print("[LLC]   Total Known Error Addresses:    {}\n", total);
        fmt::print("[LLC]   Retired (page offline):         {} ({:.2f}%)\n", retired_n, coverage);
        fmt::print("[LLC]   Live (still tracked):           {}\n", live_n);
        fmt::print("[LLC] ===================================================\n");
    }
}
```

`print_error_way_stats()` 의 기존 early return 조건은 위 구조로 자연스럽게 흡수됨.

## 5. 변경 범위

- `inc/error_page_manager.h`: ~8줄 (멤버 + 2개 getter + 선언)
- `src/error_page_manager.cc`: ~15줄 (`retire_page()` 1줄, `record_baseline_error()` 본체 이전)
- `src/cache.cc`: ~20줄 (`print_error_way_stats()` 구조 분리 + baseline 출력)

**총 ~40줄 안팎**.

## 6. 동작 예상 결과

| Config | Live (snapshot) | Retired (set size) | Coverage % | 해석 |
|--------|----------------|---------------------|------------|------|
| Conv t=2  | 작음 | 큼 | 높음 | retire가 부지런히 보호. cost 큼. |
| Conv t=16 | 중간 | 중간 | 중간 | 균형 |
| Conv t=32 | **큼** | 작음 | **낮음** | retire 부족 → 노출 위험 ↑ (unsafe) |
| Proposed (참고용, 출력 안함) | 작음 | 작음 | — | pinning 으로 live가 작게 유지됨 |

시간에 안흔들림: `retired_set` 은 working set 으로 bounded, `error_addresses` 도 동일. 둘 다 unique cl_addr 단위 set.

## 7. 명시적 비변경 사항

다음은 본 작업에서 건드리지 않음:
- Pinning ON의 Error Way Statistics / Protection Coverage 출력
- `record_error()` (pinning ON 경로) 로직
- `retire_page()` 의 LLC sweep 큐잉 (`pending_retirement_pages`)
- LLC error-way eviction 시 `error_addresses` 처리 (시나리오 C — `ALREADY_KNOWN` 그대로)
- VirtualMemory remapping
- Latency 모델 (pinning ON dynamic/fixed, pinning OFF retirement 시점)
- 누적 카운터(`stat_retired_cl_count`, `stat_evicted_cl_count`) — 추가하지 않음

## 8. 검증 항목

- `pinning_off/threshold_*_1e-*.json` 빌드 통과
- 시뮬레이션 실행 시 `[LLC] Baseline Protection Coverage` 섹션 출력 확인
- threshold 작을수록 Coverage% 가 높게 나오는지 (즉 retired_n > live_n)
- `retired_n + live_n` 이 시간에 따라 무한 증가하지 않는지 (working set bound)
- Pinning ON 빌드 결과의 출력이 이전과 동일한지 (회귀 확인)
