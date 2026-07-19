# 08. Fault-Injection Model — 개념 정리 (정독용)

> 2026-07-16 대화에서 도달한 이해를 재구성. 이 문서 하나로 모델을 남에게 설명할 수
> 있는 것이 목표. 코드 수준의 엄밀한 규칙은 03, 여기는 개념과 왜.

## 0. 모델의 정체 — 한 줄

> **물리 현상("faulty 주소는 read마다 CE를 낸다")을 직접 돌리는 게 아니라,
> 그 현상의 결과물인 MC의 CE 로그를 통제된 속도로 직접 생성한다.**
> 타이머가 로그 한 줄의 발행 시각을, 주사위가 소속(누구의 에러인가)을,
> 실제 DRAM read가 주소와 적용 시점을 정한다.

## 0.5 가장 중요한 그림 — 시스템은 두 레이어다

거의 모든 혼란은 "에러에 관한 모든 일을 주입 모델이 관장한다"는 한-레이어 가정에서
나온다. 실제로는 역할이 갈라져 있다:

```
레이어 1 — 발견 (fault-injection model)
  질문: "새 에러가 언제, 어디서 '처음' 관측되는가"
  도구: 타이머(Poisson) + 주사위 1·2·3 + 앵커 + 배달.  예산제 (rate 통제).
  read의 역할: 배달만. 주사위는 전부 시계의 것.

        ↓ 발견 즉시 장부 기록 (error_addresses, ECC cache 등록, fault 구역)

레이어 2 — 결과 (각 scheme의 역학)
  질문: "faulty로 알려진 블록이 그 후 어떻게 행동하는가"
  도구: read가 직접 끈다. 주사위도 예산도 없음.
  ├─ CARE:    tracked 블록의 매 read = 재검출 (+30cyc, S2→S3→retire)
  ├─ Pinning: 그 line의 DRAM read 자체를 제거 (LLC 상주)
  └─ Retire:  그 page의 미래 에러를 영구 차단
```

**"hard fault는 read마다 재검출된다"는 물리 직관은 레이어 2에 구현되어 있다.**
레이어 1이 영속성까지 떠안으면 CE 총량이 접근 패턴에 종속되어 비교가 무너지므로
(§1), rate 통제가 필요한 "발견"만 예산제로 분리한 것. 한 문장으로:

> 발견은 예산제 주입이 만들고, 발견 이후의 모든 일(비용·상태 진행·보호·격리)은
> scheme이 read-driven으로 처리한다. 주입 모델은 CE 로그의 작성자일 뿐,
> 에러 물리학 전체가 아니다.

## 1. 왜 "매 read CE"를 직접 돌리지 않는가

물리적으로 hard fault 주소의 read는 매번 CE가 맞다. 그러나 그대로 돌리면:

1. **개수 통제 상실** — CE 수 = 접근 패턴의 함수. hot line 하나가 CE 수만 건을 만들면
   error rate(1e-5~1e-8)라는 실험 축이 무의미해짐. 우리 rate 자체가 수년치 fault를
   수십 ms로 압축한 가속 주입이라 rate는 통제 노브여야 함.
2. **Baseline 퇴화** — threshold=2 offline은 모든 faulty page가 2번째 접근에서 즉시
   retire → scheme이 아니라 접근 빈도를 측정하게 됨. 페널티(454k cycle)가 접근마다
   터지면 죽음의 나선 (실증: 22시간에 3M instruction 미완).
3. **비용의 물리** — SEC-DED는 인라인 정정이라 CE 1건의 latency ≈ 0. 비용이 실재하는
   이벤트는 기록·retirement·CARE의 BCH decode뿐이고, 모델은 그것만 과금한다.

단, "매 read" 의미론이 실재하는 곳에는 남아 있다(§8 Q5의 scheme별 표 참조).

## 2. 용어 — 세 가지를 분리해서 생각할 것

| 용어 | 뜻 | 갖고 있는 것 |
|---|---|---|
| **Fault (결함)** | 물리적 결함 1개. 지속됨 | mode(점/줄/면), chip(0~7), 앵커 후엔 구역 좌표 |
| **Error / CE (발현)** | 그 결함이 만든 관측 1건. fault 1개가 CE 여러 개를 만듦 (1:N) | 주인 fault, 발행 시각 |
| **배달 (read)** | CE가 시뮬레이션에 실제 적용되는 사건 | 주소·시점을 확정 |

핵심 분리: **소속(누구의 에러)·모양(mode)·die(chip)는 주사위**가 정하고,
**주소는 주사위 없이 실제 read**가 정한다(앵커).

## 3. 에러 한 개의 일생 — 4단계

### 3.1 발행 — 언제
타이머: 평균 `error_cycle_interval` cycle의 exponential 간격 (Poisson).
seed에서 유도된 전용 RNG → 같은 seed = 완전 재현.

### 3.2 소속 — 누구의 에러인가 (주사위 1, 2, 3)

| 주사위 | 언제 굴리나 | 무엇을 정하나 |
|---|---|---|
| **1** | 매 이벤트 | 기존 fault의 반복(70%) vs 새 fault(30%). reuse면 살아있는 fault 중 균등 추첨 |
| **2** | **새 fault 탄생 시 1회만** | mode ~ FIT 비율 (CELL 18.6 : ROW 8.2 : BANK 10.0) |
| **3** | **새 fault 탄생 시 1회만** | chip 0~7 균등 — 어느 x8 die의 결함인가 |

주의: reuse로 뽑힐 때는 **아무 주사위도 다시 굴리지 않는다.** 태어날 때 받은
mode·chip을 평생 유지. fault당 평균 CE 수 = 1/(1−0.7) ≈ 3.3 (기하분포, 실측 일치).

### 3.3 주소 — 앵커 (주사위 없음)

새 fault는 **주소 없이** 태어난다. 그 fault의 첫 CE를 배달받은 read의 좌표
(bank, row, line)가 fault에 복사되어 **1회 영구 동결** — 이것이 앵커.

- 왜 무작위 주소로 미리 안 뽑나: footprint ≪ 물리 메모리라 대부분 접근 불가
  주소에 떨어져 배달 불가(개수 붕괴) + 유효 에러율이 워크로드 의존이 됨.
- 정당화: 접근 안 되는 결함은 CE를 못 낸다 → 우리는 **"관측된 결함"의 조건부
  분포**를 모델링하는 것. 실제 read된 자리는 정의상 관측 가능한 자리.

### 3.4 배달 — 자격 규칙

이벤트는 pending 큐에서 **자격 있는 read**를 기다렸다가 그 read의 주소에 적용된다
(read당 최대 1개, 오래된 것부터, retire된 page의 read는 자격 없음):

```
미앵커 fault의 이벤트 → 아무 read (소비 순간 앵커)
CELL → 정확히 그 line     ROW → 그 (bank, row)     BANK → 그 bank
굶으면 완화: 1M cycle → 같은 bank 아무 read, 2M → 아무 read
             (이벤트별 완화. fault의 구역 자체는 불변)
```

### 3.5 두 개의 시간축 — 주사위는 시계가 굴리고, read는 배달만 한다

가장 흔한 오해: "error address X에 또 접근하면 그때 주사위를 굴린다?" — 아니다.
**접근은 그 어떤 주사위도 굴리지 않고 fault도 만들지 않는다.** 주사위는 전부
타이머(read와 무관한 Poisson 시각)의 사건이다:

```
[타이머 tick ①]  주사위1→신규, 주사위2→CELL, 주사위3→chip5. fault F 탄생(주소 미정), e1 큐로
[read X]         e1 배달 → F가 X에 앵커. "X의 첫 에러".  ← read는 주사위 0개 굴림
[read X 또]      큐 비어있음 → 아무 일 없음 (물리론 CE지만 예산 없으면 기록 안 함)
[타이머 tick ②]  주사위1→reuse→F 당첨. e2 큐로  ← 이 순간 X 근처에 read가 없어도 됨
[read X 또]      e2의 주인 F의 구역에 X 포함 → 배달 → "X의 두 번째 에러"
```

X를 백만 번 읽어도 큐에 이벤트가 없으면 에러는 0번. "X가 error address"라는 말의
정확한 뜻은 "**F의 구역에 X가 있다** → F 몫의 예산이 발행되어 있을 때 X를 읽으면
또 에러가 난다"이지, X를 읽는 행위가 에러를 만든다는 뜻이 아니다.

### 3.6 시간축의 수학 — "1e-8이 여전히 1e-8"인 이유

주입 간격은 지수분포, 개수는 Poisson분포다:

```
X ~ Exp(λ),  λ = 1/interval          (라벨 1e-8 ↔ interval = 144,000 cycles)
f(x) = λe^(−λx),   E[X] = 1/λ = 144,000

T cycle 동안의 에러 개수:  N(T) ~ Poisson(λT)
P(N=k) = (λT)^k e^(−λT) / k!,   E[N] = T/144,000,   SD = √(λT)
```

검증 예 (mcf 20M instr, T = 55.65M cycles):
E[N] = 55,650,000 / 144,000 = **386.5**, SD ≈ 19.7 → 관측 **390** (0.18σ) ✓

**구모델과의 일치 — 같은 λ의 같은 프로세스**: 레거시 uniform 모드도 다음 발생
시각을 X ~ Exp(1/interval)로 뽑았다. 즉 두 모델은 정의상 동일한 rate의 Poisson
process이며, "1e-8"이라는 라벨의 의미(λ = 1/144,000)는 바뀐 적이 없다.
미세 구현 차이 두 개는 모두 무시 가능 규모:

1. 레거시는 발화 시 "현재 cycle"에서 다음 시각을 재기점 → 이벤트당 잔차 ≤ DRAM
   1 tick(CPU 3~4 cycle) = interval의 **0.003%** 편향
2. 레거시는 호출당 최대 1발 (clustered는 catch-up while로 진짜 Poisson) → 한 tick에
   2발 이상 몰릴 확률 ≈ (4/144,000)²/2 ≈ **4×10⁻¹⁰**

공간축(fault/reuse/앵커)은 "누구의 에러이고 어디로 가는가"만 정할 뿐 발생 개수에
관여하지 않고, 기아 단계 확장이 배달을 보장하므로 E[N]이 실제 소비량으로 이어진다
(문서화된 예외: off@1e-8 극한의 대량 영구 retire → 09 §5).

실측 대조: uniform 453 vs clustered 454/456 (E≈444) · 3,837 vs 3,839 (E≈3,888) ·
멀티코어 6,185 vs 6,059 — 전부 ±√N 이내. 기억용 한 줄: 지수분포의 무기억성
P(X>s+t | X>s) = P(X>t)가 "일정 주기가 아니라 언제든 같은 확률"의 수학적 표현이고,
그 귀결이 Poisson 개수 분포다.

## 4. 주사위 3(chip)의 엄밀한 의미 — 주소는 chip을 결정하지 않는다

x8 rank에서 64B 블록은 8개 die가 8B씩 내놓아 만들어진다:

```
chip0  chip1  chip2  chip3  chip4  chip5  chip6  chip7
 8B     8B     8B     8B     8B     8B     8B     8B   → 합쳐서 64B
```

- **주소가 정하는 것** = (bank, row, col) 배열 좌표. 단, 이 좌표는 8개 die
  **모두에 동시에** 적용된다 (deterministic — 여기까진 직관대로).
- **주소가 못 정하는 것** = 그 좌표의 셀이 8개 die에 병렬로 존재하는데,
  **어느 die가 불량인가.** 8권짜리 전집에서 "137페이지"는 8권 모두에 있다 —
  어느 권이 인쇄 불량인지는 페이지 번호가 못 정한다. 그건 제조 우연 → 주사위 3.

**chip이 fault의 속성이어야 하는 이유**: die 하나의 결함은 그 die가 기여하는
byte lane에서만 깨진다. 따라서 한 fault의 CE들은 — ROW/BANK fault처럼 **주소가
여러 개라도 — 전부 같은 lane**에서 나타난다. 이 "교차-주소 lane 일관성"이
CARE가 감지하는 지문이다. chip을 주소에서 유도(해시)하면 주소마다 lane이
제각각이 되어 이 지문이 파괴된다.

## 5. Global counter와 트리거 — 시나리오 세 개

Set(= 1 bank × 1 row구역)마다 4-bit counter 8개(lane별). **retirement가 일어날
때만** 그 retirement를 만든 fault의 chip 칸에 +3 (err_count cap). 트리거(OR):
어떤 counter 포화(15) **또는** max−min ≥ 12.

```
A. 단일 fault 지배 (chip3 bank fault가 이 구역 retirement를 독점):
   [0, 0, 0, 12, 0, 0, 0, 0]   ← 4회 만에 bias 12 → 발화 ✔
   의미: "chip 3의 이 bank가 죽어간다" — CARE가 노리는 시나리오

B. 여러 fault, 서로 다른 chip (산발적 결함):
   [0, 3, 0, 0, 3, 0, 0, 3]    ← bias 3 → 발화 ✘
   의미: 특정 die의 구조적 고장이 아님 — bias 검사가 정확히 이걸 걸러냄

C. 총체적으로 병든 region (OR가 추가로 잡는 경우):
   [12, 15, 9, 12, 6, 9, 12, 9] ← bias 9 < 12지만 counter 하나가 15 → 발화 ✔
   (어느 경우든 counter 15 = 같은 chip발 retirement 5회는 필요)
```

요점: **주사위 3이 균등해도 counter는 균등해지지 않는다** — counter를 채우는
단위가 에러가 아니라 fault이고, 편중은 chip 분포의 우연이 아니라 **단일 fault의
반복(reuse)**이 만든다. 한 set에서 여러 counter가 같이 오르는 것(B)도 정상이며,
bias는 "올라갔냐"가 아니라 "한 놈만 유독 올라갔냐"를 본다. bias ≥ 12 ≈ 같은
chip발 retirement 4회 (min은 8개 전체의 최솟값이라 조용한 lane이 있으면
bias ≈ 최대 counter 값).

## 6. Lifecycle — retire와 fault의 죽음

Page retire = 건강한 frame으로 migration. 그 순간:

- 그 page의 error address들은 정상 복귀 (pinning 게이트 해제 + LLC error way 회수
  + CARE entry/증거 제거) — "주소를 되돌리는 작업"은 전부 구현되어 있음
- 그 page에 앵커된 **CELL/ROW fault는 죽는다** (옛 frame은 더 이상 읽히지 않음).
  **BANK fault는 생존** (bank 회로는 page 이사로 안 고쳐짐 — CARE proactive의 전제)
- 죽은 fault 몫의 pending 이벤트는 산 fault로 **재샘플** → 총량 보존
- Retire된 page는 영구 기록되어 다시는 에러를 받지 않음 (재-retire 루프 없음)

## 7. 워크로드가 개입하는 곳 / 못 하는 곳

| | 워크로드 의존? |
|---|---|
| 새 fault의 집 위치 | **의존** (앵커 = 트래픽을 따름; 조건부 분포 논리로 정당) |
| 배달 시점/속도 | **의존** (그 구역을 안 읽으면 굶음 — 예: pinning이 line을 LLC에 가두면 그 CELL fault의 재발현이 굶는 것 = scheme 효과의 자연 반영) |
| **총 에러 수** | **비의존** — 기아 확장이 배달을 보장. 개수는 rate 설정만의 함수 (실측: uniform 453 vs clustered 454/456) |

## 8. FAQ — 실제로 가졌던 의문들

**Q1. Error address를 read하면 무조건 CE 아닌가?**
물리적으로 맞다. 하지만 모델은 그 스트림 전체가 아니라 rate로 샘플링된 CE 로그를
생성한다 (§1의 세 이유). 반복 read의 비용이 실재하는 곳에는 남아 있다 → Q5.

**Q2. 70%가 "새로운 곳에 에러", 30%가 "에러 안 만듦"?**
반대 + 둘 다 에러를 만든다. 70% = 기존 결함의 반복(기존 구역 안), 30% = 새 결함의
첫 CE(새 자리). 버려지는 이벤트는 없다 — 그래서 총량 보존.

**Q3. reuse 때 FIT 비율로 line/row/bank 중 어디 넣을지 정하나?**
아니다. FIT(주사위 2)는 탄생 시 1회. reuse로 뽑힌 fault는 자기 mode의 구역을
그대로 따른다.

**Q4. 주소가 chip을 deterministic하게 정하는 것 아닌가?**
아니다 — §4. 주소는 배열 좌표(8 die 공통)를 정하고, 어느 die가 불량인지는 독립된
물리 사실(주사위 3). 한 fault의 여러 주소가 같은 lane에서 깨지는 상관이 핵심.

**Q5. 등록된 error address를 다시 read하면?**
| Scheme | 처리 | 근거 |
|---|---|---|
| Pinning | DRAM read 자체가 없음 (LLC 상주) | 반복 CE 차단이 scheme의 이득 |
| Baseline | 추가 비용 없음 | SEC-DED 인라인 정정 ≈ 0 cost, 중복 관측은 상태 불변 |
| CARE | **매 read마다 BCH decode +30cyc** | CARE의 실제 하드웨어 동작 |

**Q6. 한 set에서 counter 하나만 마구 오르나?**
아니다 — 여러 개가 같이 오를 수 있고(§5 시나리오 B), 그게 정상 노이즈. 트리거는
"하나만 유독"(bias) 또는 "하나가 15까지"(포화)일 때만.

**Q7. 접근 안 된 random 주소에 fault를 두면 개수가 줄지 않나?**
그래서 미리 안 뽑는다(앵커, §3.3) + 기아 확장이 배달을 보장. 실측 ±1% 일치.

**Q8. Retire하면 그 page의 error address를 정상으로 되돌려야 하지 않나?**
전부 구현됨 (§6). LLC 일반 way의 사본만 남는데, 데이터를 모델링하지 않으므로
"이사 간 frame의 데이터"와 동치이고, 지우면 오히려 migration 비용 이중 과금.

**Q9. CARE에서 S2까지 간 블록은 reuse가 안 뜨면 S0으로 돌아가나? S3 가려면 reuse가 필요한가?**
둘 다 아니다 — 레이어 구분(§0.5)의 대표 사례. S2→S0 경로는 논문의 soft-error
치유 경로라 hard-only 모델에는 없다 (S2는 read가 올 때까지 그냥 머묾). 그리고
주입 예산이 필요한 전이는 **S0→S1(발견) 단 하나**. S1→S2(write/scrub),
S2→S3(그 블록의 아무 read), S3→retire(또 아무 read)는 전부 레이어 2에서
read가 끈다 — "hard fault는 읽을 때마다 재검출"이 그대로 구현된 곳. reuse가
tracked 블록에 또 떨어지면 ALREADY_TRACKED(상태 불변)이고, reuse의 CARE 역할은
같은 region의 **다른 line들**에 새 등록을 만들어 retirement를 반복시키는 것뿐.

**Q10. reuse의 "살아있는 fault 중 랜덤 추첨" — X에 접근했는데 왜 다른 fault와 엮이나?**
안 엮인다 — 추첨의 방향이 반대다. 추첨은 read가 아니라 타이머의 사건이며,
"이 접근을 누구 걸로 할까"가 아니라 **"다음 에러 예산의 수령자가 누구냐"**를
정한다. 당첨된 fault의 소포는 **그 fault의 구역으로 가는 read만** 기다리므로,
X의 read는 X를 구역에 포함하는 fault(자기 CELL/자기 row의 ROW/자기 bank의
BANK)의 소포나 미앵커 소포만 받을 수 있다. 남의 구역 소포가 X에 배달되는 일은
없다(기아 완화 예외뿐). 비유: 본사가 송장에 수신자를 적고(추첨), 소포는 수신자
주소지행 트럭에만 실린다 — 당신 집 앞을 지나는 트럭은 당신 앞으로 온 소포가
있을 때만 초인종을 울린다.

**Q11. 새 fault(30% 분기)는 모든 bank·chip에 균일하게 분포하는 것 아닌가?**
맞다 — 그리고 그게 의도된 물리다. 결함의 "탄생 위치"는 균등한 게 옳다 (제조
결함은 die/bank를 가리지 않음; bank는 트래픽 가중 균등, chip은 주사위 균등).
뭉침은 위치가 아니라 **반복(reuse)**에서 온다. 다트판 비유: 다트(fault)는 아무
데나 꽂히지만(균등), 꽂힌 자리마다 여러 발(에러, 평균 3.3발)이 몰린다 — 다트의
분포는 균등해도 구멍의 분포는 울퉁불퉁하다. 실측: Banks Touched 55~64(배치 균등)
+ Top-1 share 5.3% vs 균등 1.6%(에러 뭉침). reuse=0이면 정확히 기존 uniform
모델로 퇴화 — 이 연속성이 설계 축이다. 참고: read가 먹는 것은 fault가 아니라
fault의 이벤트 1건이며, fault는 살아남아 또 뽑힐 수 있다.

**Q12. 새 fault가 쌓여서 모든 bank가 fault로 덮이면, 모든 read가 에러를 내지 않나?**
아니다 — 에러 수는 1개도 안 늘어난다. "구역 안"의 뜻은 "에러가 난다"가 아니라
"타이머가 발행한 소포를 받을 **자격**이 있다"이고, 소포는 fault 수와 무관하게
예산(rate)만큼만 발행된다 (1e-8 스모크: read 132k회 vs 소포 390개 → 전 bank가
덮여도 99.7%의 read는 깨끗). 커버리지가 넓어질수록 바뀌는 것은 개수가 아니라
**분포** — 배달이 "다음 read가 가져감"에 가까워져 uniform 쪽으로 희석된다.
물리적으로도 옳은 퇴화 (모든 bank에 결함이 있으면 에러 위치의 특별함이 실제로
사라짐). 뭉침의 정도 = (fault 수 : 예산) 비율이며 reuse가 통제한다. 각주:
등록된 특정 line들의 재-read 비용(CARE decode)은 레이어 2의 일이고 그 line들에
한정 — "구역 전체"가 비용을 내는 게 아니다.

**Q13. 논문은 global counter가 "bank"라는데, lane(chip)으로 구현한 게 맞나?**
맞다 — 그리고 논문도 틀리지 않았다 (전문 적대적 재검증, 07 §2b). "DRAM bank"의
지시 대상이 rank-level 논리 bank가 아니라 **chip 내부의 bank array**다: rank의
bank b는 물리적으로 8개 chip 각각의 bank-b 조각의 합집합이고, set index가
(ch,rank,bank)를 고정하므로 counter i = "chip i의 그 bank 조각". 이 독해에서
"one counter for a DRAM bank"는 정확한 문장이 된다. rank-level 독해는 세 논증으로
붕괴: ① set index가 bank 비트를 전부 소비 → 한 set = 단일 bank → counter 7개가
영구 0, 논문의 8-uniform-RV 통계 성립 불가 ② entry에 bank 필드가 없어
bank-indexed 누적은 구현 자체가 불가 (lane은 local[i]→global[i] 위치 배선으로 완결)
③ lockstep 구조상 rank-level bank 고장은 8 lane을 균등하게 깨뜨려 bias가 생길 수
없음 — bias 검출기가 잡을 수 있는 것은 chip(과 chip 내부 bank)뿐. 원문 인용 전체는
07 §2b.

## 9. "Fault-injection modeling 어떻게 구현했어?" — 교수님께 한 호흡으로

> 기존 구현은 일정 간격으로 발생시킨 에러를 "다음 DRAM read의 주소"에 붙이는
> 방식이라 에러가 bank들에 균등하게 흩어졌는데, 이를 시간축과 공간축으로
> 분리했습니다. **시간축**은 seed로 재현 가능한 Poisson process로 기존 error rate
> 스케일(1e-5~1e-8)을 그대로 유지해 총 에러 수를 보존하고, **공간축**은 field
> study의 permanent FIT 비율(single-bit 18.6 : row 8.2 : bank 10.0)로 종류가
> 정해지는 "지속성 있는 fault"를 도입해 — 각 에러의 70%는 기존 fault의
> 재발현으로서 그 fault의 구역(같은 line/row/bank, 같은 chip lane) 안에만
> 떨어집니다. Fault의 위치는 실제 접근된 주소에 앵커되므로 모든 에러가
> 워크로드에 관측 가능하고, page retirement 시 CELL/ROW fault는 소멸(migration
> 의미론), BANK fault는 생존해 bank 단위 대응(CARE proactive)의 전제를 만듭니다.
> 검증은 ① uniform 모드 bit-identical 보존(기존 결과 유효) ② 총량 ±1% 일치
> ③ 같은 seed 완전 재현 ④ CARE proactive trigger의 실제 발화 확인으로 마쳤습니다.

## 10. 한 문장 재조립

> 타이머가 울리면 에러 1개가 확정되고, 70%면 기존 결함이 "또"(그 결함의 mode가
> 정한 구역 안, 그 결함의 lane으로), 30%면 새 결함 탄생(mode는 FIT, die는 균등,
> 집은 첫 배달 read의 자리) → 구역에 맞는 read를 기다려 부착, 굶으면 bank→전체로
> 풀려 어쨌든 배달 → retire는 그 page의 CELL/ROW 결함을 죽이고 BANK는 살아남아
> 다음 page를 때린다 → **위치와 lane은 뭉치고, 개수는 정확히 유지된다.**
