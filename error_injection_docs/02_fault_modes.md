# 02. Fault Mode: CELL / ROW / BANK의 의미

## 1. DRAM 물리 구조 복습

DRAM bank는 2차원 셀 배열이다.

```
                 column (bitline) →
        ┌────────────────────────────┐
 row    │ c c c c c c c c c c c c c │  ← wordline 하나가 row 하나를 activate
(word-  │ c c c c c c c c c c c c c │
 line)  │ c c c ✗ c c c c c c c c c │  ✗ = single-cell fault
   ↓    │ ✗✗✗✗✗✗✗✗✗✗✗✗✗✗✗✗✗✗ │  ← row fault (wordline 결함)
        └────────────────────────────┘
          bank 전체 오동작 = bank fault (row decoder / sense amp / 제어 회로 결함)
```

- **row**: wordline 하나로 동시에 activate되는 셀들의 집합. row buffer로 통째로 읽힌다.
- **column**: bitline 방향의 셀 집합.
- **bank**: row decoder, sense amplifier, 제어 로직을 공유하는 독립 배열 단위.

## 2. Field study가 관찰한 fault 분류

대규모 필드 데이터(Sridharan & Liberty, *"A Study of DRAM Failures in the Field"*,
SC'12 — Jaguar 슈퍼컴퓨터 DDR-2 수만 DIMM; 후속 DSN'13, ASPLOS'15도 유사)는 고장난
DRAM device의 fault를 **결함이 걸친 영역의 크기**로 분류했다:

| Fault 유형 | SC'12 비율(대략) | 물리적 원인 예시 |
|---|---|---|
| Single-bit (cell) | ~50% | 셀 커패시터/트랜지스터 결함, weak cell |
| Single-word | ~2.5% | 특정 word 접근 경로 결함 |
| Single-column | ~10% | bitline / column decoder 결함 |
| Single-row | ~8% | wordline / row driver 결함 |
| Single-bank | ~17% | row decoder, sense amp 등 bank 공유 회로 결함 |
| Multi-bank / multi-rank | ~12% | 칩 글로벌 회로, I/O, TSV 등 |

핵심 관찰 두 가지:

1. **Fault는 지속된다(persistent/hard/intermittent)** — 한번 생긴 결함 영역은
   접근할 때마다 (또는 간헐적으로) CE를 계속 만든다. 일회성 soft error(입자 충돌)와
   근본적으로 다르며, 필드 CE의 대부분은 소수의 하드 fault가 반복 발현한 것이다.
   (CARE, ArchShield, FreeFault 등이 전부 이 관찰 위에 서 있다.)
2. **영역 크기가 계층적이다** — 한 셀만 죽기도 하고, row/column 단위로 죽기도 하고,
   bank 공유 회로가 죽으면 그 bank 전체에 넓게 퍼진 주소에서 에러가 난다.

## 3. 우리 모델의 3-mode 단순화

시뮬레이터에서 fault mode는 **"이 fault의 에러가 재발현될 수 있는 주소 영역"**을 정한다.

| Mode | 재발현 매칭 조건 | 시뮬레이션에서 만드는 패턴 | 주로 자극하는 메커니즘 | Page retire 시 |
|---|---|---|---|---|
| `CELL` | 같은 cache line (64B) | 한 line에서 CE 반복 | CARE S1→S2→S3 (같은 주소 재에러로 hard 확인), pinning ALREADY_KNOWN 경로 | **죽음** (migration이 셀을 회피) |
| `ROW`  | 같은 (bank, DRAM row) | 인접 주소들(한 row의 여러 line)에 CE 뭉침 | page당 다중 에러 → retirement threshold, PERT 다중 슬롯 | **죽음** (row ⊂ page) |
| `BANK` | 같은 bank (channel/rank/bankgroup/bank) | 한 bank의 여러 row/page에 넓게 뭉침 | CARE proactive의 bank-bias 카운터, bank 편중 통계 | **생존** (bank 회로는 그대로) |

죽은 fault의 Poisson 이벤트 몫은 살아있는 fault로 재샘플되어 총량이 유지된다.
BANK fault만 retire를 넘어 살아남는 구조가 "page retirement로는 bank fault를 못 잡고
CE가 계속 나온다 → bank 단위 대응 필요"라는 CARE 논문의 서사를 자연스럽게 재현한다.

single-word와 single-column을 별도 mode로 두지 않은 이유:
- **word**는 cache line(64B)보다 작아서 line 단위로 에러를 기록하는 우리 파이프라인에서
  CELL과 구별되지 않는다 → CELL에 흡수.
- **column** fault는 "여러 row에 걸쳐 같은 column offset"이라 address mapping을 거치면
  한 bank 안에 넓게 흩어진 주소로 보인다 → 시뮬레이션 효과가 BANK와 사실상 동일 → BANK에 흡수.
- multi-bank/multi-rank는 사실상 device 교체 대상(uncorrectable로 빠르게 격상)이라 제외.

## 4. 기본 가중치 — CARE Table II의 Permanent FIT 비율

CARE 논문(HPCA'21) Table II (Sridharan field study 기반, 1Gb chip FIT):

| Failure Mode | Transient FIT | Permanent FIT | 우리 모델 |
|---|---|---|---|
| Single Bit | 14.2 | **18.6** | `CELL` |
| Single Word | 1.4 | 0.3 | 미모델 (cache line 단위 기록에서 CELL과 구별 불가, 비중 0.8%) |
| Single Column | 1.4 | 5.6 | 미모델 (효과가 BANK와 유사하나 단순화를 위해 제외) |
| Single Row | 0.2 | **8.2** | `ROW` |
| Single Bank | 0.8 | **10.0** | `BANK` |
| Multiple Banks | 0.3 | 1.4 | 미모델 (사실상 device 교체 대상) |
| Multiple Ranks | 0.9 | 2.8 | 미모델 (동일) |

→ 기본값 `fault_weight_cell=18.6, fault_weight_row=8.2, fault_weight_bank=10.0`
(합으로 정규화되므로 FIT 값을 그대로 config에 사용: 비율 50.5% / 22.3% / 27.2%).

**중요 — FIT는 비율로만 차용한다.** FIT의 절대값(10⁹ device·hour당 fault 수)을
사이클 단위로 환산하면 수십 ms짜리 시뮬레이션 창에서는 fault가 사실상 0건이다.
따라서 **시간축 발생률은 기존 가속 주입 스케일(`error_cycle_interval`,
BER 1e-5~1e-8 sweep 환산값)을 유지**하고, 필드 데이터에서는 "발생한 fault의
공간적 구성비"만 가져온다 (accelerated fault injection의 표준 논법).
Transient 열은 hard-fault-only 모델 정책상 제외한다.

실험 목적에 따라 JSON에서 자유롭게 조정 가능 (예: CARE proactive 스트레스
테스트 → bank 비중 상향, CARE 전용 ablation → `fault_weight_row: 0`).

## 5. 재발현 횟수와 fault_reuse_prob

이벤트가 기존 fault를 재발현할 확률이 `p = fault_reuse_prob`이면, fault 하나가 받는
평균 발현 횟수는 기하급수적으로 `1/(1-p)`다 (p=0.7 → fault당 평균 ~3.3회, 기본값).
p를 올리면 같은 에러 총량이 더 적은 fault에 집중되어 "심하게 아픈 소수 fault" 시나리오,
내리면 "넓게 퍼진 다수 fault" 시나리오가 된다. p=0이면 모든 에러가 새 fault의 첫
발현이 되는데, 첫 발현은 접근 위치에 앵커되므로 UNIFORM과 유사한 분포로 수렴한다
(단 RNG 스트림은 다름).
