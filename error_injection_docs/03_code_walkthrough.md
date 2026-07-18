# 03. 코드 워크스루

수정 파일: `inc/error_page_manager.h`, `src/error_page_manager.cc`,
`src/dram_controller.cc`, `src/cache.cc`(출력 1줄), `config/defaults.py`,
`config/instantiation_file.py`.

## 1. 자료구조 (`inc/error_page_manager.h`)

```cpp
enum class ErrorSpatialModel { UNIFORM, CLUSTERED };
enum class FaultMode { CELL, ROW, BANK };

struct FaultDomain {                 // 지속성 있는 결함 영역 하나
    FaultMode mode;
    bool anchored{false};            // 첫 발현으로 위치가 확정됐는가
    uint64_t bank_key;               // (channel << 32) | bank_request_index
    uint64_t row;                    // DRAM row (ROW 매칭용)
    uint64_t anchor_cl;              // cache line 주소 (CELL 매칭용)
    uint64_t manifest_count;
};
struct PendingManifest {             // 소비를 기다리는 Poisson 이벤트 하나
    size_t fault_idx;                // 어느 fault의 발현인가
    uint64_t fire_cycle;             // 발생 시각 (기아 판정용)
    uint8_t widen{0};                // 기아 확장 단계: 0=정확, 1=bank, 2=any
};

std::mt19937_64 temporal_rng;        // 발생 시각 전용 (seed = error_seed)
std::mt19937_64 spatial_rng;         // fault 샘플링 전용 (seed = error_seed ^ 황금비 상수)
std::vector<FaultDomain> faults;
std::vector<PendingManifest> pending_manifests;
```

UNIFORM 모드는 이 상태를 전혀 건드리지 않는다 — 기존 `gen`/`exp_dist`/
`pending_error_count` 경로가 그대로 실행되어 레거시 결과가 바이트 단위로 재현된다.

## 2. 발생: `update_clustered_errors(current_cycle)` (`src/error_page_manager.cc`)

호출 위치: `DRAM_CHANNEL::operate()` → `update_cycle_errors()` (매 DRAM 사이클,
warmup 제외) → CLUSTERED이면 이 함수로 분기.

```
1. (최초 1회) temporal/spatial RNG를 error_seed로 시드하고 첫 발생 시각 샘플
2. while (현재 사이클 >= 다음 발생 시각):        ← 밀린 arrival을 전부 처리 (진짜 Poisson)
       spawn_manifest(발생시각)
       다음 발생 시각 += Exp(1/interval) 샘플 (최소 1 cycle)
3. 기아 aging: 각 pending 이벤트의 나이에 따라 매칭 영역을 단계적으로 확장
       나이 > error_starvation_cycles     → widen=1 (fault의 bank 안이면 매칭)
       나이 > 2 × error_starvation_cycles → widen=2 (아무 read나 매칭)
```

CELL fault의 anchor line은 LLC에 있는 동안 DRAM 재읽기가 없어(pinning이 보호하면
더욱) 기아가 구조적으로 흔하다. widen=1 단계 덕분에 그런 발현도 fault의 bank 안에
떨어져 공간 뭉침이 유지되고, widen=2가 최종적으로 총량을 보존한다.

### `spawn_manifest(fire_cycle)`

```
faults 비어있지 않고 U(0,1) < fault_reuse_prob ?
  ├─ YES: 기존 fault 중 균등 선택 → 그 fault의 재발현 이벤트를 pending에 추가
  └─ NO : 새 fault 생성 (mode ~ cell/row/bank 가중치, 미앵커 상태)
          → 첫 발현 이벤트를 pending에 추가
```

## 3. 소비: `consume_clustered_error(cl, bank_key, row)`

호출 위치: `DRAM_CHANNEL::service_packet()`의 CYCLE 분기. read packet(WRITE 제외)을
서비스할 때 packet 주소의 DRAM 좌표와 함께 호출된다:

```cpp
// src/dram_controller.cc service_packet()
const uint64_t err_bank_key = (get_channel(addr) << 32) | op_idx;  // bank 유일 식별자
...
epm.consume_cycle_error(raw_pa, err_bank_key, op_row)
```

매칭 규칙 (pending 리스트를 오래된 것부터 스캔, 첫 매칭 1개만 소비):

```
fault가 미앵커 → 무조건 매칭 + 이 접근의 (bank_key, row, cl)로 앵커
그 외          → CELL: cl == anchor_cl
                 ROW : bank_key == fault.bank_key && row == fault.row
                 BANK: bank_key == fault.bank_key
                 (불일치여도) widen>=1 이고 bank_key == fault.bank_key → 매칭
                 (불일치여도) widen>=2 → 매칭
```

매칭되면 true를 반환하고, 이후의 에러 기록/latency 처리는 **기존 경로 그대로**다:
- pinning ON → `record_error()` (FIRST/ADDED/KNOWN/RETIRED)
- pinning OFF → `record_baseline_error()`
- CARE → `care_on_injected_error()` (S1 등록, demand scrub 등)

즉 clustered 모델은 **"어떤 read가 에러를 받는가"만 바꾸고, 받은 다음의 처리는 일절
건드리지 않는다.** 이 경계 덕분에 scheme 간 비교(pinning/offline/CARE)의 공정성이
유지된다.

## 3b. Retirement 연동: `on_page_retired_clustered(page_base)`

`retire_page()` 말미에서 CLUSTERED일 때만 호출된다 (pinning/baseline/CARE 세 retire
경로 모두 통과). 하는 일:

1. `clustered_retired_pages`에 page 영구 기록 → 이후 그 page로 오는 read는
   `consume_clustered_error()` 첫 줄에서 차단 (앵커/기아 확장 포함 일절 소비 불가).
   uniform 모드의 "retired page 재등록 → 재-retire 루프" artifact가 clustered에서는
   구조적으로 제거된다.
2. 그 page에 앵커된 CELL/ROW fault를 dead 처리 (`live_fault_indices`에서 제거).
   BANK fault는 유지.
3. dead fault를 가리키던 pending 이벤트는 `select_fault_for_manifest()`로 재샘플
   (살아있는 fault 재사용 또는 새 fault 생성) → 총량 보존.

## 4. bank_key의 구성

`op_idx = bank_request_index(addr)`는 채널 내부에서 rank/bankgroup/bank를 접은 평탄
인덱스(bank FSM 배열 인덱스와 동일)다. 멀티채널 구분을 위해 channel을 상위 32비트에
넣는다. CARE proactive의 글로벌 카운터 인덱스(`op_idx % 8`)는 기존 그대로 유지
(uniform CARE 결과의 bit-identical 보존).

## 5. 통계 출력

`print_spatial_fault_stats()` — CLUSTERED일 때만 `[ERROR] [Spatial Fault Model
(clustered)]` 섹션을 출력한다. 호출 경로는 두 곳:
- pinning ON: `print_error_stats()` 내부 (cache.cc LLC 최종 통계)
- pinning OFF / CARE: cache.cc의 early-return 분기

내용: seed, mode별 fault 수/발현 수, 앵커 발현 수, 기아 fallback 수, pending
잔량/피크, fault당 평균/최대 발현, 접촉한 bank 수, 상위 bank별 발현 수(top 8),
top-1 bank 점유율.

## 6. Config 흐름

```
JSON "error_page_manager" 섹션
  → config/parse.py (defaults.py와 chain, 통과만 함)
  → config/instantiation_file.py: error_spatial_model == 'clustered'일 때만
      epm.set_error_spatial_model(ErrorSpatialModel::CLUSTERED);
      epm.set_error_seed(...); epm.set_fault_mode_weights(...);
      epm.set_fault_reuse_prob(...); epm.set_error_starvation_cycles(...);
    를 .csconfig 생성 코드에 emit  (uniform이면 아무것도 emit 안 함 → 기존 코드젠 불변)
```

주의: 모든 EPM 설정은 **컴파일 타임에 박힌다** (기존 방식 동일). seed를 바꾸려면
JSON을 바꾸고 재빌드해야 한다. seed sweep이 필요해지면 CLI 옵션화가 다음 단계.

## 7. 불변 조건 정리 (리뷰/설명용)

1. UNIFORM 모드: 신규 코드는 분기 한 줄(`spatial_model == CLUSTERED` 체크) 외에 실행되지
   않는다. RNG 소비 순서 불변 → 기존 결과 bit-identical (smoke로 확인, 05 문서).
2. CLUSTERED 모드: 에러 발생 "총량"의 기댓값은 UNIFORM과 동일 (같은 Poisson rate).
   fault가 retirement로 죽어도 그 몫은 재샘플되므로 총량은 유지된다.
3. 에러는 항상 실제 서비스된 read에 부착 → 모든 scheme이 에러를 관측 가능.
4. 기아 fallback이 있으므로 pending이 무한히 쌓여 총량이 새는 일 없음 (통계로 감시).
5. 같은 `error_seed` + 같은 워크로드 + 같은 바이너리 → 완전 동일 결과.
6. 한번 retire된 page는 (clustered에서) 다시는 에러를 기록하지 않는다 — hard fault
   영속성과 migration 의미론의 결합. retirement 카운트에 중복이 없다.
