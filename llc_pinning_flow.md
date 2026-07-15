# LLC Pinning Architecture: 동작 흐름 상세 정리

**날짜: 2026.03.17**
**상태: 설계 확정 방향 — 미확정 사항은 [TBD]로 표기**

---

## 0. 설계 핵심 원칙

1. **CE 감지와 LLC Pinning을 분리한다** — CE 감지 시점에는 기록만, 실제 pinning은 이후 접근 시 수행
2. **평소에는 MC를 건드리지 않는다** — PDE counter와 ETT만으로 동작, ECT는 EDAC 경로를 통해 CE 발생 시 병렬 갱신
3. **MC → LLC controller 간 별도 pin 신호가 필요 없다** — CE 감지 시 MC는 기존 data 반환 경로에 CE_flag(1bit)를 태울 뿐, 별도의 pin 명령을 보내지 않는다. 실제 pinning 여부는 이후 접근 시 LLC controller가 ETT를 보고 자체적으로 결정한다
4. **기존 cache hierarchy의 동작 흐름을 최소한으로 수정한다**
5. **완벽한 시스템을 설계하지 않는다** — threshold 기반으로 합리적 시점에 retirement
6. **OS-transparent의 범위를 구분한다** — CE 감지 → 기록 → pinning → proactive protection의 핵심 경로는 완전히 hardware-only로 OS 개입이 없다. ECT 갱신은 기존 EDAC 프레임워크를 통해 CE 발생 시 병렬로 수행되며, physical page 재할당 시 ECT lookup은 page allocator에 경량 hook을 추가하여 처리한다. 이는 기존 커널 인프라(EDAC, buddy allocator)의 자연스러운 확장이다

---

## 1. Building Blocks

| 자원 | 위치 | 역할 | 접근 빈도 |
|---|---|---|---|
| PDE counter (6bit) | Page table → TLB에 캐싱 | Per-page CE count + threshold 판단 + ETT lookup trigger | 매 TLB lookup마다 (읽기), CE 감지 시 (쓰기) |
| ETT (Error Tracking Table) | LLC controller 내부 SRAM | Bloom filter 기반 error cache line 위치 판별 | PDE counter > 0인 page에서 error way hit이 아닌 LLC 접근 시 (일반 way hit 또는 LLC miss) |
| ECT (Error Counter Table) | MC 내부 SRAM | Physical page별 CE counter의 persistent 저장소 | CE 감지 시 EDAC 경로로 갱신, page 할당 시 lookup |
| LLC error way | LLC | Pin된 error cache line의 정상 data 저장 | Pin 이후 해당 주소 접근 시 (LLC hit) |

---

## 2. PDE Counter (6bit)

### 2.1 Bit Field 구조

```
PDE Ignored Bit (9bit 중 6bit 사용):
┌──────────────────────────────────────┐
│  counter (6bit)                      │
│  값이 0이면 정상 page                │
│  값이 > 0이면 error 존재 page        │
│  최대 63까지 count 가능              │
│  threshold(32) 도달 시 retirement     │
├──────────────────────────────────────┤
│  나머지 3bit: 미사용 (향후 확장용)    │
└──────────────────────────────────────┘
```

### 2.2 설계 결정 근거

- Counter > 0 자체가 "error 존재"를 의미하므로 별도 flag bit 불필요
- Threshold = 32이면 6bit(최대 63)로 충분히 커버
- 나머지 3bit는 미사용으로 비워두거나 향후 확장에 활용
- Threshold를 16에서 32로 확장: LLC error way 상한(8-way)과의 균형 및 page 열화 판단의 보수성 확보

### 2.3 PDE Counter의 역할

| 역할 | 설명 |
|---|---|
| 1차 필터 | Counter == 0이면 정상 page → ETT 접근 없음 (대다수) |
| Threshold 판단 | Counter ≥ 32이면 page retirement trigger |
| CE count 유지 | CE 감지 시 PTW를 통해 increment |

### 2.4 PDE Counter의 한계와 ECT의 역할

PDE counter는 virtual mapping에 속하므로, **PDE 해제 시 counter가 유실**된다.

```
Process A: physical page X 사용 → CE 12회 → PDE counter = 12
Process A 종료 → PDE 해제 → counter 유실
Physical page X가 Process B에 재할당 → 새 PDE counter = 0 (위험!)
```

이를 방지하기 위해 ECT(Error Counter Table)가 physical page별 CE counter를 persistent하게 유지한다:
- **CE 감지 시:** 기존 EDAC 프레임워크가 MCE/CMCI를 통해 CE 통보를 받을 때, MMIO/MSR로 MC 내부 ECT의 해당 physical page counter를 increment (hardware 핵심 경로와 병렬)
- **Physical page 재할당 시:** Page allocator의 hook이 MMIO/MSR로 ECT를 lookup하여 counter를 새 PDE에 복구

ECT는 EDAC이라는 기존 커널 인프라를 활용하므로, PDE 해제를 별도로 감지할 필요가 없다. EDAC이 CE 발생 시마다 ECT를 갱신하므로 ECT는 항상 최신 상태이다.

**ETT bloom filter도 PDE 해제 시 invalidation하지 않는다.** ETT는 physical page base PA를 tag로 사용하므로 virtual mapping과 독립적이며, PDE가 해제되더라도 bloom filter 정보가 보존된다. Physical page 재할당 시 ECT에서 PDE counter가 복구되면, 기존 ETT bloom filter를 즉시 활용하여 첫 접근부터 LLC pinning이 가능하다.

---

## 3. ETT (Error Tracking Table)

### 3.1 위치 및 역할

- **위치:** LLC controller 내부 SRAM
- **역할:** Bloom filter 기반으로 error cache line의 위치를 판별
- **접근 시점:** PDE counter > 0인 page에 대해, error way hit이 아닌 LLC 접근이 발생했을 때 (일반 way hit 또는 LLC miss). Error way hit 시에는 이미 pin된 상태이므로 ETT 조회 불필요.

### 3.2 ETT Entry 구조

```
ETT Entry (~66 bytes):
┌──────────────────────────────────────────────────────────┐
│  tag          : page base PA (~21bit)                    │
│                 2MB page 단위로 physical page 식별        │
├──────────────────────────────────────────────────────────┤
│  bloom filter : error cache line 위치 판별 (512bit = 64B) │
│                 2MB page 내 32,768개 cache line에 대해     │
│                 hash 기반 membership test                  │
│                 false positive ≈ 8% (n=16), false neg = 0 │
├──────────────────────────────────────────────────────────┤
│  metadata     : valid bit, LRU 등 (~수 bit)              │
└──────────────────────────────────────────────────────────┘
```

### 3.3 Bloom Filter 파라미터

| 항목 | 값 | 근거 |
|---|---|---|
| Bloom filter 크기 (m) | 256bit 또는 512bit (후보) | Threshold=32에서 FP ~2.4% (m=256) 또는 ~0.24% (m=512) |
| Hash 함수 수 (k) | 4 | BlockHammer(HPCA '21) 선례, hardware-friendly |
| 입력 (n) | Error cache line 수 (최대 32) | Threshold에 의해 제한 |
| Hash 함수 종류 | H3 hash (XOR 기반) | 아래 참조 |

**False Positive Rate 계산**

Bloom filter의 false positive rate는 다음 공식으로 계산된다:

```
FP rate ≈ (1 - e^(-kn/m))^k

m = bloom filter bit 수
k = hash 함수 수
n = 삽입된 원소 수 (= 해당 page 내 error cache line 수)
```

본 설계에서 k=4로 고정하고, threshold=32이므로 n의 최대값은 32이다. 이론적 최적 k는 (m/n)×ln2 = (512/32)×0.693 ≈ 11이나, k=4에서 이미 FP가 충분히 낮고 BlockHammer(HPCA '21)에서 동일한 k=4, H3-class 조합이 사용되었으므로 k=4를 채택한다.

**Bloom filter 크기별 FP rate 비교 (k=4):**

| m (bit) | m (byte) | n=1 | n=4 | n=8 | n=16 | n=32 | ETT entry 크기 | ETT 64 entries |
|---|---|---|---|---|---|---|---|---|
| 128 | 16B | <0.001% | 0.019% | 0.24% | 2.40% | 16.0% | ~20B | ~1.2KB |
| **256** | **32B** | **<0.001%** | **0.001%** | **0.019%** | **0.24%** | **2.40%** | **~36B** | **~2.2KB** |
| **512** | **64B** | **<0.001%** | **<0.001%** | **0.001%** | **0.019%** | **0.24%** | **~68B** | **~4.2KB** |
| 1024 | 128B | <0.001% | <0.001% | <0.001% | 0.001% | 0.019% | ~132B | ~8.2KB |

**m=256bit vs m=512bit 선택:**

| | FP (n=32) | ETT 64ent | 총 SRAM (ETT+ECT) | 평가 |
|---|---|---|---|---|
| m=256 | 2.40% | 2.2KB | 6.2KB | FP 우수, 균형 잡힌 선택 |
| m=512 | 0.24% | 4.2KB | 8.2KB | FP 매우 낮음, overhead 허용 가능 |

Sensitivity analysis에서 m=128/256/512을 sweep하여 최종 결정 예정.

**Hash 함수: H3 Hash**

- 구현: 사전에 고정된 random bit matrix와 입력(cache line index 15bit)의 XOR 연산
- k=4개의 독립 hash를 위해 4개의 서로 다른 random bit matrix를 사용
- 각 hash 출력: 8bit (m=256) 또는 9bit (m=512)
- 4개의 hash를 **병렬로 1~2 cycle에 계산** 가능 (XOR만 사용)
- Gate 수가 적고 latency가 낮아 LLC controller 내부에 적합
- BlockHammer(HPCA '21)에서 동일한 H3-class hash, k=4 조합이 사용된 선례

### 3.4 ETT 크기 및 Eviction

- **On-demand allocation:** Error가 발생한 page만 entry 할당
- **기본 entry 수:** 64 entries
- **Bloom filter 크기에 따른 ETT 총 크기:** m=256 시 ~2.2KB, m=512 시 ~4.2KB

**ETT Entry 수 Sensitivity (m=256bit 기준):**

| Entry 수 | SRAM overhead | 커버 가능 환경 | 부족 시 영향 |
|---|---|---|---|
| 32 | ~1.1KB | 정상~간헐적 CE | 빈번 CE 환경에서 eviction 자주 발생 |
| 64 (기본) | ~2.2KB | 대부분 환경 | CE storm에서만 부족 |
| 128 | ~4.5KB | 거의 모든 환경 | 극단적 상황에서만 부족 |

- 64 entry 선택 근거: 대부분의 서버 환경에서 동시에 CE가 활성인 page가 64개를 초과하기 어려움. Threshold=32이므로 CE가 32번 발생한 page는 retirement되어 entry 해제 → 자연스러운 순환.
- **ETT entry는 physical page 기반으로 관리된다.** PDE 해제(프로세스 종료 등)와 무관하게 ETT entry는 유지되며, 해당 physical page가 다른 프로세스에 재할당되더라도 bloom filter 정보가 보존된다. 이를 통해 재할당 직후 첫 접근부터 기존 bloom filter를 활용한 즉시 pinning이 가능하여, proactive protection의 연속성이 보장된다. ETT entry 해제는 오직 page retirement 시에만 수행된다.
- ETT 부족 시 **graceful degradation**: 시스템이 crash하지 않고, LRU로 eviction된 page의 bloom filter만 유실. 이미 pin된 cache line은 LLC에 유지되며, PDE counter와 ECT counter도 보존되어 retirement 판단은 정상 동작.
- Sensitivity analysis에서 entry 수 32/64/128, bloom filter 크기 m=128/256/512을 sweep 예정.

**Eviction Policy: LRU**

ETT가 가득 찬 상태에서 새 page에 CE가 발생하면:
- LRU 기반으로 가장 오래된 entry를 eviction
- Eviction 시 해당 page의 **이미 pin된 cache line은 LLC error way에 그대로 유지** (pin은 ETT와 독립)
- Bloom filter 정보만 유실 → 이후 pin 해제 시 proactive protection 불가
- **PDE counter와 ECT counter는 유실되지 않음** → retirement 판단은 정상 동작

---

## 4. ECT (Error Counter Table)

### 4.1 위치 및 역할

- **위치:** MC 내부 SRAM (DRAM CE로부터 안전한 저장소)
- **역할:** Physical page별 CE counter의 persistent 저장소. PDE counter가 virtual mapping에 속하여 PDE 해제 시 유실되는 문제를 해결
- **갱신 시점:** CE 감지 시 EDAC 프레임워크를 통해 병렬 갱신 (hardware 핵심 경로와 독립)
- **조회 시점:** Physical page 할당 시 page allocator hook에서 MMIO/MSR로 lookup

### 4.2 ECT Entry 구조

```
ECT Entry (~4 bytes):
┌──────────────────────────────────────┐
│  tag     : page base PA (~21bit)     │
│  counter : CE count (6~8bit)         │
│  metadata: valid bit 등 (~수 bit)    │
└──────────────────────────────────────┘
```

### 4.3 ECT 크기

- **기본 entry 수: 1024 entries → 총 ~4KB**
- 1024 entries × 2MB per page = 2GB 커버
- CE가 발생한 physical page가 1024개를 초과하는 것은 DIMM 교체 수준의 심각한 상황
- 따라서 **eviction이 사실상 발생하지 않음**
- 만약 발생 시: Lowest Counter First로 단순 처리 (counter가 가장 낮은 entry eviction)

### 4.4 ECT 동작: EDAC 기반 설계

기존 리눅스 커널의 EDAC(Error Detection And Correction) 서브시스템은 이미 MC와 소통하여 CE 이력을 관리한다. 본 설계는 이 기존 인프라를 활용하여 ECT를 관리한다.

**CE 감지 시 (EDAC 경로, hardware 핵심 경로와 병렬):**
```
1. MC의 ECC engine이 CE 감지 → MCE/CMCI를 통해 EDAC driver에 통보
   (기존 EDAC 동작과 동일)
2. EDAC driver가 MMIO/MSR write로 MC 내부 ECT의 해당 physical page counter를 increment
3. ECT에 해당 page의 entry가 없으면 새 entry 할당
```

이 경로는 hardware 핵심 경로(MC → LLC → Core/PTW)와 **완전히 병렬**로 수행된다. Hardware 경로가 PDE counter++와 ETT bloom filter 삽입을 처리하는 동안, software 경로(EDAC)가 ECT를 갱신한다. 두 경로는 서로 독립적이며 간섭하지 않는다.

**Physical page 할당 시 (page allocator hook):**
```
1. Buddy allocator가 physical page를 할당할 때
2. Page allocator hook이 MMIO/MSR read로 ECT에서 해당 physical page를 lookup
3. Entry가 있으면 (counter > 0):
   a. 새 PDE의 counter field를 ECT의 counter 값으로 초기화
   b. ETT에 해당 physical page의 bloom filter가 이미 존재하므로,
      새 프로세스의 첫 접근부터 즉시 LLC pinning이 가능
4. Entry가 없으면:
   a. 새 PDE counter = 0 (정상 page)
```

모든 page allocation에서 무조건 ECT lookup을 수행한다. ECT에 entry가 없는 경우(대다수) miss로 빠르게 반환되며, page allocation 자체가 이미 비싼 연산(lock 획득, free list 탐색, 2MB zeroing 등)이므로 MMIO read 한 번(수백 ns)의 추가 overhead는 무시 가능하다.

**Design rationale (ETT entry 유지):** ETT entry는 physical page 기반으로 관리되며, PDE 해제 시에도 invalidation하지 않는다. Physical page의 DRAM fault는 physical property이므로 virtual mapping의 생성/해제와 무관하게 동일한 위치에 존재한다. ETT bloom filter를 PDE 해제 시마다 초기화하면, 재할당된 프로세스가 해당 cache line에 접근할 때 bloom filter에 정보가 없어 pinning이 즉시 수행되지 않고, DRAM의 faulty cell에 다시 접근하게 되어 CE가 재감지되어야만 pinning이 복구된다. ETT entry를 유지하면 이 취약 구간(vulnerability window)을 제거하여 proactive protection의 연속성을 보장한다.

**Retirement 시:**
```
1. Page가 영구 retire되면 ECT에서 해당 entry 삭제
   (retire된 page는 재사용되지 않으므로 counter 불필요)
```

### 4.5 PDE 해제 감지가 불필요한 이유

기존 설계에서는 PDE 해제 시 ECT에 counter를 백업해야 했으므로 PDE 해제를 감지하는 것이 핵심 문제였다. 새 설계에서는 EDAC이 CE 발생 시마다 ECT를 갱신하므로, **ECT는 항상 최신 상태**이다. PDE가 해제되든 말든 ECT에는 영향이 없으며, PDE 해제를 감지할 필요 자체가 사라진다.

마찬가지로, **ETT entry도 PDE 해제 시 invalidation하지 않는다.** ETT는 physical page 기반(page base PA를 tag로 사용)으로 관리되므로, virtual mapping의 생성/해제와 독립적이다. PDE가 해제되더라도 해당 physical page의 DRAM fault는 그대로 존재하므로, bloom filter 정보를 유지하는 것이 올바르다. 이를 통해 physical page가 재할당될 때 기존 bloom filter를 즉시 활용하여 첫 접근부터 LLC pinning이 가능하다.

### 4.6 ECT를 MC 내부 SRAM에 유지하는 이유

ECT를 커널 메모리(DRAM)의 자료구조로 구현하면 SRAM overhead를 제거할 수 있으나, CE를 관리하는 자료구조 자체가 DRAM CE에 취약해지는 문제가 발생한다. MC 내부 SRAM은 DRAM과 독립적이므로 CE의 영향을 받지 않으며, error counter의 무결성이 보장된다.

### 4.7 OS 수정 범위

- **EDAC driver 확장:** CE 통보 시 MMIO/MSR로 ECT counter increment 로직 추가. 기존 EDAC이 이미 MC와 소통하는 경로를 재활용하므로 자연스러운 확장
- **Page allocator hook:** Buddy allocator의 page allocation 경로에 ECT lookup 1회 추가. Hook 한 줄 수준의 수정
- 총 커널 수정: 기존 인프라(EDAC, buddy allocator)에 각각 경량 hook 추가 2곳

---

## 5. Phase 1: CE 감지 및 기록 (Error Recording)

CE가 감지되면 **PDE counter 갱신과 ETT bloom filter 삽입만 수행. LLC pinning은 하지 않는다.**

### 통신 경로: MC → LLC controller → Core(PTW)

CE 감지 후 두 가지 기록 동작(ETT bloom filter 삽입, PDE counter++)은 **단일 data 반환 경로를 따라 순차적으로 trigger**된다. MC가 여러 component에 독립적으로 신호를 보내는 것이 아니라, 기존 data 반환 경로(MC → LLC controller → Core)에 CE metadata를 태워서 자연스럽게 전달한다.

```
MC ──(corrected data + CE_flag + error CL index)──→ LLC controller ──(data + CE notification)──→ Core(PTW)
         기존 data 반환 경로의 metadata 확장                 기존 data 반환 경로에 notification 추가
```

- **MC → LLC controller**: 기존 LLC miss 응답으로 data를 반환하는 경로에 CE_flag(1bit) + error cache line index를 sideband로 함께 전달. 새로운 interface가 아닌 기존 경로의 metadata 확장이므로 구현이 자연스러움.
- **LLC controller → Core**: LLC controller가 data를 요청 core에 전달하면서 CE notification을 함께 전달. CE가 발생하는 상황 자체가 "특정 core의 LLC miss → DRAM 접근"이므로 요청 core가 이미 특정되어 있음.
- **Core 내부**: CE notification을 받은 core의 PTW가 page table walk를 수행하여 PDE counter를 increment.

**Design rationale**: MC→PTW 간 직접 통신 경로는 기존 x86 아키텍처에 존재하지 않으므로, LLC controller를 경유하여 기존 data 반환 경로를 재활용하는 것이 가장 자연스럽다. PTW에 CE notification에 의한 page table walk trigger 조건이 추가되지만, 이는 core 내부의 수정이므로 uncore 간 새로운 interface 추가 없이 구현 가능하다.

### 동작 흐름

```
1. CPU memory request → L1 miss → L2 miss → LLC miss → DRAM 접근
2. MC의 ECC engine이 CE 감지
3. MC가 data를 correction하여 정상 data 확보
4. MC가 corrected data를 LLC controller에 반환할 때 CE_flag(1bit) + error cache line index를
   sideband로 함께 전달 (기존 data 반환 경로의 metadata 확장)
5. LLC controller의 동작:
   a. 정상 data를 일반 LLC way에 캐싱 (기존 동작과 동일)
   b. CE_flag를 확인하고 ETT bloom filter에 cache line index 삽입:
      - ETT에서 page base PA로 lookup
      - Entry 없음 → 새 entry 할당, bloom filter에 cache line index 삽입
      - Entry 있음 → bloom filter에 cache line index 삽입
   c. Data를 요청 core에 전달하면서 CE notification을 함께 전달
6. Core 내부의 동작:
   a. PTW가 CE notification을 받아 page table walk 수행 → PDE counter++
   b. PDE counter ≥ threshold(32) → Phase 3 (Page Retirement) trigger
   c. Local core의 TLB entry 갱신 (PDE counter 반영)
7. EDAC 병렬 경로 (hardware 핵심 경로와 독립):
   a. MC가 MCE/CMCI를 통해 EDAC driver에 CE 통보 (기존 EDAC 동작)
   b. EDAC driver가 MMIO/MSR write로 MC 내부 ECT counter increment
```

### 이 시점에서의 상태

```
- 정상 data가 일반 LLC way에 캐싱되어 있음 (pin 아님, eviction 가능)
- ETT의 bloom filter에 해당 cache line index가 기록됨
- PDE counter가 증가됨 (>0)
- LLC error way에는 아직 아무 변화 없음
- ECT의 해당 physical page counter가 증가됨 (EDAC 경로로 갱신)
```

---

## 6. Phase 2: Error Data 접근 및 LLC Pinning

이후 해당 page의 cache line에 접근할 때, **PDE counter와 ETT bloom filter를 기반으로 LLC controller가 자체적으로 pinning 여부를 결정한다.**

### Case 1: 정상 page 접근 (대다수)

```
1. CPU memory request
2. TLB lookup → PDE counter == 0
3. 일반적인 cache hierarchy 동작 (L1 → L2 → LLC → DRAM)
4. ETT 접근 없음, 추가 overhead 없음
```

→ **대다수의 메모리 접근에 대해 overhead가 전혀 없다.**

### Case 2: Error page, LLC error way에서 hit (이미 pin된 상태)

**Pin 이후의 일반적인 접근. 가장 빈번한 error page 접근 패턴.**

```
1. CPU memory request
2. TLB lookup → PDE counter > 0
3. L1 miss → L2 miss → LLC lookup
4. Error way에서 hit → 정상 data 반환
5. ETT 접근 불필요
```

→ **Pin된 이후에는 추가 overhead 없이 LLC hit으로 서빙.**
→ **DRAM의 faulty cell에 다시는 접근하지 않음 → proactive protection.**

### Case 3: Error page, 일반 LLC way에서 hit + bloom filter hit

**가장 일반적인 pinning 시나리오.** CE 감지 직후, 정상 data가 아직 일반 LLC way에 있을 때.

```
1. CPU memory request
2. TLB lookup → PDE counter > 0 (이 page에 error가 존재함을 인지)
3. L1 miss → L2 miss → LLC lookup
4. 일반 LLC way에서 hit (CE 감지 시 캐싱된 정상 data가 아직 있음)
5. LLC controller가 ETT bloom filter 조회
6. Bloom filter hit → 이 cache line은 error 위치로 판별
7. 일반 way에 있는 data를 error way로 이동 → pin 완료
8. 정상 data를 CPU에 반환
```

→ **DRAM에 다시 접근하지 않으므로 UE 발전 여부와 무관하게 안전.**
→ **MC → LLC controller 간 별도 신호 없이, LLC controller가 자체적으로 판단.**

### Case 4: Error page, 일반 LLC way에서 hit + bloom filter miss

해당 cache line은 error 위치가 아닌, 같은 page 내의 정상 cache line.

```
1. CPU memory request
2. TLB lookup → PDE counter > 0
3. L1 miss → L2 miss → LLC lookup
4. 일반 LLC way에서 hit
5. LLC controller가 ETT bloom filter 조회
6. Bloom filter miss → 정상 cache line으로 판별
7. 일반 way에 그대로 유지 (pin하지 않음)
8. 정상 data를 CPU에 반환
```

→ **정상 cache line에 대해서는 불필요한 pinning이 발생하지 않는다.**

### Case 5: Error page, LLC miss + bloom filter hit

LLC miss 상태에서 bloom filter가 hit한 경우. 실제 error이든 false positive이든 **LLC controller 입장에서는 구분하지 않으며, 동일하게 pin 처리한다.**

```
1. CPU memory request
2. TLB lookup → PDE counter > 0
3. L1 miss → L2 miss → LLC miss
4. LLC controller가 ETT bloom filter 조회
5. Bloom filter hit → pin 대상으로 판별
6. DRAM에서 data를 읽어옴 → error way에 pin
7. 정상 data를 CPU에 반환
```

→ **실제 error인 경우:** CE 상태면 ECC correction 후 pin → 안전. UE로 발전했다면 correction 불가 → system crash (Limitation).
→ **False positive인 경우:** 정상 data를 pin → LLC capacity 약간 낭비되지만 안전성 영향 없음.
→ **Bloom filter의 판별과 pinning 로직이 분리되어 있으므로, hit이면 무조건 pin. 별도 fallback 불필요.**
→ FP rate ~8%이고 error page의 LLC miss에 대해서만 적용되므로 전체 LLC capacity 영향 극히 미미.

### Case 6: Error page, LLC miss + bloom filter miss

같은 page 내의 정상 cache line이 LLC에 없는 경우.

```
1. CPU memory request
2. TLB lookup → PDE counter > 0
3. L1 miss → L2 miss → LLC miss
4. LLC controller가 ETT bloom filter 조회
5. Bloom filter miss → 정상 cache line으로 판별
6. DRAM에서 정상 data를 읽어옴 → 일반 LLC way에 캐싱
7. 정상 data를 CPU에 반환
```

→ **정상 동작. Error가 아닌 cache line이므로 DRAM 접근해도 안전.**

---

## 7. Phase 3: Page Retirement

PDE counter가 threshold(32)에 도달하면 page retirement을 수행한다.

### Trigger 조건

```
PDE counter ≥ 32 (PTW가 PDE counter++를 수행한 직후 비교)
```

### 동작 흐름

```
1. PTW가 PDE counter ≥ threshold 감지
2. 해당 physical page를 OS에 통보 (MCE 또는 별도 hardware interface)
3. OS가 bad page offlining 수행:
   a. 해당 page의 data를 새로운 clean page로 migration
   b. 원래 page를 bad page list에 등록하여 재사용 방지
4. 해당 page의 TLB entry invalidate (TLB shootdown)
5. ETT entry 해제 (bloom filter 초기화)
6. LLC error way에서 해당 page에 속하는 cache line을 tag sweep으로 찾아 invalidate
7. ECT에서 해당 page의 entry 삭제 (retire된 page는 재사용 불가이므로 counter 불필요)
8. PDE counter는 새 page에 대한 PDE이므로 자연스럽게 0
```

**순서의 근거 (4→5→6):** TLB shootdown을 가장 먼저 수행하면, shootdown 완료 후 모든 core가 해당 page의 TLB entry를 잃는다. 이후 해당 page에 접근하려면 TLB miss → page table walk가 발생하는데, 이 시점에서 OS가 이미 새로운 clean page로 migration을 완료하고 새 PDE(counter=0)를 설정했으므로, 새 PDE로 접근하게 되어 ETT 조회 자체가 trigger되지 않는다. 따라서 ETT entry 해제(step 5)와 LLC error way invalidate(step 6)를 안전하게 수행할 수 있다. 만약 LLC invalidate를 ETT 해제보다 먼저 수행하면, 그 사이에 다른 core가 stale TLB로 접근 시 bloom filter hit → pin 시도가 발생하는데 error way가 이미 정리된 상태여서 예기치 않은 동작이 발생할 수 있다.

### Threshold = 32의 의미

- LLC Pinning 환경에서 counter는 **unique CE만 반영**
- Pin된 cache line은 이후 DRAM 미접근 → 같은 fault의 반복 CE 차단 → counter가 증가하지 않음
- Threshold 32 = 한 2MB page 내에서 **32개의 서로 다른 cache line에 실제 physical fault 존재** (32,768 cache line 중 0.1%)
- LLC error way 상한(8-way)과의 균형: retirement 전까지 최대 32개 cache line이 pin되며, 이는 절대적으로 32 × 64B = 2KB에 불과하여 LLC capacity 영향 무시 가능
- 기존 mcelog 기준 (4K page당 10 CE in 24h, 반복 CE 포함)보다 **훨씬 정밀한 판단**

---

## 8. PDE Lifecycle과 ECT 연동

ECT 관리는 기존 리눅스 커널의 EDAC(Error Detection And Correction) 프레임워크와 page allocator를 활용한다. Hardware 핵심 경로(CE 감지 → ETT 삽입 → PDE counter++)와는 완전히 독립적인 software 경로로 동작한다.

### 8.1 통신 경로 개요

```
CE 감지 시 (두 경로가 병렬 수행):

  [Hardware 핵심 경로]
  MC ──(data + CE_flag)──→ LLC controller(ETT 삽입) ──→ Core/PTW(PDE counter++)

  [Software 부수 경로]
  MC ──(MCE/CMCI)──→ EDAC driver ──(MMIO/MSR write)──→ ECT counter++

Physical page 할당 시:
  Page allocator ──→ hook ──(MMIO/MSR read)──→ ECT lookup ──→ 새 PDE counter 초기화
  ETT bloom filter는 PDE 해제와 무관하게 유지 ──→ 재할당 즉시 pinning 가능
```

### 8.2 CE 감지 시: ECT 갱신

EDAC driver는 기존에도 MC로부터 MCE/CMCI를 통해 CE 통보를 받아 CE 이력을 관리한다. 본 설계에서는 이 기존 경로에 ECT 갱신 로직을 추가한다.

```
1. MC의 ECC engine이 CE 감지 → MCE/CMCI로 EDAC driver에 통보 (기존 동작)
2. EDAC driver가 error PA에서 page base PA를 추출
3. MMIO/MSR write로 MC 내부 ECT의 해당 entry counter를 increment
   - Entry가 없으면 새 entry 할당
   - Entry가 있으면 counter++
```

이 경로는 hardware 핵심 경로와 **완전히 비동기**이다. Hardware 경로가 수십 cycle 내에 PDE counter++와 ETT 삽입을 완료하는 반면, EDAC 경로는 software interrupt 처리이므로 수 us 단위이다. 하지만 ECT는 retirement 판단의 정확성을 위한 persistent storage일 뿐, pinning의 즉시성과는 무관하므로 latency 차이가 문제되지 않는다.

### 8.3 Physical Page 할당 시: ECT Lookup + ETT Bloom Filter 즉시 활용

```
1. Buddy allocator가 physical page를 할당
2. Page allocator hook이 MMIO/MSR read로 ECT lookup (무조건 수행)
3. Entry가 있으면 (counter > 0):
   a. 새 PDE의 counter field를 ECT의 counter 값으로 초기화
   b. ETT에 해당 physical page의 bloom filter가 이미 존재하므로,
      새 프로세스의 첫 접근부터 즉시 LLC pinning 가능 (vulnerability window 없음)
4. Entry가 없으면:
   a. 새 PDE counter = 0 (정상 page)
```

**무조건 lookup의 근거:** ECT에 entry가 없는 경우(대다수) miss로 빠르게 반환된다. Page allocation 자체가 이미 비싼 연산(lock 획득, free list 탐색, 2MB page zeroing 등)이므로 MMIO read 한 번(수백 ns)의 추가 overhead는 무시 가능하다.

**ETT bloom filter 즉시 활용의 핵심:** PDE counter가 ECT로부터 >0으로 복구되면, 새 프로세스의 첫 LLC 접근부터 ETT bloom filter 조회가 trigger된다. ETT entry가 physical page 기반으로 유지되고 있으므로, 이전 프로세스에서 축적된 bloom filter 정보가 그대로 살아있어 error cache line에 대한 pinning이 즉시 수행된다. 이는 PDE 해제-재할당 사이에 bloom filter를 초기화했을 때 발생하는 "CE 재감지까지의 vulnerability window"를 완전히 제거한다.

### 8.4 PDE 해제 감지가 불필요한 이유

기존 설계에서는 PDE 해제 시 ECT에 counter를 "백업"해야 했으므로 PDE 해제를 감지하는 것이 핵심 문제였다. 새 설계에서는 EDAC이 CE 발생 시마다 ECT를 갱신하므로, **ECT는 항상 최신 상태**이다. PDE가 해제되든 유지되든 ECT에는 영향이 없으며, PDE 해제를 감지할 필요 자체가 사라진다.

**ETT entry도 동일하게 PDE 해제와 무관하다.** ETT는 physical page base PA를 tag로 사용하므로, virtual mapping의 생성/해제와 독립적으로 존재한다. PDE가 해제되더라도 ETT entry를 invalidation하지 않으며, physical page 재할당 시 기존 bloom filter를 즉시 활용한다. ETT entry 해제는 오직 page retirement 시에만 수행된다.

### 8.5 OS 수정 범위

| 수정 위치 | 내용 | 수정 규모 |
|---|---|---|
| EDAC driver | CE 통보 시 MMIO/MSR로 ECT counter increment | 기존 EDAC CE 처리 경로에 로직 추가 |
| Page allocator | Page allocation 시 MMIO/MSR로 ECT lookup | Buddy allocator에 hook 1곳 추가 |

두 수정 모두 기존 커널 인프라(EDAC, buddy allocator)의 자연스러운 확장이며, 새로운 서브시스템이나 dedicated instruction을 도입하지 않는다.

---

## 9. 설계의 핵심 장점 요약

### 9.1 CE 감지와 Pinning의 분리

| 항목 | 즉시 Pin 방식 | 본 설계 (분리 방식) |
|---|---|---|
| CE 감지 시 동작 | MC → LLC controller에 pin 신호 | MC → LLC(ETT 삽입) → Core(PDE counter++) |
| MC-LLC 간 통신 | 별도 pin 신호 필요 | **기존 data 반환 경로에 CE_flag sideband만 추가** |
| Pin 시점 | CE 감지 즉시 | **이후 접근 시 LLC controller가 자체 판단** |
| 구현 복잡도 | MC-LLC 간 새로운 interface 필요 | **기존 경로의 metadata 확장 + Core 내부 PTW trigger 추가** |

### 9.2 Unique CE Counting

| 항목 | 기존 mcelog | 본 설계 |
|---|---|---|
| Counter 의미 | 반복 CE 포함 | **Unique error position만** |
| 1개 fault의 결과 | Scrubber 반복 감지 → counter 빠르게 증가 | Pin 후 DRAM 미접근 → **counter = 1에서 멈춤** |
| Threshold 도달 의미 | 실제 fault 수와 무관할 수 있음 | **실제 N개의 distinct fault 존재** |

**Limitation: CE 감지~Pin 완료 사이의 overcounting 가능성.** CE 감지 시 정상 data는 일반 LLC way에 캐싱되며(pin 아님), pin은 이후 재접근 시에 수행된다. 이 사이에 해당 cache line이 일반 LLC way에서 evict되면, 재접근 시 DRAM에서 같은 fault의 CE가 다시 감지되어 PDE counter가 중복 increment될 수 있다. 다만 실질적 영향은 미미하다: (1) CE 감지 직후의 cache line은 LRU 기준 가장 최근 상태이므로 즉시 evict될 확률이 낮고, (2) 두 번째 CE 감지 시 다시 캐싱 → 재접근 시 pin이 완료되므로 동일 fault당 overcounting은 최악의 경우에도 1~2회에 그치며, (3) threshold=32에 비해 소수의 overcounting은 retirement 판단에 실질적 영향을 주지 않는다(예: 실제 distinct fault 30개 + overcounting 2회로 threshold 도달 시, 이미 30개 fault가 존재하는 page이므로 retirement은 합리적).

### 9.3 정상 접근에 대한 Zero Overhead

```
전체 메모리 접근 중 CE가 발생한 page에 대한 접근은 극소수.
대다수의 접근: TLB lookup → PDE counter == 0 → 일반 동작 → overhead 없음
```

### 9.4 ECT 관리의 단순성 및 ETT의 PDE-independent Persistence

```
Hardware 핵심 경로: PDE counter + ETT만으로 동작 → ECT에 접근하지 않음
ECT 갱신: EDAC이 CE 통보 시 병렬로 수행 → 핵심 경로에 overhead 없음
ECT 조회: Page allocation 시에만 → page allocation 자체 대비 무시 가능
PDE 해제 감지: 불필요 → ECT가 항상 최신이므로
ETT entry: PDE 해제 시에도 유지 → physical page 재할당 시 즉시 pinning 가능
ETT entry 해제: 오직 page retirement 시에만 수행
```

**Proactive protection의 연속성:** Physical page가 프로세스 A에서 프로세스 B로 재할당될 때, ECT가 PDE counter를 복구하고 ETT bloom filter가 그대로 유지되므로, 프로세스 B의 첫 접근부터 error cache line이 즉시 pin된다. DRAM fault는 physical property이므로, virtual mapping이 바뀌더라도 동일한 위치에 존재한다. ETT bloom filter를 초기화하지 않음으로써, 재할당 후 CE가 다시 감지되기까지의 vulnerability window를 완전히 제거한다.

---

## 10. Overhead 요약

### 10.1 Hardware Overhead

| 구성 요소 | 크기 (m=256) | 크기 (m=512) | 위치 |
|---|---|---|---|
| ETT (64 entries) | ~2.2KB | ~4.2KB | LLC controller 내부 SRAM |
| ECT (1024 entries × ~4B) | ~4KB | ~4KB | MC 내부 SRAM |
| LLC error way | 기존 LLC way 재활용 | 기존 LLC way 재활용 | LLC (제어 로직만 추가) |
| PDE counter (6bit) | 기존 ignored bit 재활용 | 기존 ignored bit 재활용 | Page table (추가 면적 없음) |
| **총 SRAM overhead** | **~6.2KB** | **~8.2KB** | |

### 10.2 성능 Overhead

| 시나리오 | Overhead |
|---|---|
| 정상 page 접근 (대다수) | 없음 (PDE counter=0 → 추가 동작 없음) |
| Error page 접근, LLC error way hit | 없음 (기존 cache hit과 동일) |
| Error page 접근, 일반 way hit + bloom filter 조회 | ETT bloom filter hash (수 cycle) |
| Error page 접근, LLC miss + bloom filter 조회 | ETT lookup + DRAM 접근 |
| CE 감지 시 (HW 경로) | MC→LLC sideband로 ETT 삽입 + LLC→Core notification으로 PTW가 PDE 갱신 |
| CE 감지 시 (SW 경로) | EDAC이 MCE/CMCI 처리 시 ECT counter increment (HW 경로와 병렬, 핵심 경로에 영향 없음) |
| Physical page 할당 시 | ECT lookup MMIO read 1회 (page allocation 대비 무시 가능) |

### 10.3 관련 논문의 SRAM Overhead 비교

LLC controller 또는 MC 근처에 SRAM 테이블을 두는 것은 아키텍처 논문에서 일반적인 접근이다. 본 설계의 총 SRAM overhead(m=256 기준 ~6.2KB, m=512 기준 ~8.2KB)는 관련 연구 대비 매우 보수적인 수준이다.

**Rowhammer 방어 논문 (MC 근처 SRAM):**

| 논문 | 학회 | SRAM Overhead | 정당화 서술 |
|---|---|---|---|
| Hydra (Qureshi 등) | ISCA '22 | 56.5KB (28KB/rank) | "Hydra uses a total of 32K-entry GCT (32KB) and 8K-entry RCC (24KB), for a total overhead of approximately 56KB (28KB per rank)... the SRAM overhead of Hydra is significantly lower than prior techniques that would need 680KB to 3MB" |
| DREAM | ISCA '25 | 1KB/bank (32KB system) | "DREAM-C can tolerate a TRH=500 at a storage overhead of just 1 KB/bank, which is 8x lower than what Graphene needs (7.9 KB/bank)" |
| START | HPCA '24 | LLC의 ~9.4% | "START dynamically uses 1-way, 2-way, or 8-way of the cache set based on demand. START consumes, on average, 9.4% of the LLC capacity to store metadata" |
| Rowhammer Cache | HOST '24 | 128KB/LLC slice (LLC의 12.5%) | "two ways from each set of each LLC slice are reserved for usage by rowhammer cache... 128KB of LLC slice for GCT, RCC, and RCT-ACT which is 12.5% of the total LLC size" |

**LLC Replacement Policy 논문 (LLC controller 내부 SRAM):**

| 논문 | 학회 | SRAM Overhead | 정당화 서술 |
|---|---|---|---|
| SHiP | 인용 via ISCA '25 | 6KB | "a 16K entry table of 3-bit saturating counters... the table itself costs 6KB of SRAM" |
| Mockingjay | ISCA '25 인용 | 32KB | "Mockingjay requires 32KB of extra storage built over the baseline LRU policy" |

**본 설계와의 비교:**

| 항목 | 본 설계 (m=256) | 본 설계 (m=512) | Hydra | DREAM | START |
|---|---|---|---|---|---|
| 총 SRAM | **~6.2KB** | **~8.2KB** | 56.5KB | ~32KB | LLC의 9.4% |
| 비율 (vs Hydra) | **1/9** | **1/7** | 기준 | 57% | 8MB LLC 기준 ~750KB |

본 설계의 총 SRAM overhead(m=256 기준 6.2KB, m=512 기준 8.2KB)는 Rowhammer 방어 논문들이 수십~수백 KB를 가정하는 것 대비 한 자릿수 이상 작으며, LLC replacement policy가 LLC controller에 6~32KB의 SRAM 테이블을 두는 것과 비교해도 보수적인 수준이다.

### 10.4 기존 Bad Page Offlining과의 비교

| 항목 | Bad page offlining (기존) | LLC Pinning (본 설계) |
|---|---|---|
| CE 발생 시 비용 | 2MB page migration + TLB shootdown | PDE counter++ , ETT bloom filter 삽입 |
| Memory 가용성 손실 | 2MB per CE event | 0 (retirement 전까지) |
| Huge page 유지 | ✗ (page 분할 또는 폐기) | ✓ (retirement 전까지) |
| Hardware 추가 비용 | 없음 (SW 기반) | ETT ~2.2~4.2KB + ECT ~4KB |
| Retirement 판단 | 반복 CE 포함, 과도할 수 있음 | Unique CE 기반, 정밀 |
| UE 방지 | Page retirement으로 방지 | LLC pinning으로 proactive 방지 + threshold 시 retirement |

---

## 11. 해결된 사항

| # | 항목 | 결론 |
|---|---|---|
| 1 | PDE 재할당 시 ECT 복구 및 ETT 즉시 활용 | **Page allocator hook이 MMIO/MSR로 ECT lookup하여 counter 복구.** 모든 page allocation 시 무조건 lookup 수행. ECT miss(대다수)는 빠르게 반환되며, page allocation 대비 overhead 무시 가능. **ETT bloom filter는 PDE 해제 시에도 invalidation하지 않고 유지한다.** ETT는 physical page base PA 기반으로 관리되므로 virtual mapping과 독립적이며, 재할당 시 ECT에서 PDE counter가 >0으로 복구되면 기존 bloom filter를 즉시 활용하여 첫 접근부터 pinning이 가능하다. 이를 통해 PDE 해제-재할당 사이의 vulnerability window를 제거하고 proactive protection의 연속성을 보장한다. |
| 2 | Pin 해제 시 대응 방안 | **별도 대응 불필요.** 기존 Phase 2 흐름에 의해 재접근 시 자동으로 다시 pin됨. ETT까지 eviction됐으면 CE 재감지를 통해 다시 기록 + pin. |
| 3 | ETT bloom filter hash 함수 | **H3 hash (XOR 기반), k=4 사용.** BlockHammer(HPCA '21) 선례에 따라 k=4 채택. 사전 고정된 random bit matrix와 cache line index(15bit)를 XOR하여 4개의 독립 hash를 병렬로 1~2 cycle에 계산. Gate 수 적고 latency 낮음. |
| 4 | CE 감지 시 통신 경로 (MC → LLC controller → Core) | **단일 data 반환 경로를 따라 순차 전달.** MC가 LLC miss 응답으로 data를 반환할 때 CE_flag(1bit) + error cache line index를 sideband로 함께 전달. LLC controller가 (a) CE_flag를 보고 ETT bloom filter 삽입을 수행하고, (b) data를 요청 core에 전달하면서 CE notification을 함께 전달. Core 내부의 PTW가 CE notification을 받아 page table walk로 PDE counter++를 수행. 이와 병렬로 MC가 MCE/CMCI를 통해 EDAC에 CE를 통보하고, EDAC이 ECT counter를 갱신한다. |
| 5 | ETT eviction policy | **LRU 확정.** ETT는 cache와 달리 상위 hierarchy에 원본이 없으므로 eviction 시 bloom filter 정보가 유실됨. LRU가 적합한 이유: hot page는 LLC miss가 간헐적으로 발생하여 LRU가 갱신되므로 유지되고, cold page는 오래 접근되지 않아 eviction되더라도 재접근이 드물어 위험이 낮음. |
| 6 | ECT eviction policy | **Lowest Counter First 확정. 단, eviction은 사실상 발생하지 않음.** ECT를 1024 entries(~4KB)로 설정하여 2GB 분량의 error page를 커버. CE가 발생한 physical page가 1024개를 초과하는 것은 DIMM 교체 수준의 심각한 상황이므로, eviction 자체가 비현실적. 안전장치로 Lowest Counter First를 적용. |
| 7 | False positive fallback 동작 | **별도 fallback 불필요. Bloom filter hit이면 무조건 pin.** Error 판별과 pinning 로직이 분리되어 있으므로, bloom filter hit = pin 대상. 실제 error든 false positive든 LLC controller가 구분할 이유도 방법도 없음. FP 시 정상 data가 pin되어 LLC capacity가 약간 낭비되지만, k=4/m=256 기준 FP rate ~2.4%(n=32)이고 error page의 LLC miss에만 적용되므로 영향 극히 미미. |
| 8 | ETT entry 수 및 bloom filter 크기 sensitivity | **ETT 64 entries, bloom filter 크기는 m=256bit 또는 m=512bit로 후보 확정.** k=4 기준 FP rate: m=256에서 n=32일 때 ~2.4%, m=512에서 ~0.24%. ETT entry 수는 32/64/128으로 sweep 예정. 64 entry면 대부분 서버 환경 커버 가능, 부족 시 graceful degradation. |
| 9 | Lazy TLB Update 전략 (remote core) | **Eager TLB shootdown 불필요. 자연스러운 TLB entry 교체로 충분.** CE 감지 시 local core만 즉시 TLB 갱신하고, remote core는 stale TLB(PDE counter 미반영)를 유지. Remote core가 stale TLB로 해당 page에 접근해도: (a) 이미 pin된 cache line이면 error way hit으로 안전하게 서빙, (b) 아직 pin 안 된 cache line이면 PDE counter=0으로 보이므로 ETT 조회 없이 일반 동작 → DRAM 접근 시 CE가 다시 발생할 수 있으나, 이는 Section 9.2의 overcounting limitation과 동일 범주(동일 fault당 최악 1~2회). Remote core의 TLB는 자연스러운 TLB miss 시 새 PDE를 가져오면서 갱신됨. Retirement 시에는 TLB shootdown을 수행하며, 이는 기존 bad page offlining에서도 동일하므로 추가 비용이 아님. |
| 10 | Retirement 시 cleanup 순서 | **TLB shootdown → ETT entry 해제 → LLC error way invalidate → ECT entry 삭제 순서 확정.** TLB shootdown을 먼저 수행하면 모든 core가 stale TLB를 잃으므로, 이후 ETT 해제와 LLC invalidate 사이에 다른 core가 끼어들어 bloom filter hit → pin 시도를 하는 race condition이 발생하지 않음. ECT entry 삭제는 retire된 page가 재사용되지 않으므로 순서에 민감하지 않음. |
| 11 | ECT 갱신/조회의 trigger 주체 | **EDAC 프레임워크 기반으로 확정.** CE 감지 시: MC가 MCE/CMCI로 EDAC에 통보 → EDAC이 MMIO/MSR로 ECT counter increment (hardware 핵심 경로와 병렬). Page 할당 시: page allocator hook이 MMIO/MSR로 ECT lookup → counter 복구. PDE 해제 감지 불필요 (ECT가 항상 최신). 기존 커널 인프라(EDAC, buddy allocator)의 자연스러운 확장. Section 8 참조. |
