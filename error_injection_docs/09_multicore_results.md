# 09. 멀티코어 Exp1 — Uniform vs Clustered 주입 비교 결과 (2026-07-17)

> 실행: 2026-07-16 14:12 발사 → 07-17 01:42 완료. **40/40 DONE, FAIL 0** (최장 11.5h).
> 구성: 4-core SPEC mixes (M1-4/C1-4/H1-2) × {off, pin} × {1e-7, 1e-8} × clustered
> (seed 54321, FIT 구성비), warmup 50M + sim 250M/core.
> 비교 기준선: 기존 uniform 결과(`results/multicore/1_error_rate_sweep`, bit-identical
> 보존으로 재실행 불필요) + 같은 mix의 noerr run을 weighted-speedup 분모로 사용.
> 재현: `python3 stat_script_rev/compare_multicore_clustered.py`
> (CSV: `stat_script_rev/multicore_clu_compare_summary.csv`)

## 요약 (TL;DR)

1. **1e-7에서는 모델 전환의 성능 영향이 무시 가능** (ΔWS 평균 off −0.003 / pin +0.002).
2. **1e-8에서 conventional offline의 평가가 크게 달라짐**: uniform은 offline을
   과도하게 처벌하고 있었다 (재-retire 루프). clustered에서 offline WS 평균
   **2.10 → 3.22 (+1.03)**, retirement **6,137 → 1,557 (−75%)**.
3. **Pinning은 주입 모델에 불감** (ΔWS +0.009) — line 단위 보호가 공간 분포와 직교.
4. **논문 함의**: 1e-8에서 pinning vs offline 격차가 (3.90 vs 2.10) → (3.92 vs 3.22)로
   축소되지만 여전히 명확한 pinning 우위. uniform 기반 기존 수치는 offline에 불리한
   구조적 편향이 있었으므로 clustered 결과로 갱신 권장.

## 1. Weighted Speedup (같은 mix의 noerr 대비, 최대 4.0)

### off @ 1e-7 (Δ 평균 −0.003 — 동등)
| mix | uniform | clustered | Δ |
|---|---|---|---|
| M1 | 3.971 | 3.969 | −0.002 |
| M2 | 3.930 | 3.916 | −0.014 |
| M3 | 3.980 | 3.994 | +0.013 |
| M4 | 3.958 | 3.949 | −0.009 |
| C1 | 3.917 | 3.907 | −0.010 |
| C2 | 3.849 | 3.898 | +0.049 |
| C3 | 3.848 | 3.836 | −0.012 |
| C4 | 3.855 | 3.833 | −0.022 |
| H1 | 3.962 | 3.951 | −0.010 |
| H2 | 3.778 | 3.767 | −0.011 |

### off @ 1e-8 (Δ 평균 **+1.033** — 모델이 결론을 바꾸는 지점)
| mix | uniform | clustered | Δ |
|---|---|---|---|
| M1 | 3.034 | 3.235 | +0.201 |
| M2 | 2.079 | 2.494 | +0.415 |
| M3 | 3.416 | 3.594 | +0.178 |
| M4 | 2.566 | 3.240 | +0.673 |
| C1 | 1.920 | 3.392 | +1.473 |
| C2 | 1.363 | 3.038 | +1.675 |
| C3 | 1.544 | 3.113 | +1.570 |
| C4 | 1.541 | 3.388 | +1.847 |
| H1 | 2.416 | 2.639 | +0.223 |
| H2 | 1.131 | 3.204 | +2.072 |

### pin @ 1e-7 (Δ 평균 +0.002) / pin @ 1e-8 (Δ 평균 +0.009)
전 mix에서 |Δ| ≤ 0.036 — pinning은 두 모델에서 사실상 동일 (표는 CSV 참조).
pin @ 1e-8 절대값: uniform 3.83~3.96, clustered 3.84~3.96.

## 2. Retirement 비교 (run당 평균 / 최대)

| | uniform | clustered | 해석 |
|---|---|---|---|
| off 1e-7 (baseline retire) | 171 / 358 | 177 / 388 | 동등 |
| **off 1e-8** | **6,137 / 21,062** | **1,557 / 3,329** | **−75%** — uniform의 재-retire 루프(retired page 재에러→재-retire, 회당 454k cycle)가 제거되고, fault lifecycle(run당 평균 804개 fault가 retire로 소멸)이 후속 에러를 구조적으로 줄임 |
| pin 1e-7 (page retire) | 0 / 0 | 0 / 0 | threshold 32 미도달 |
| pin 1e-8 | 28 / 96 | 23 / 71 | 유사 |

**off@1e-8이 uniform에서 그토록 느렸던 이유가 scheme의 본질이 아니라 주입 모델의
아티팩트였음**이 이 표의 핵심이다. C-mixes(작은 working set → 같은 page 재타격
빈발)에서 격차가 가장 컸던 것도 이 메커니즘과 일치한다.

## 3. 공간 통계 (clustered run 평균)

| | faults | 소멸 | manifests | 영구 retire | Top-1 bank | line max | row max |
|---|---|---|---|---|---|---|---|
| off 1e-7 | 183 | 76 | 621 | 177 | 6.3% | 1.5 | 2.0 |
| off 1e-8 | 2,419 | 804 | 3,142 | 1,557 | 3.3% | 2.0 | 2.0 |
| pin 1e-7 | 183 | 0 | 607 | 0 | 5.9% | 1.0 | 4.5 |
| pin 1e-8 | 1,784 | 158 | 6,059 | 23 | 2.9% | 1.0 | 8.2 |

- pin의 **line max = 1.0**: pinning이 anchor line을 LLC에 가둬 같은 line 재발현이
  구조적으로 억제됨 (scheme 효과가 모델에 자연 반영). 대신 **row max 8.2** (1e-8):
  ROW fault의 page 내 다중 에러는 살아 있음.
- Top-1 bank share 2.9~6.3% (균등 기대 1.56%) — 실험 스케일에서도 bank 뭉침 형성.

## 4. Per-CPU 에러 흡수 편중

absorbed_max_share (한 CPU가 흡수한 에러의 최대 비중, 균등=0.25) 평균:
**uniform 0.339 → clustered 0.396** — fault가 특정 코어의 page/bank에 고착되면서
흡수 편중이 커짐. mix 해석 시 per-CPU 통계 필수 (EXPANSION_PLAN의 예측과 일치).

## 5. 총량 보존 확인

pin 기준 (retire가 적어 배달 왜곡 없음): 1e-7 615→607, 1e-8 6,185→6,059 (−2%) ✓.

**정직한 예외 — off@1e-8**: 소비 3,142 / 도착 ~6k, 미배달 pending 최대 9,172건.
평균 1,557 page(≈3.1GB)가 영구 retire되면서 배달 가능 영역 자체가 줄어든 결과다.
"retire된 page는 에러를 낼 수 없다"는 의미론적으로 옳은 동작이지만, 극한
retirement 국면에서는 소비량이 도착량을 따라가지 못한다는 점을 결과 해석 시
명시할 것 (uniform off@1e-8의 총량과 직접 비교하면 안 됨 — uniform 쪽은 같은
page가 무한 재에러하는 반대편 아티팩트를 갖고 있었음).

## 6. Caveats / 다음 단계

- 단일 seed(54321) — 신뢰구간용 다중 seed는 P6에서.
- CARE는 이 스윕에 미포함 (P3 재정렬로 기존 CARE 결과가 무효화되어 별도 재실험 필요).
- 1e-6 clustered 미실행 (1e-7에서 이미 Δ≈0이므로 우선순위 낮음 — 필요시
  `run_mixes_clustered.sh`에 바이너리 추가).
