# 04. Config 레퍼런스

JSON의 `error_page_manager` 섹션. 아래 키들은 전부 **`mode: "CYCLE"`일 때만 의미**가
있고, `error_spatial_model: "clustered"`가 아니면 spatial 키들은 무시된다(기존과 동일
동작). 기본값은 `config/defaults.py`.

## 신규 키

| 키 | 기본값 | 의미 |
|---|---|---|
| `error_spatial_model` | `"uniform"` | `"uniform"` = 레거시(접근 스트림에 부착), `"clustered"` = Poisson cluster fault 모델 |
| `error_seed` | `54321` | temporal/spatial RNG 시드. 같은 seed → 동일한 에러 시퀀스 재현 |
| `fault_weight_cell` | `18.6` | 새 fault가 CELL일 상대 가중치 (합으로 정규화; 기본값 = CARE Table II permanent FIT) |
| `fault_weight_row` | `8.2` | 새 fault가 ROW일 상대 가중치 (동일) |
| `fault_weight_bank` | `10.0` | 새 fault가 BANK일 상대 가중치 (동일) |
| `fault_reuse_prob` | `0.7` | 이벤트가 기존 fault를 재발현할 확률. fault당 평균 발현 = 1/(1−p). [0,1) |
| `error_starvation_cycles` | `1000000` | 기아 확장 시간 단위: 이 CPU cycle 수 경과 시 fault의 bank 전체로, 2배 경과 시 아무 read로 매칭 확장 |
| `error_location_stats` | `false` | **uniform** 모드에서도 에러 위치 분포(line/row/bank 히스토그램 요약)를 출력. clustered는 항상 출력. 기본 off라 레거시 출력 불변 |
| `care_proactive_victims` | `"observed"` | proactive victim 모드: `"observed"` = 그 region에서 에러가 관측된 page만 (증거 기반), `"region"` = **논문 문자 그대로** — row-group과 겹치는 할당 page 전부 (2MB page + interleave에서는 trigger당 ~2GB, ablation용) |

## 기존 키 (관련분만)

| 키 | 의미 |
|---|---|
| `mode` | `"CYCLE"` — 시간 기반 주입 (이 프로젝트의 표준) |
| `error_cycle_interval` | 평균 에러 간격 (CPU cycles). BER sweep은 이 값으로 환산되어 있음 |
| `cache_pinning` / `care` / `care_proactive` 등 | scheme 선택 — spatial model과 직교, 자유 조합 |

## 예시 1 — 기존 실험 그대로 (변화 없음)

```json
"error_page_manager": {
    "mode": "CYCLE",
    "error_cycle_interval": 144000,
    "cache_pinning": true
}
```
`error_spatial_model` 미지정 → uniform → 기존과 bit-identical.

## 예시 2 — clustered + pinning

```json
"error_page_manager": {
    "mode": "CYCLE",
    "error_cycle_interval": 144000,
    "error_spatial_model": "clustered",
    "error_seed": 54321,
    "cache_pinning": true
}
```

## 예시 3 — clustered + CARE proactive, bank fault 스트레스

```json
"error_page_manager": {
    "mode": "CYCLE",
    "error_cycle_interval": 144000,
    "error_spatial_model": "clustered",
    "error_seed": 54321,
    "fault_weight_cell": 0.3,
    "fault_weight_row": 0.1,
    "fault_weight_bank": 0.6,
    "fault_reuse_prob": 0.85,
    "care": true,
    "care_demand_scrub": true,
    "care_proactive": true
}
```

## 예시 4 — seed 변주 (통계적 신뢰구간용)

같은 config에서 `error_seed`만 바꿔 여러 벌 빌드/실행:
```json
"error_seed": 777
```
주의: 설정이 컴파일 타임에 박히므로 seed마다 `executable_name`을 다르게 해서
별도 빌드해야 한다.

## 출력에서 확인할 것

CLUSTERED 실행의 최종 통계에 다음 섹션이 추가된다:

```
[ERROR] [Spatial Fault Model (clustered)]
[ERROR]   Seed:                           54321
[ERROR]   Faults Created:                 N (cell=a row=b bank=c)
[ERROR]   Manifestations (injected CEs):  M (cell=x row=y bank=z)
[ERROR]     Anchoring (first of a fault): ...
[ERROR]     Starved -> Bank-Widened:      ...   ← CELL/ROW 기아 (bank 안에 유지됨, 정상)
[ERROR]     Starved -> Any-Widened:       ...   ← 크면 error_starvation_cycles 재고
[ERROR]   Pending at End / Peak:          p / P ← 잔량이 크면 interval 대비 트래픽 부족
[ERROR]   Manifests per Fault (avg/max):  ...
[ERROR]   Banks Touched:                  ...
[ERROR]   Top Banks (ch/bank_idx: count): ...
[ERROR]   Top-1 Bank Share:               ...%  ← 클수록 bank 편중 (uniform 대비 비교)
[ERROR]   Distinct Lines / Rows / Banks:  L / R / B   ← 에러가 닿은 위치 수 (적을수록 뭉침)
[ERROR]   Errors per Line (avg/max):      ...
[ERROR]   Errors per Row (avg/max):       ...
[ERROR]   Errors per Bank (avg/max):      ...
[ERROR]   Top Lines (cl:count):           상위 5개
[ERROR]   Top Rows (ch/bank/row:count):   상위 5개
```

위치 분포 블록은 **고정 크기 요약**(에러 수와 무관하게 ~8줄)이다. 수집 비용은
에러 이벤트당 map 증가 3회로 시뮬레이션 대비 무시 가능(run당 수천 이벤트, <1MB).
uniform 실행에서도 `error_location_stats: true`로 같은 블록을 출력해 비교할 수 있다.
