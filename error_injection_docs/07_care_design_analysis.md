# 07. CARE 설계 분석 — 트리거, Victim 정의, 지오메트리 일반화, 면적 (2026-07-16)

P3 재구현(논문식 index + chip counter)에 대한 엄밀성 보강 문서.

## 1. Proactive 트리거: OR 채택 (논문 AND과의 의도적 결별)

```
논문 (III.C):  트리거 = (counter 포화 == 15) AND (max − min ≥ 12)
우리 (기본값): 트리거 = (counter 포화 == 15) OR  (max − min ≥ 12)
```

**정량적 의미** (retirement당 기여 = min(err_count, 3) ≈ 3):
- bias 12 도달 = 같은 chip의 retirement **4회** (다른 counter가 0일 때)
- 포화 15 도달 = 같은 chip의 retirement **5회**
- AND = 사실상 5회 + 편중 유지, OR = 4회 편중 또는 5회 누적이면 발화

**근거**: (a) full-scale uniform probe에서 AND 발화 0/29 — 논문 스스로도 1년치
fault 누적(R1Y)이라는 극한에서만 발화. 시뮬레이션 시간창에서 per-set retirement
밀도는 구조적으로 낮아 AND는 관측 불가능한 이벤트가 됨. (b) OR은 두 신호 각각의
의미(누적 임계/통계적 편중)를 보존하면서 필요 밀도를 1회분 낮춤.
`care_proactive_or: false`로 논문 조건 복원 가능 (ablation용).

## 2. Proactive Victim의 엄밀한 정의

### 논문이 region 전체를 내릴 수 있는 이유
논문 구성(DDR3, 4KB page, coarse interleave)에서는 **4KB page ⊂ 1 row ⊂ 1 bank**.
따라서 set의 region(1 bank × row 1/16 구역)은 4KB page들의 **disjoint 합집합**이고
"region의 모든 page" = 8MB/4KB = 2048개가 잘 정의됨.

### 우리 구성에서 그 정의가 무너지는 이유
2MB page + block 단위 fine interleave에서는 한 page가 **전 bank에 걸쳐** 뿌려짐.
region ∩ page = 각 page의 얇은 슬라이스이고, "region에 포함된 page"를 문자
그대로 읽으면 (row-구역이 겹치는) 거의 모든 활성 page가 victim이 됨 — 무의미.

### 채택한 정의 (구현됨)
> **Victim = 그 set의 region에서 에러가 한 번이라도 관측된 모든 page** (ECC 등록
> 성공 여부와 무관: REGISTERED / ALREADY_TRACKED / DROPPED 전부 증거로 인정),
> 단 이미 retire된 page는 제외 (retire 시 목록에서 제거).

- 자료구조: set당 `observed_pages` (unordered_set<page_base>) — 에러 page 수에
  비례하는 메모리, retire 시 정리.
- 기존 "set 상주 entry의 page" 방식(way 수 2에 묶여 victim ≤ 2)의 결함 해소:
  DROP된 블록·이미 invalidate된 블록의 page도 region의 증거로 남음.
- 하드웨어 대응 논거: 실제 시스템에서 이 정보는 MC가 아니라 OS(mcelog의
  per-page 에러 기록)에 있고, retirement는 어차피 MSR→인터럽트→OS 경로로
  일어나므로 OS-side 목록 사용은 구현 비용 0. 시뮬레이터의 observed_pages는
  그 OS 기록의 대리.

### 정량 비교와 모드 전환 (2026-07-20 추가, 사용자 결정)

문자적 정의가 병리적이 되는 이유를 수치로: 우리 구성(32GB, 64 banks, row 8KB/bank)
에서 한 2MB page는 시스템 row ~4개에 걸치므로, region(1 bank × 4096 rows = **32MB**)
의 row를 포함하는 page = 4096/4 ≈ **1024개 × 2MB = 2GB** — faulty 구역의 64배를
격리하게 된다. 근본 원인은 containment 붕괴: 논문(coarse 매핑)은 page ⊂ region,
우리(block interleave)는 page ∩ region = page의 ~1/64 슬라이스.

그럼에도 proactive 발화 자체가 희귀 이벤트이므로(아래 §및 05 V8), **논문 문자
그대로의 의미론도 `care_proactive_victims: "region"` 모드로 구현**했다 (기본은
`"observed"`): 할당된 page(current_ppage) 중 row-range가 트리거 set의 row-group과
겹치는 것 전부를 retire. 두 모드는 `[CARE][PROACTIVE] mode=...` 로그로 구분되며,
observed vs region victim 수의 실측 대비가 ablation 데이터가 된다 (demo 실측:
동일 발화 지점에서 observed 389 vs region 667 pages).

명세 주의 두 가지: ① region victim은 **할당(사용 중) page에 한정**된다 — 미사용
주소공간은 후보가 아니며, "2GB" 추정치도 할당 page 기준. 관측(에러) page들은
region 집합의 부분집합으로 함께 retire된다 (이미 영구 retire된 page는 스킵).
② 실제 OS라면 region의 free frame도 비용 0으로 blacklist하겠지만, 시뮬레이터는
메모리 압박(frame 고갈)을 모델링하지 않아 free frame 제거는 관측 효과가 없으므로
생략 — 결과에 영향 없는 추상화.

## 2b. Global Counter = Device(lane) 단위 — 적대적 전문 재검증 (2026-07-19 확정)

"탑티어 논문이 bank라고 썼는데 그게 틀렸다는 전제가 이상하다"는 문제 제기(정당함)에
따라, **전문(12p)을 두 명의 독립 변론자에게 읽혀 각각 'rank-level bank 해석'과
'byte-lane/device 해석'의 최강 변론을 구성**하게 하는 적대적 검증을 수행했다.

### 최종 판정 — 논문은 틀리지 않았다. "bank"의 지시 대상이 다를 뿐이다

> **"one counter for a DRAM bank"(p.538)의 "DRAM bank" = chip 내부의 물리 bank
> array** (rank의 bank b는 물리적으로 8개 device 각각의 bank-b array의 합집합).
> set index가 (ch, rank, bank)를 고정하므로, counter i = "chip i가 가진 그 bank
> array" — 이 독해에서 논문의 모든 문장이 참이 되고, rank-level 논리 bank 독해만
> 구조적으로 붕괴한다. **bank-해석 변론자 스스로 이 결론에 도달**했다.

### Rank-level bank 독해가 붕괴하는 세 개의 독립 논증

1. **Index 논증** (치명): "the index bits ... composed of channel, rank, bank, and
   the highest bits of a row" (p.536) + 비트 예산 1+2+3+4=10 (p.537) — bank 비트
   3개가 전부 index에 소비되어 **한 set = 단일 bank**. rank-level 독해면 set당
   counter 8개 중 7개가 영구히 0 → "max−min ≥ 12" 검사와 "8개 uniform 확률변수"
   통계(p.539)가 무의미해짐. 보강 인용(p.536): "each error counter can now be
   associated with the **predetermined** channel, rank, bank, and row" — bank
   연관성은 counter 배열이 아니라 **index의 속성** (set의 단일 bank에 공통 귀속).
2. **하드웨어 폐쇄성 논증**: entry 저장 내용 = tag + BCH 61b + valid + state 2b +
   **local counter 8×2b가 전부** (p.536, Fig.2a) — per-entry bank 필드가 없어
   bank-indexed 누적은 저장된 상태로부터 **구현 자체가 불가능**. 반면 lane-indexed
   누적은 저장된 것만으로 완결: local i(8×1 byte column별 에러 수, p.536, Fig.1/2b의
   XOR→OR→adder tree 회로는 주소 입력이 없음) → "accumulated to the **corresponding**
   global error counters" (p.537) = 위치 보존 배선 local[i]→global[i].
3. **물리 논증**: DDR3 rank의 device들은 lockstep — 진짜 rank-level bank 고장은
   **8개 lane을 균등하게** 깨뜨려 counter 간 bias를 만들 수 없다. bias 검출기가
   rank-level bank를 측정한다는 해석은 물리적으로도 불가능. 반대로 chip i의 bank
   고장은 lane i만 편중 — p.539의 결론 문구 "biased toward a particular **chip or
   bank**"가 정확해지는 유일한 독해 (rank-level 독해에서 "chip"은 설명 불가).

### 부수 확인

- Table I "×8" 구성이 핵심: data device 8개 ↔ 8×1 byte column 8개 ↔ counter 8개가
  정확히 1:1 (x4였으면 16 lane이라 이 대응이 흐려짐). Table II의 fault model도
  "FIT for 1Gb DRAM **chips**" — Single Bank = chip 내부 bank 고장으로 정의됨.
- Table I "Banks per channel: 8"은 본문 "8 banks per rank"(p.537)와 모순 — DDR3
  규격상 표의 오기로 판단.
- 정직한 약점 (변론자 명시): 논문에 "byte lane"/"device index"라는 단어 자체는 없다.
  본 독해는 Fig.1/2(b)의 기하 + DDR3 물리 구조에서 도출된 것 (의도 신뢰도 ~90%,
  "기술된 하드웨어와 정합하는 유일한 독해"로서는 ~99%).

→ **구현 결론 불변**: chip(lane)별 counter가 논문에 충실한 구현이며, 이제 그 근거는
"논문의 오기 정정"이 아니라 "논문의 정확한 독해"다. 리뷰어 대응용으로 보존.

## 3. Set Index의 지오메트리 일반화 (DDR3 → DDR5)

### 일반 규칙 (구현: `set_care_dram_geometry`)
```
index = [ channel | rank | bankgroup | bank | row MSBs ]   (총 log2(care_ecc_sets) bit)
row_groups = care_ecc_sets / total_banks     ← bank 필드는 전부 포함이 필수
제약: care_ecc_sets % total_banks == 0, row_groups ≤ rows (위반 시 즉시 abort)
```

### 논문(DDR3) vs 우리(DDR5) 대응표

| | 논문 (DDR3-1600) | 우리 (DDR5-4800) |
|---|---|---|
| 구성 | 2ch × 4rank × 8bank = **64 banks** | 2ch × 1rank × 8bg × 4bank = **64 banks** |
| bank 필드 | 1+2+3 = 6 bit | 1+0+3+2 = 6 bit |
| row MSB | 4 bit | 4 bit |
| index | **10 bit = 1024 sets** | **10 bit = 1024 sets** (동일) |

DDR5의 bankgroup은 rank 비트가 차지하던 자리를 대체한 형태라 **비트 예산이
우연히 일치**함. 의미론: bank-level 회로(row decoder, sense amp)는 여전히
bank당 존재하므로 **fault 입도 = (bankgroup, bank) 쌍 = 채널당 32개**로 정의
(bankgroup은 배선 공유일 뿐 결함 도메인의 하한은 bank). BANK fault mode와
global counter 계정 모두 이 입도를 따름.

다른 지오메트리 예: 4채널이면 total_banks=128 → row_groups=8 (3 bit)로 자동
조정. total_banks > care_ecc_sets가 되면 abort — 이때는 sets를 늘리는 게 맞음.

## 4. DRAM 용량 스케일링

논문에는 region 크기 숫자가 **둘** 있다 — 이 구분이 중요하다 (2026-07-16 보강):

- **설계점 (III.B.3)**: 256GB 서버, MC당 128GB → 10-bit index 고정 → **set당 최대
  128MB**. 2-way 충분성의 근거인 contention 분석(binomial, Fig 4a)은 바로 이
  1Gb(=128MB)/set 조건에서 수행됨.
- **평가 구성 (IV)**: 8GB 시스템 → set당 8MB (proactive 배치 2048 pages는 이 구성의 값).

즉 논문의 의도 자체가 "**index 10-bit 고정, region은 용량 따라 8MB~128MB**"이며,
우리 32GB(1 MC) → **32MB/set는 그 설계 범위의 안쪽**이다. 논문의 contention 분석이
우리보다 4배 큰 region에서 성립했으므로 우리 쪽 set 충돌 여유는 더 크다.

| 영향 | 분석 |
|---|---|
| 트리거 통계 | **불변** — counter 값 분포(uniform 가정 하 차이의 95% 상한 12)에만 의존, region 크기와 무관 |
| Victim 배치 크기 | 논문의 문자적 정의는 설계점에서 한 방에 128MB/4KB = **32,768 pages**로 폭발. 우리의 증거 기반 정의는 region 크기가 아니라 **에러 밀도**에 비례 — 스케일에서 이 정의가 필수가 되는 이유 |
| Set 충돌(drop) 압력 | region당 에러 수 ∝ 용량. 논문 자체 분석이 128MB/set에서 2-way 충분(p_cont ~1e-10)을 보였으므로 32MB/set는 여유. 용량 증설은 MC 추가로 이뤄지고 ECC cache는 **MC당 1개** |
| 대안 | region 입도를 평가 구성(8MB)과 맞추려면 `care_ecc_sets = capacity / 8MB` (32GB → 4096 sets, config로 가능). 면적은 아래처럼 선형 증가 |

## 5. 면적(Area) 오버헤드 분석

### Entry당 비트 (우리 구성, 32GB PA = 35 bit)

```
valid 1 + state 2 + BCH 코드 61 + local counter 8×2=16 + tag (35−6)=29  ≈ 109 bit ≈ 13.6 B
```
(tag는 index가 주소 비트에서 안 나오므로 line 주소 전체 필요 — 논문도 동일 구조)

### 총량 (1024 set × 2 way 기준)

| 구성요소 | 크기 | 비고 |
|---|---|---|
| Entry array | 2048 × 13.6B ≈ **27.3 KB** | |
| Global counters | 1024 set × 8 × 4bit = **4 KB** | |
| 합계 | **~31 KB / MC** | 8MB LLC의 **0.4%**, 논문의 "trivial area cost" 주장과 일관 |

### 스케일링 규칙 — 사용자 질문에 대한 답

1. **Global counter 수는 bank 수와 무관** — counter는 bank가 아니라 **byte lane
   (= 64B / 디바이스 폭)** 대응이므로 bank가 8개든 32개든 **8개 고정** (x8 기준).
   bank 수 증가는 counter가 아니라 **index 비트(=set 수 하한)**로 흡수됨.
   디바이스 폭이 바꾸는 것: x4 DIMM → lane 16개 → counter 16개/set (8KB),
   x16 → 4개/set (2KB). 4-bit 폭과 임계값 12/15는 lane 수와 무관하게 유지 가능
   (단 uniform-차이 95% 상한은 lane 수에 따라 재유도 필요 — x4면 16개 균등
   변수 기준으로 bound 재계산이 엄밀).
2. **용량 증가는 tag 비트만 log로 증가** (64GB → tag 30 bit, +0.5KB 수준).
3. **Set 수를 키우면 면적 선형 증가**: 4096 sets(paper-동등 8MB region @32GB)
   → ~125 KB ≈ LLC의 1.5% — 여전히 작음. 논문 재현성과 면적의 트레이드오프는
   config(`care_ecc_sets`)로 실험 가능.
