# 11. Fault Co-location (Defect Clustering) — 설계안

> 목적: sticky 모델에 **"새 결함이 기존 결함 근처에 태어나는" 공간 상관(reuse)**을
> 도입해, CARE-관련 은퇴가 한 set·한 chip에 집중되게 만든다. 이로써 proactive 발화의
> 병목("은퇴가 흩어져 bias가 12에 못 감")을 물리적으로 정당한 방식으로 해소한다.
> 배경: 100M 멀티코어 실험에서 reactive 은퇴 89건에도 **Peak Bias가 9/12에서 정체**
> (50M과 동일) → **시간이 아니라 집중이 노브**임이 확인됨.

## 0. 한 줄
> **결함은 뭉쳐서 발생한다** (약한 bank/die는 결함을 더 모은다 — 공정 편차·wear-out).
> 이 현상을 `fault_colocate_prob`로 모델링: 새 결함이 확률 p로 기존 결함의
> **bank(+row-group)·chip을 상속**해 같은 자리에 쌓인다. p=0이면 현재 sticky와 동일.

## 1. 왜 필요한가 (물리 + 실험 근거)

- **실험 근거:** proactive 발화 = 한 set(bank×row-group)에서 **같은 chip 은퇴 4건**
  (4×3=bias 12). 현재는 결함이 독립·랜덤 위치라 은퇴가 1024 set × 8 chip에 흩어져
  어느 (set,chip)도 4를 못 채움 (최고 3건 = bias 9). **은퇴 총량(89)이 아니라 분포가
  문제.** → 집중 노브가 필요.
- **물리 근거:** 실제 DRAM 결함은 독립 균등이 아니라 **공간 상관(clustering)**을 가진다.
  공정 편차로 약한 영역/약한 die가 생기면 그 근처에 결함이 더 잘 생기고, wear-out도
  기존 손상 부위를 악화시킨다. 즉 "약한 bank는 결함을 모은다"는 현상을 모델링하는 것 =
  **억지 튜닝이 아니라 누락됐던 물리의 복원.**

## 2. 메커니즘 (결함 탄생 시점)

`birth_fault()`를 다음과 같이 확장:
```
birth_fault():
  if (live 결함이 있음) and (spatial_rng: u < fault_colocate_prob):
      # --- co-located 결함 ---
      seed 결함 E = live 결함 중 균등 추첨
      새 결함.chip     = E.chip                    # lane 상속 (같은 die가 약함)
      새 결함.bank_key = E.bank_key                # 같은 bank
      (scope == "set"이면)  새 결함.row = E.row    # 같은 row-group까지
      새 결함.anchored = true                      # E의 영역은 이미 working set → 즉시 앵커
      새 결함.mode     = FIT 추첨 (독립)           # 종류는 다양할 수 있음
      새 결함.salt     = spatial_rng()             # 자기만의 고장 line 산포
  else:
      # --- fresh 결함 (현재 sticky 그대로) ---
      mode/chip/salt 랜덤, 미앵커 (다음 read에 앵커)
```

**핵심 설계 선택:**
1. **chip은 반드시 상속** — lane 일관성이 CARE bias의 전제. (다른 chip이면 은퇴가
   다른 counter로 가서 bias가 안 생김.)
2. **born-anchored** — E의 영역(bank/row)은 E가 이미 앵커된 곳 = 워크로드가 실제
   접근하는 자리이므로, co-located 결함은 **read를 기다릴 필요 없이 즉시 E의 좌표를
   복사**해 앵커 완료 (starvation 없음).
3. **mode는 독립 추첨** — 한 bank에 cell/row/bank 결함이 섞여 있는 게 현실적. (chip과
   위치만 상속, 종류는 다양.)
4. **salt는 독립** — co-located BANK 결함은 같은 bank지만 **자기만의 고장 line 산포**를
   가짐 (E와 겹치는 line은 union으로 고장, 물리적으로 자연스러움).

## 3. Scope (집중 강도) — config로 선택

| `fault_colocate_scope` | 상속 범위 | 은퇴 집중 | 물리 해석 |
|---|---|---|---|
| `"bank"` | bank_key + chip | bank의 16개 row-group에 분산 (중간) | "이 chip의 이 bank가 약함" |
| `"set"` ⭐ | bank_key + **row** + chip | **한 set에 직접 누적** (강함, 발화 쉬움) | "이 chip의 이 bank의 이 row-구역이 심하게 약함" |

- proactive는 **per-set** 통계이므로, 발화를 직접 겨냥하려면 `"set"`이 효과적.
- `"bank"`는 더 완만 — bank 결함이 원래 bank 전역이라 이미 bank 상속과 유사.
- 권장: 기본 `"set"` (발화 곡선을 명확히 뽑기 위해), `"bank"`는 완만한 변형.

## 4. Config 키 (신규)
```json
"fault_colocate_prob": 0.6,        // 0=현재 sticky, 클수록 뭉침 강함
"fault_colocate_scope": "set"      // "bank" | "set"
```
- 기존 키(`error_cycle_interval`, `fault_density_bank`, `fault_weight_*`, `error_seed`)와
  독립. p=0이면 생성 코드/동작이 현재 sticky와 **바이트 동일**해야 함 (opt-in).

## 5. 기존 노브와의 관계 (보완적)

| 노브 | 무엇을 집중 | proactive에 대한 효과 |
|---|---|---|
| `fault_density_bank` | 한 결함이 **자기 bank 안**에서 얼마나 조밀 | 간접 (은퇴가 bank의 16 row-group에 퍼짐) |
| **`fault_colocate_prob`** | 결함들이 **같은 set/chip**에 얼마나 모임 | **직접** (한 set에 같은 chip 은퇴를 쌓음) |

→ 발화의 정공법은 **colocate_prob**. density는 "각 결함의 생산성", colocate는 "결함들의
집결"을 담당.

## 6. 기대 효과 & 발화 곡선

- p = 0    → 현재 sticky (bias 9에서 정체, 미발화).
- p ↑      → 같은 (set,chip)에 결함·은퇴 누적 → per-set bias 상승 → **어느 p 이상에서
  proactive 발화**.
- 논문용: **p를 sweep(0/0.3/0.6/0.9)해 "defect clustering 강도 vs proactive 발화" 곡선**을
  그린다. p는 물리적 의미(결함 공간상관)를 가진 축이므로 cherry-pick이 아님.

## 7. 재현성 / 불변조건

- co-location 코인·seed 결함 추첨은 **`spatial_rng`**에서 (temporal 스트림 불변).
- 같은 seed → 동일 결과 (결정론적).
- p=0 → uniform/clustered/기존 sticky 전부 **불변**.
- lane 일관성(한 결함의 CE가 한 chip) 보존 — chip 상속이 이를 강화.

## 8. 열린 구현 디테일 (구현 시 확정)

1. **CELL co-located의 anchor_cl:** `"set"` scope에서 CELL 결함이 E의 (bank,row)를
   상속하면, 구체 line 하나가 필요. 방안: (a) E의 row 내 **다음 접근된 line**에 앵커
   (born-anchored 대신 그 row 한정 대기), 또는 (b) row 내 결정론적 오프셋. → (a) 권장
   (starvation 위험 낮음, E의 row는 접근 중).
2. **seed 결함 추첨 풀:** live 결함 전체 균등 vs 최근 결함 편향. → 균등이 단순·재현적.
   (최근 편향은 "새 결함이 최신 약점 근처" 모델링이나 v2로.)
3. **dead 결함 상속 방지:** seed는 `live_fault_indices`에서만 추첨 (은퇴로 죽은 결함
   상속 안 함).
4. **co-located BANK가 bank 전역이면 "set" scope의 row 상속이 무의미** — BANK 결함은
   원래 bank 전체라 row 개념이 약함. → BANK co-located는 `"bank"`처럼 동작(bank+chip
   상속), CELL/ROW co-located만 row까지 상속. (구현 시 mode별 분기.)

## 9. 검증 계획 (구현 후)

1. p=0 → 기존 sticky bit-identical.
2. 같은 seed 재현.
3. **p sweep(0/0.3/0.6/0.9) × C1 멀티코어 50M** → Peak Bias / proactive triggers 곡선.
   기대: p↑ → bias 9 돌파 → 어느 지점에서 발화.
4. lane 일관성·starvation 부재·총 CE 개수 sanity.
5. proactive 발화 시 victim/은퇴 로그 정합성 (기존 F1~ 감사 항목 재확인).

---

*이 설계는 "시간(sim 길이)은 발화 노브가 아님"(50M→100M bias 9→9)을 확인한 뒤, 집중을
물리적으로 정당한 방식(defect clustering)으로 도입하기 위한 것. 구현 전 §8 디테일과
scope 기본값을 확정할 것.*
