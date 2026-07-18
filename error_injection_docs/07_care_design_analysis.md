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
