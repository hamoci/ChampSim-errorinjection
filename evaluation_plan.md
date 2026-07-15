# Evaluation Plan: LLC Pinning with ETT Bloom Filter

## 논문의 핵심 주장 (Story)

> 2MB huge page 환경에서 DRAM CE가 발생하면, 기존 방식은 전체 2MB page를 retire해야 한다.
> 우리는 **LLC error way pinning + ETT bloom filter**로 error cache line만 격리하여,
> page retirement을 최대한 지연시키면서도 성능 저하를 최소화한다.

이 주장을 뒷받침하기 위해, 아래 순서로 evaluation을 구성한다.

---

## Section 1: "Pinning이 실제로 동작하는가?"

**스토리**: CE가 발생한 cache line을 LLC error way에 pin하면, 이후 접근 시 faulty DRAM cell을 회피하여 LLC hit으로 처리된다. Pin이 없으면 매번 DRAM에 재접근해야 하고, corrected data를 다시 받아야 한다.

**보여줄 데이터:**
- **Pin Hit Rate** = error way hit 횟수 / (해당 error page에 대한 전체 LLC 접근 횟수)
  - Pin hit이 높을수록 DRAM re-access 회피 효과가 큼
  - "Pin된 데이터가 실제로 재사용되고 있다"를 보여주는 핵심 metric
- **DRAM Access 감소량** = Baseline(no pinning) 대비 pinning ON일 때 DRAM access 수 차이
  - Error page에 대한 DRAM access만 별도 집계하면 더 명확

**왜 중요한가**: Pin hit이 낮으면 error way가 LLC capacity만 낭비하는 것이고, 높으면 contribution이 정당화된다.

---

## Section 2: "성능 저하가 얼마나 작은가?"

**스토리**: LLC way의 일부를 error way로 전용하면 normal data의 cache capacity가 줄어든다. 그러나 error way 수가 적고 (최대 8/16), error page 수도 적으므로 IPC 영향은 미미하다.

**보여줄 데이터:**
- **IPC 비교** (3-way):
  1. Baseline: no error (이상적 상한)
  2. Pinning ON: CE 발생 + LLC pinning
  3. Pinning OFF: CE 발생 + 즉시 retirement (기존 방식)
- **Workload별 IPC 변화**: SPEC CPU, cloud workload 등에서 pinning ON/OFF 비교
  - Memory-intensive workload에서 capacity 손실 영향이 더 클 수 있으므로, 이를 정직하게 보여줌
- **Error Way 점유율**: 시뮬레이션 종료 시 error way가 LLC의 몇 %를 차지하는지
  - "전체 LLC의 X% 미만만 사용, 사실상 무시 가능"

**왜 중요한가**: Reviewer는 "pinning이 LLC capacity를 너무 많이 잡아먹지 않느냐"를 반드시 물어본다. IPC + capacity 수치로 선제 답변.

---

## Section 3: "Bloom filter가 충분히 정확한가?"

**스토리**: ETT bloom filter는 false positive이 존재하여, 정상 cache line도 error way에 pin될 수 있다. 그러나 m=256, k=4 기준 FP rate은 이론적 ~2.4%(n=32)이며, 실측에서도 LLC capacity에 미치는 영향은 미미하다.

**보여줄 데이터:**
- **Bloom Filter False Positive Rate (실측)**:
  - `is_error_data()` true 판정 중 실제 error position이 아닌 비율
  - 이론값과 실측값 비교
- **FP로 인한 추가 pin 수**: 실제 error 수 vs 실제 pin된 cache line 수의 차이
  - 현재 로그에서도 관찰: 31개 unique error에 67개 cache line invalidated → ~36개가 FP로 pin
- **Bloom filter size sensitivity**: m=128/256/512에서 FP rate + IPC 변화
  - m이 클수록 FP 줄지만 HW overhead 증가 → trade-off 그래프

**왜 중요한가**: "Bloom filter를 왜 선택했는지, exact tracking 대비 trade-off가 합리적인지"에 대한 답.

---

## Section 4: "Retirement을 얼마나 지연시킬 수 있는가?"

**스토리**: 기존 방식(4KB page, 즉시 retire)은 CE 1개에 page 전체를 offline한다. 우리는 threshold=32까지 CE를 수용하면서 pinning으로 보호하므로, page retirement 빈도가 대폭 감소한다. 이는 가용 physical memory를 더 오래 유지한다는 의미다.

**보여줄 데이터:**
- **Retirement 빈도 비교**:
  - Baseline: threshold=1 (CE 즉시 retire)
  - 4KB page: threshold=1 (기존 방식)
  - Our approach: threshold=32
  - 같은 error rate에서 retirement 횟수 비교
- **Threshold sensitivity**: threshold=16/32/64에서 retirement 횟수 + IPC
  - Threshold가 높으면 retirement 줄지만, error way capacity pressure 증가 → sweet spot 제시
- **Page lifetime 연장**: 한 page가 첫 CE부터 retirement까지의 cycle 수 분포
  - "기존 대비 X배 더 오래 page를 유지할 수 있다"

**왜 중요한가**: 이것이 논문의 핵심 motivation. 2MB huge page에서 CE 1개로 2MB를 잃는 문제를 해결한다는 것.

---

## Section 5: "Error rate가 높아져도 버틸 수 있는가?"

**스토리**: DRAM aging이 진행되면 BER이 증가한다. Error rate가 높아질수록 ETT entry 부족, error way 포화, retirement 빈번이 발생할 수 있다. 우리 설계가 다양한 error rate에서 graceful하게 동작하는지 보여준다.

**보여줄 데이터:**
- **BER sweep** (1e-6 ~ 1e-9):
  - IPC, retirement 횟수, error way 점유율, ETT eviction 횟수
  - 4개 metric을 한 그래프에 (normalized)
- **ETT entry 수 sensitivity**: BER이 높을 때 ett_entries=32/64/128의 영향
  - ETT가 부족하면 eviction 빈번 → pin 효율 저하 → IPC 하락
- **Graceful degradation**: BER이 매우 높아도 (1e-6) baseline 대비 IPC가 크게 나빠지지 않음을 보여줌
  - 최악의 경우에도 "pinning OFF(즉시 retire)보다는 낫다"

**왜 중요한가**: Reviewer는 "extreme case에서 어떻게 되느냐"를 물어본다. Graceful degradation을 보여주면 설계의 robustness를 입증.

---

## Section 6: "Hardware overhead가 합리적인가?"

**스토리**: ETT 64 entries + ECT 1024 entries로 총 ~6-8KB SRAM. 기존 LLC controller 내부 테이블(SHiP 16KB, Mockingjay 32KB)과 비교해도 작다.

**보여줄 데이터:**
- **SRAM overhead 테이블**: ETT size vs bloom filter size별 overhead (이미 Architecture 섹션에 있음)
- **기존 논문 overhead 비교**:
  - BlockHammer(HPCA'21): CBF 1KB~8KB
  - Hydra(ISCA'22): 56.5KB
  - SHiP: 16KB, Mockingjay: 32KB
  - **Ours: 6.2KB (m=256) / 8.2KB (m=512)**
- **Bloom filter size vs accuracy trade-off**: m=128(~4KB total) ~ m=512(~8KB total)에서 FP rate과 IPC

**왜 중요한가**: HW 논문에서 area overhead 정당화는 필수. "이 정도 SRAM은 이미 관행적으로 허용되는 수준"이라는 선례 제시.

---

## 실험 매트릭스

| 실험 | 변수 | 고정 | Workload |
|---|---|---|---|
| IPC 비교 | pinning ON/OFF/no-error | default config | SPEC CPU + cloud |
| BER sweep | 1e-6/7/8/9 | pinning ON, default | SPEC CPU subset |
| Bloom filter size | m=128/256/512 | k=4, BER=1e-8 | SPEC CPU subset |
| ETT entries | 32/64/128 | m=256, BER=1e-8 | SPEC CPU subset |
| Threshold | 16/32/64 | m=256, BER=1e-8 | SPEC CPU subset |
| Max error ways | 1/2/4/8 | m=256, BER=1e-8 | Memory-intensive |

---

## 그래프 목록 (예상)

1. **Fig. IPC comparison** — Bar chart, workload별 3-way (no error / pinning / no pinning)
2. **Fig. BER vs IPC** — Line plot, BER 축에 4개 point, pinning ON/OFF 두 선
3. **Fig. Retirement count** — Bar chart, BER별 retirement 횟수 (pinning vs no pinning)
4. **Fig. Bloom filter FP rate** — Bar chart, m=128/256/512에서 이론 vs 실측 FP
5. **Fig. Error way occupancy** — Stacked bar, workload별 error way 점유율
6. **Fig. Sensitivity** — Small multiples, threshold/ETT entries/max ways별 IPC
7. **Fig. HW overhead comparison** — Table or bar, 기존 논문 대비 SRAM 비교
8. **Fig. Pin hit rate** — Bar chart, workload별 pin hit rate
