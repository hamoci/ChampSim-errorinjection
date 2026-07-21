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

`birth_fault()`를 다음과 같이 확장 (**실제 구현 기준** — 초안의 born-anchored에서 수정됨, §8 참조):
```
birth_fault():
  if (ANCHORED live 결함이 있음) and (spatial_rng: u < fault_colocate_prob):
      # --- co-located 결함 ---
      seed 결함 E = ANCHORED live 결함 중 균등 추첨      # 미앵커 부모는 좌표(bank_key)가 없음 → 제외
      새 결함.chip            = E.chip                  # lane 상속 (같은 die가 약함)
      새 결함.target_bank_key = E.bank_key              # 같은 bank 조준
      (scope=="set"이면) 새 결함.target_rowgroup = E.row_group  # 같은 row-group까지
      새 결함.colocated = true                          # 미앵커 유지 — 아래 (2) 참조
      새 결함.mode     = FIT 추첨 (독립)                # 종류는 다양할 수 있음
      새 결함.salt     = spatial_rng()                  # 자기만의 고장 line 산포
      # 앵커는 consume 시점: target 영역(bank[+row-group])으로 오는 첫 read에만 → 그 read의 실제 line 취함
  else:
      # --- fresh 결함 (독립 sticky) ---
      mode/chip/salt 랜덤, 미앵커 (다음 read에 앵커)
```

**핵심 설계 선택:**
1. **chip은 반드시 상속** — lane 일관성이 CARE bias의 전제. (다른 chip이면 은퇴가
   다른 counter로 가서 bias가 안 생김.)
2. **born-unanchored + 영역 게이트** (초안의 born-anchored에서 변경) — born-anchored는
   CELL 결함에 구체 line이 필요한 문제(§8)가 있어, 구현은 co-located 결함을 **미앵커로
   두고 target 영역으로 오는 첫 read에 앵커**한다. 그 read의 실제 line을 취하므로
   CELL/ROW/BANK 전부 구체 좌표를 얻음.
   - **트레이드오프: starvation 가능** — target 영역이 다시 안 읽히면 미앵커로 남아 CE를
     안 냄. 단 실측상 무시할 수준(p9 테스트 unanchored 0(bank)/24(set)), 굶는 건 "접근
     안 되는 영역의 결함"뿐이라 물리적으로도 맞음.
3. **부모는 ANCHORED 결함만 추첨** — 미앵커 부모는 `bank_key=0`이라 상속하면 bank 0로
   잘못 집중(spurious). anchored 부모는 target 영역이 실제 접근된 곳임을 보장 → starvation도
   완화. (앵커된 결함이 아직 없으면 fresh 결함으로 fallback.)
4. **mode는 독립 추첨** — 한 bank에 cell/row/bank 결함이 섞여 있는 게 현실적. (chip과
   위치만 상속, 종류는 다양.)
5. **salt는 독립** — co-located BANK 결함은 같은 bank지만 **자기만의 고장 line 산포**를
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

## 9b. 파라미터 실제값 근거 (grounded / accelerated / swept·calibrated)

cherry-pick을 피하려면 각 파라미터의 값 출처를 **3범주로 명시**한다. 논문에도 "어느 값이
문헌 고정 / 어느 값이 가속 / 어느 값이 sweep·calibrate인지" 표로 밝힐 것.

| 파라미터 | 범주 | 실제값 / 출처 |
|---|---|---|
| `fault_weight_cell/row/bank` (mode 비율) | **grounded (문헌 고정)** | CARE HPCA'21 **Table II** permanent-FIT: single-bit **18.6** / single-row **8.2** / single-bank **10.0** (원출처 Sridharan & Liberty, SC'12 필드). 그대로 사용 |
| CARE 하드웨어 (1024 set · 2 way · 8×4-bit counter · **bias≥12** · **sat 15** · BCH **30cyc** · retire threshold) | **grounded** | CARE HPCA'21 §III. 이미 구현·사용 중 |
| `error_cycle_interval` (발생률) | **accelerated (표준 논법)** | FIT 절대값(10⁹ device·hr당)은 수십 ms 창에서 ~0건이라 사용 불가 → 가속 주입 스케일(1e-5~1e-8 sweep). "발생률은 가속, 공간 구성비는 문헌" = accelerated fault injection 표준 |
| `fault_density_bank` (bank 결함 밀도) | **swept / calibrated** | 필드에 "bank의 몇 %"라는 직접 값 없음. 제약: CE-correctable이어야 함(else UE=장비교체). → **sweep**(0.02~0.5)하거나, 관측 CE rate를 재현하도록 **calibrate** |
| `fault_colocate_prob` (결함 공간상관) | **swept / calibrated** | 필드는 **강한 공간 상관**을 보고(Sridharan et al. SC'13 "Feng Shui"; Meza et al. DSN'15 — 소수 영역이 대부분 에러 유발) 하나 clean한 단일 p는 없음. → **sweep**(0/0.3/0.6/0.9)하거나, 필드의 "재발 위치발 에러 비율" 또는 "결함당 에러 분포"를 재현하도록 **calibrate** |

**원칙:**
1. **grounded는 논문값 고정** — FIT 비율, CARE 하드웨어 임계는 절대 임의로 안 바꿈.
2. **swept는 sweep해서 곡선으로 보고** — density·colocate_prob는 단일 magic number 대신
   "값 vs (bias/발화/성능)" 곡선. p는 "결함이 얼마나 뭉치나"라는 **물리적 의미를 가진 축**.
3. **calibrated가 더 강함** — 가능하면 (density, colocate_prob)를 **필드의 관측 통계
   (결함당 에러 분포·재발 비율)를 재현하도록 맞춤** → "임의값"이 아니라 "필드 재현값"이 됨.
4. **정직성 표기 필수** — 리뷰어가 cherry-pick을 의심하지 않도록, 세 범주를 논문에 명시.

> 주의: 위 문헌값 중 FIT 비율(18.6/8.2/10.0)과 CARE 하드웨어 임계는 repo 문서(02, 07)에서
> 이미 검증됨. density·colocate는 **문헌에 직접 값이 없어** sweep/calibrate가 정당한
> 경로다. 논문 작성 시 Sridharan SC'12/SC'13, Meza DSN'15의 정확한 수치를 재확인해
> "값" 또는 "범위 근거"로 인용할 것.

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
