# 10. Sticky Hard-Fault 재설계 — 접근구동 CE + 영역별 rate cap (설계안, 2026-07-20)

> 목적: CE 개수를 전역 Poisson 예산으로 통제하던 clustered 모델을, **고정 fault 영역
> + 접근구동 CE + 영역별 refractory cap**으로 바꿔 (①시간축 storm ②공간 몰림 →
> CARE proactive 발화 ③접근구동 retirement ④개수 통제)를 **동시에** 얻는다.
> 배경: clustered 모델은 count-fidelity를 위해 starvation-widening + 전역 Poisson
> 예산을 두었는데, 그게 정확히 공간 몰림을 희석시킨다(08 §3.5, 09 §3, demo3=widening off).

## 0. 한 줄
> 결함(fault)이 1차, CE는 그 관측이다. **결함 N개를 공간에 박고, 그 영역을 읽을 때마다
> CE를 내되(hard fault), 영역별 refractory R로 개수를 묶는다.** 몰림은 구조적, storm은
> 접근 패턴에서 창발, 개수는 N·R로 통제.

## 1. 통제축 재정의 (핵심 전환)
| | OLD (clustered) | NEW (sticky) |
|---|---|---|
| 1차 통제 노브 | CE rate (`error_cycle_interval`) | **fault 개수 N (= 결함 밀도)** |
| CE 개수 | Poisson 예산이 직접 정함 | 접근 × 발현으로 **창발** (상한 N/R) |
| 공간 분포 | 예산의 부산물 (희석됨) | **구조적** (fault = 고정 영역) |
| 물리 해석 | "초당 CE 몇 개" | "이 DIMM에 hard fault 몇 개" (더 physical) |

## 2. Fault population (지속 결함 집단)
- 지속 fault N개. 각 fault = { mode ~ FIT(cell 18.6:row 8.2:bank 10.0), chip ~ U(0,7),
  anchor(bank,row,line), last_emit_cycle, emit_count }.
- **Lazy anchor 생성**: `live < N`이면 적격 DRAM read가 `spatial_rng` 기반 확률로 그 자리에
  새 fault를 앵커(첫 접근 위치 상속) — N 도달까지. (footprint≪메모리라 사전 랜덤배치는
  대부분 관측불가 → 기존 앵커 논리 유지, "관측된 결함의 조건부 분포".)
- retirement로 죽은 CELL/ROW는 새 fault로 보충 → N 유지 (기존 resample 대체).
- **드롭**: `fault_reuse_prob`(몰림이 구조적이라 불필요), `pending_manifests`, spawn/widening.

## 3. CE emission — 접근구동 + cap (당신이 원한 그것)
```
on DRAM read A (warmup 제외, WRITE 제외, retired page 제외):
  F ← A를 구역에 포함하는 live fault  (CELL: line==anchor_cl / ROW: bank+row / BANK: bank;
                                        여러 개 매칭이면 최소 입도 우선)
  if F and (cycle - F.last_emit_cycle >= R_effective):   # §4의 refractory
      emit CE   → 기존 record_error / record_baseline_error / care_on_injected_error 그대로
      last_consumed_chip = F.chip;  F.last_emit_cycle = cycle;  F.emit_count++
```
- "영역 접근 = CE"가 그대로 살아난다 → 같은 page 반복접근 → CE 누적 → **retirement 자연 트리거.**
- widening/pending 없음 → 몰림이 안 흩어진다.

## 4. 개수통제 & death spiral 회피
- **Refractory 입도 = (fault, page)** 추천: 한 page는 R당 최대 1 CE.
  - CELL(1 line)·ROW(page 내 여러 line)·BANK(여러 page) 모두 page당 상한 → retirement가
    `threshold × R` cycle 이상 걸리게 통제되면서, BANK fault는 여러 page를 때려 CARE
    per-set 밀도를 만들 수 있음. (per-fault 입도는 BANK을 과도히 굶겨 bias 형성 실패;
    per-line 입도는 개수통제 약함 → page 입도가 균형.)
- 상한 CE rate = (fault가 건드린 page 수) × 1/R. hot page도 R로 묶여 폭발 없음.
- **spiral 회피 3중 안전**: (1) CE cost ≈ 0 (SEC-DED inline, 08 §1) (2) retirement 영구
  (`clustered_retired_pages` 유지 → 재등록 루프 없음) (3) R cap. → 05 §운영기록의 454k
  나선이 구조적으로 재발 불가.
- **구 sweep 대응**: N,R를 조정해 목표 CE 수(예: 1e-8≈6k)에 맞추는 캘리브레이션 1회
  (아래 §10 결정 (a)).

## 5. 시간축 storm (목표①) — 공짜로 해결
CE가 접근에 걸리므로 **접근 스트림의 burstiness를 그대로 상속**한다. faulty 영역이
working set에 뜨거울 때 CE storm, 식으면 조용 → 워크로드 인과적 **진짜 storm**
(합성 Hawkes/NHPP보다 현실적). R은 첨두만 깎고 burst 구조는 보존.
※ homogeneous Poisson(구 모델, Fano=1)과 근본적으로 다름: 여기 CE는 시간 자기상관을 가짐.

## 6. Retirement / lifecycle (그대로 유지)
CELL/ROW anchored page retire 시 사망(migration), BANK 생존(bank 회로 안 고쳐짐),
retire page 영구 차단 — `on_page_retired_clustered` 로직 유지.

## 7. CARE proactive (목표②) — 발화 unblock
단일 BANK fault(고정 chip lane)가 bank 전역에 접근구동 CE → 그 fault발 retirement가
**같은 set에서 같은 chip counter 누적** → bias≥12 발화. widening 산란 제거가 핵심.
demo3(05 §V8, widening off로만 발화)를 **hack 없이 현실 밀도**에서 재현하는 구조.

## 8. 코드 변경 (bf501d9 위에서 최소 수술)
- **유지**: `FaultDomain`(+`last_emit_cycle`,`emit_count` 필드 추가), `faults`,
  `live_fault_indices`, chip 지정, `on_page_retired_clustered`, `record_error_location`,
  retirement lifecycle, seed 이원화(`temporal_rng`는 이제 fault 생성 확률용으로 재활용/삭제).
- **제거**: `update_clustered_errors`의 Poisson catch-up spawn, `pending_manifests`,
  `spawn_manifest`, starvation widening 블록, `stat_widened_bank/any`, `next_error_cycle`.
- **개조**: `consume_clustered_error` → §3 매칭+refractory 로직. `select_fault_for_manifest`
  → `create_fault(mode,chip)` (앵커는 소비 시점). `update_clustered_errors` → per-cycle
  할 일 없음(또는 dead fault 보충만).
- **dispatch**: `consume_cycle_error`에 `sticky` 분기 추가(`inc/error_page_manager.h:510`).
- **stats**: widening 통계 → emit_count 분포/영역별 CE 밀도/per-set retirement 집중도로 교체.

## 9. Config (`config/instantiation_file.py` emit)
- `error_spatial_model: "sticky"` (신규; `uniform`/`clustered` 바이트 보존).
- 신규: `fault_count`(N), `fault_refractory_cycles`(R), refractory 입도(`per_page` 기본).
- 유지: `fault_weight_cell/row/bank`, `error_seed`.
- **무시**(sticky일 때): `error_cycle_interval`, `fault_reuse_prob`, `error_starvation_cycles`.

## 10. 사용자 결정 필요 (구현 전 확정)
- **(a) 실험축**: 기존 pinning 그림 연속성 위해 **CE-count 캘리브레이션**(N을 조정해 구
  1e-7/1e-8 CE 수 재현) vs **fault-density 축**(더 physical, CARE 실험용). → 둘 다 가능,
  CARE는 density 축 권장·pinning 재현은 캘리브레이션 권장.
- **(b) R 값 근거**: 물리적(예: intermittent fault의 재발현 주기) vs 개수목표 역산.
- **(c) emission**: refractory(추천, 개수↔접근빈도 분리 깔끔) vs Bernoulli p_emit(더 단순,
  단 hot page 지배 잔존). refractory 입도 per_page vs per_line.
- **(d) CARE 스윕 포함**: `care_proscrub_clu_*.json`을 sticky로 실제 실행(현재 결과 0건 해소)
  — 목표②의 결정적 실험.

## 11. 검증 계획 (구현 후)
1. uniform/clustered bit-identical 보존(회귀).
2. 같은 seed 재현.
3. Line/Row/Bank 몰림 실측: sticky에서 Line max ≫ 1, per-set retirement 집중 상승 확인.
4. **CARE proactive 실제 발화**(현실 density, widening 없이) — 목표② 증명.
5. 개수 상한 N/R 준수 + death spiral 부재(IPC 붕괴 없음) 확인.
6. 시간축: CE inter-arrival이 접근 burst 상속(Fano>1) 확인 — 목표① 증명.
