# DRAM Fault-Injection Modeling — 사용설명서 (User Manual)

> **대상 독자: 이 프로젝트를 처음 보는 사람.** DRAM 에러가 뭔지부터 시작해서, 이
> 시뮬레이터가 에러를 어떻게 만들어내는지, 어떻게 쓰는지, 왜 이렇게 설계했는지,
> 무엇을 조심해야 하는지까지 순서대로 설명한다. 코드 수준의 세부는 03/07 문서를,
> 개념적 직관은 08 문서를 참고. **이 문서 하나만 읽어도 모델을 남에게 설명할 수 있는
> 것이 목표.**

---

## 0. 30초 요약

이 시뮬레이터(ChampSim fork)는 DRAM에 **정정 가능한 에러(CE)**를 인위적으로 주입해서,
에러 대응 기법(page offline, LLC pinning, CARE)의 성능을 비교한다. 에러 주입은
**"언제(시간축)"와 "어디에(공간축)"를 분리**해서 모델링한다:

- **시간축**: seed로 재현 가능한 **Poisson 과정**이 "결함(fault)이 태어나는 시각"을 정한다.
- **공간축**: 각 결함은 **지속성 있는 물리 결함 영역**(한 셀 / 한 row / 한 bank의 일부)이고,
  워크로드가 그 결함의 **고장난 line을 읽을 때마다 CE가 발생**한다(hard fault).

현재 권장 모델 이름은 **`sticky`**다. JSON 설정에서 `error_spatial_model: "sticky"`로 켠다.

---

## 1. 배경 개념 (모르는 사람을 위해)

| 용어 | 뜻 |
|---|---|
| **DRAM** | 메인 메모리. 2차원 셀 배열이 bank → row → column 으로 구성됨 |
| **cache line (블록)** | 메모리 접근 단위. 여기선 64바이트 |
| **CE (Correctable Error)** | ECC(SEC-DED 등)가 **정정할 수 있는** 비트 오류. 데이터는 살아있고, "여기 에러가 있었다"는 기록만 남음 |
| **UE (Uncorrectable Error)** | 정정 불가 오류. 시스템 크래시/장비 교체 대상. **이 모델은 UE는 다루지 않음** |
| **hard fault (경성 결함)** | 물리적으로 고장난 셀/회로. **접근할 때마다 계속 에러를 냄** (일회성 soft error와 다름). 필드 CE의 대부분이 이것 |
| **fault mode** | 결함이 걸친 영역 크기: 셀 하나(cell) / 한 wordline(row) / 한 bank 회로(bank) |
| **page retirement (페이지 은퇴/offline)** | 에러가 많은 물리 페이지를 건강한 프레임으로 **migration**하고 폐기. 비쌈(~454k cycle) |
| **LLC pinning** | 에러 line을 마지막 레벨 캐시(LLC)의 예약 way에 **고정**해 DRAM 재접근을 없앰 (이 fork의 연구 주제) |
| **CARE** | 비교 대상 기법(HPCA'21). ECC cache로 에러를 추적하다 조건 충족 시 페이지를 은퇴 |

**핵심 물리 사실 (Sridharan & Liberty, SC'12 필드 연구):**
1. 결함은 **지속된다** — 한번 생긴 고장 영역은 접근할 때마다 CE를 계속 만든다.
2. 결함은 **영역 크기가 계층적** — 셀 하나만 죽기도, row/bank 단위로 죽기도 한다.

이 모델은 이 두 사실을 재현하는 것이 목표다.

---

## 2. 큰 그림 — 두 개의 축, 두 개의 레이어

### 2.1 두 축: 시간 × 공간
에러 하나를 만들 때 "몇 개(언제)"와 "어디에"를 **분리**한다.
- **시간축**이 개수/발생시각을 정한다 (Poisson).
- **공간축**이 위치를 정한다 (결함 영역).

이 분리가 중요한 이유: 만약 위치를 정하는 방식이 개수까지 좌우하면, 워크로드마다
유효 에러율이 달라져 **공정한 비교가 무너진다**. 그래서 둘을 떼어 놓는다.

### 2.2 두 레이어: 주입 vs 대응
```
레이어 1 — 주입 (fault-injection model, 이 문서의 주제)
   "새 CE가 언제·어디서 발생하는가"만 결정.
        │  CE 발생 → 장부 기록
        ▼
레이어 2 — 대응 (각 scheme의 역학)
   "faulty로 알려진 블록이 그 뒤 어떻게 처리되는가"
   ├─ Baseline(offline): 페이지에 에러 N개 → 은퇴(migration)
   ├─ Pinning:           에러 line을 LLC에 고정 → DRAM 재접근 제거
   └─ CARE:              ECC cache로 추적 → 조건 충족 시 은퇴
```
주입 모델은 **"CE 로그의 작성자"**일 뿐, 에러 물리학 전체가 아니다. "faulty 블록을
어떻게 처리하나"는 레이어 2(각 scheme)의 몫이다.

---

## 3. 세 가지 공간 모델 (설정으로 선택)

코드에는 세 가지 공간 모델이 있고 `error_spatial_model`로 고른다. 시간축(Poisson)은
셋 다 동일하고, **위치를 정하는 방식만 다르다.**

| 모델 | 위치 결정 | 공간 뭉침 | 개수 | 용도 |
|---|---|---|---|---|
| **`uniform`** (레거시) | Poisson이 CE를 발행 → **다음 read 주소**에 부착 | 없음 (bank 전역 균등) | Poisson rate가 고정 | 기존 결과 재현/비교 baseline |
| **`clustered`** | Poisson이 CE를 발행 → **기존 fault 재발현(reuse)** 또는 새 fault | bank 수준(약함) | Poisson rate가 고정 | 중간 세대 |
| **`sticky`** ⭐ | **Poisson이 fault를 발행** → 고장 line을 **접근할 때마다** CE | **구조적**(cell/row/bank) | 접근 × 밀도로 **창발** | **현재 권장** |

**왜 sticky로 왔나 (한 줄씩):**
- `uniform`: CE가 "다음 read"에 붙어 bank들에 균등하게 흩어짐 → 하드 fault의 공간
  뭉침이 원천적으로 안 생김. CARE의 bank 편중 감지가 절대 발화 불가.
- `clustered`: 뭉침을 도입했으나, 총량 보존을 위한 "starvation widening"이 오히려
  line/row 뭉침을 희석 → 살아남는 건 bank 뭉침뿐.
- `sticky`: 결함을 **고정 물리 영역**으로 놓고 "접근 = CE"라는 하드 fault 의미를
  그대로 구현 → 뭉침이 **구조적으로** 보장됨(각 결함의 CE가 자기 bank/row에 갇힘).

이 문서의 나머지는 **`sticky` 모델**을 설명한다.

---

## 4. STICKY 모델 상세 (현재 구현)

### 4.1 결함(fault) 하나의 구성
```
struct FaultDomain {
    mode      : CELL | ROW | BANK   // 결함이 걸친 영역 크기
    chip      : 0~7                 // x8 DRAM의 어느 die(byte lane)가 불량인가
    anchored  : 위치가 확정됐는가
    bank_key, row, anchor_cl        // 앵커된 좌표 (아래 참조)
    salt      : BANK 밀도 해시용 난수
}
```
- **mode**: 결함의 영역. `CELL`=한 cache line, `ROW`=한 (bank,row)의 line들, `BANK`=한 bank.
- **chip(lane)**: 64B line은 8개 die가 8B씩 만든다. 결함은 그 중 **한 die에만** 있다.
  이 chip은 결함의 **속성**이라, 그 결함의 모든 CE는 — 주소가 여럿이라도 — **같은 lane**에서
  깨진다. (CARE가 감지하는 지문.)

### 4.2 런타임 흐름 (7단계)

**① 출생 (시간축 Poisson)** — 매 DRAM 사이클(warmup 이후)마다 Poisson 타이머가 돈다.
발생 시각이 되면 결함 1개가 태어난다: mode는 FIT 가중치 추첨, chip은 균등 추첨.
**주소는 아직 없다(미앵커).** 다음 발생 시각 = +Exp(평균 `error_cycle_interval`).
> 타이머는 결함만 낳는다. CE는 여기서 안 만든다.

**② 앵커 (첫 접근)** — 미앵커 결함은 대기하다가, **다음에 실제로 서비스된 DRAM read**의
(bank, row, line)을 물려받아 위치가 **영구 고정**된다. → 결함은 항상 **워크로드가 실제로
접근하는 데이터(working set)** 위에 앉는다. 접근 안 되는 유령 결함은 생기지 않는다.

**③ 고장 line 판정 (밀도)** — 결함 영역 안에서 특정 line이 "고장"인지 판정:
```
is_bad_line(fault, line):
    CELL/ROW  → 항상 고장 (밀도 = 1, 영역이 작음)
    BANK      → hash(line ^ salt) < fault_density_bank   (희소 부분집합)
```
- **CELL**: 그 1개 line이 고장.
- **ROW**: 그 row의 line들이 고장.
- **BANK**: bank 전역에 **밀도 d(예: 5%)로 흩어진 소수 line만** 고장. 나머지 bank는 멀쩡.
  (single-bank fault는 bank 전체가 죽는 게 아니라, 공유회로 부분결함으로 **넓게 흩어진
  소수 주소**에서 CE가 나는 것.)
- 판정은 **결정론적·sticky**: 같은 line은 항상 같은 판정 (저장 불필요).

**④ CE 발생 (접근구동)** — 매 DRAM read마다:
```
if (이 페이지 이미 은퇴)            → CE 없음
if (read 주소가 어느 결함의 영역 안 AND 그 line이 고장)
    → CE 발생 (결함의 chip 운반) → 레이어 2(scheme)로 전달
```
**고장 line은 접근할 때마다 매번 CE** = 하드 fault. 정상 line은 영원히 무에러.

**⑤ Retirement** — 같은 페이지에 CE가 threshold만큼 쌓이면 페이지 은퇴(migration).
**영구적**: 은퇴한 페이지는 다시는 에러를 받지 않는다(재등록 루프 없음).

**⑥ Lifecycle (결함의 생사)** — 페이지 은퇴 시:
- 그 페이지에 앵커된 **CELL/ROW 결함은 사망** (데이터가 건강한 프레임으로 이사갔으니
  옛 결함 위치는 더 이상 안 읽힘).
- **BANK 결함은 생존** (bank 공유 회로는 페이지 하나 옮긴다고 안 고쳐짐). → 그 bank의
  다른 페이지에서 계속 CE. 이게 "page offline으로는 bank fault를 못 잡는다"는 CARE의 전제.

**⑦ 재현성** — `error_seed` 하나로 시간축(`temporal_rng`)과 공간축(`spatial_rng`)이
결정된다. 같은 seed + 같은 워크로드 + 같은 바이너리 → **완전히 동일한 결과.**

### 4.3 한 줄 요약
> **타이머가 결함을 낳고 → read가 결함의 고장 line을 밟으면 CE → 페이지 차면 은퇴
> (+CELL/ROW 결함 사망, BANK 생존).**

### 4.4 예시 타임라인
```
cyc 4,000   [출생] F0 = BANK, chip 3, 미앵커
cyc 4,100   read bank7/lineX → F0 앵커(영역=bank7 전체). hash(X)<밀도? → 아니오 → 무에러
cyc 4,200   read bank7/lineC → hash(C)<밀도? → 예(고장) → CE! (chip 3)
cyc 4,500   read bank7/lineC 또 → 고장 → CE! (같은 자리 반복 = 하드 fault)
cyc 4,700   read bank7/lineD → 정상 → 무에러          ← bank7이라도 대부분 멀쩡
cyc 8,000   [출생] F1 = CELL, chip 1 → read lineY에 앵커 → Y 고장 → CE!
   ...       Y가 속한 페이지가 threshold 도달 → 은퇴 → F1(CELL) 사망
후반부       F0(BANK) 같은 결함은 안 죽고 자기 bank에 계속 CE 누적
```
검증(debug 로그)으로 확인된 것: **모든 결함의 CE가 예외 없이 자기 bank/row 안에 갇힘.**
예) 한 BANK 결함의 CE 16개가 전부 같은 bank, 전부 같은 chip.

---

## 5. 어떻게 사용하나

### 5.1 설정 (JSON)
```json
"error_page_manager": {
    "mode": "CYCLE",
    "error_spatial_model": "sticky",

    "error_cycle_interval": 144000,     // ★ 결함 "출생" 간격 (cycle). 작을수록 결함 많음
    "fault_density_bank": 0.05,         // BANK 결함의 고장 line 밀도 (0<d<=1). CELL/ROW은 1 고정

    "fault_weight_cell": 18.6,          // FIT 비율 (CARE Table II, Sridharan). 합으로 정규화
    "fault_weight_row":  8.2,
    "fault_weight_bank": 10.0,

    "error_seed": 54321,                // 재현용 seed (컴파일 타임에 박힘)

    "retirement_threshold": 32,         // pinning/CARE 경로 은퇴 임계
    "baseline_retirement_threshold": 2, // offline(pinning off) 경로 은퇴 임계
    "cache_pinning": false,             // true면 pinning scheme
    "care": false,                      // true면 CARE scheme (별도 키 care_* 참조)
    "debug": 0
}
```
> **주의: 모든 EPM 설정은 컴파일 타임에 박힌다.** seed/interval/density를 바꾸면
> `config.sh` 후 **재빌드**해야 한다. `error_spatial_model`을 생략하면 기본 `uniform`
> (기존과 100% 동일).

### 5.2 빌드 & 실행
```bash
./config.sh my_config.json        # 코드 생성 (.csconfig, _configuration.mk 갱신)
make -j<코어수>                    # 바이너리 빌드 (config의 executable_name으로)
bin/<executable_name> \
    --warmup-instructions 50000000 \
    --simulation-instructions 250000000 \
    trace1.xz [trace2.xz ...]      # num_cores 개수만큼 트레이스
```
- 서로 다른 `executable_name`은 **다른 바이너리**를 만든다 → 여러 실험을 병렬로 돌려도
  충돌 없음.
- 멀티코어: `num_cores`를 맞추고 트레이스를 그 수만큼 준다.

---

## 6. 출력 읽는 법

`sticky` 모델이 켜지면 실행 끝에 이 섹션이 나온다:
```
[ERROR] [Spatial Fault Model (sticky)]
[ERROR]   Seed / Birth Interval:   54321 / 144000 cyc
[ERROR]   BANK Line Density:       0.0500
[ERROR]   Faults Born:             744 (cell=398 row=170 bank=176)   ← Poisson 출생 총수
[ERROR]   Faults Killed by Retirement: 400 (cell=286 row=114)        ← CELL/ROW 사망(BANK 0)
[ERROR]   Retired Pages (permanent):   205
[ERROR]   Injected CEs (access-driven): 421 (cell=293 row=118 bank=10)
[ERROR]   CEs per Fault (avg/max):     0.6 / 1
[ERROR]   Banks Touched:               64
[ERROR]   Top-1 Bank Share:            3.3%       ← 균등 기대 1.56% 대비 = 뭉침 지표
[ERROR]   Errors per Line/Row/Bank (avg/max): ...  ← 공간 집중도
```
- **Faults Born** ≈ (경과 cycle ÷ interval) 이어야 정상 (Poisson).
- **Errors per Bank max ≫ avg** 또는 **Top-1 Bank Share ≫ 1.56%** = 공간 뭉침 성공.
- **Errors per Line = 1** 이 보통인 이유는 §8(캐싱) 참조 — 버그 아님.

CARE를 켜면 추가로 `[CARE] ... Triggers / Peak Bias / Pages Retired (reactive/proactive)`,
그리고 은퇴할 때마다 `[CARE][RETIRE] ...`, proactive 발화 시 `[CARE][PROACTIVE] ...` 로그.

---

## 7. 설계에서 고려한 것들 (왜 이렇게 만들었나)

1. **개수 통제 vs 공간 집중의 트레이드오프.** "고장 line 접근 = CE"를 그대로 두면 hot
   line 하나가 CE를 수백만 개 뿜어 에러율 축이 무의미해진다. `sticky`는 이걸 **결함
   밀도(d)와 결함 수(interval)**로 물리적으로 묶는다 — 전역 예산(옛 clustered)이 아니라
   **결함별 물리 밀도**로 통제해서, 개수를 묶으면서 **공간 뭉침을 보존**한다.
2. **접근 앵커링 (random 배치 안 함).** 워크로드 footprint ≪ 물리 메모리라, 결함을 무작위
   주소에 미리 놓으면 대부분 접근 안 돼 보이지 않는다. 그래서 **실제 read된 자리에 앵커** =
   "관측된 결함의 조건부 분포"를 모델링. 모든 결함이 관측 가능하다.
3. **FIT 비율만 차용.** FIT의 절대값(10⁹ device·hour당)은 수십 ms 창에선 0건이라, 시간축
   발생률은 기존 가속 주입 스케일(`error_cycle_interval`)을 쓰고, 필드에서는 **fault 종류의
   구성비(single-bit 18.6 : row 8.2 : bank 10.0)만** 가져온다. (가속 주입의 표준 논법.)
4. **chip을 결함 속성으로.** CARE는 "한 bank의 어느 lane이 편중되나"로 결함을 감지한다.
   chip을 주소에서 유도하면 주소마다 lane이 달라져 이 지문이 파괴된다. 그래서 chip은
   결함이 태어날 때 1회 고정되어 **그 결함의 모든 CE가 같은 lane**에 나타난다.
5. **BANK 밀도(d)로 "면 결함"을 물리적으로.** single-bank fault = bank 전체가 죽는 게
   아니라 **흩어진 소수 셀**. d로 그 희소성을 표현 → bank 통째 은퇴 같은 재앙 없음.
6. **hard-fault 영속성 = 영구 retirement.** 은퇴한 페이지는 다시 에러를 안 받게 영구
   기록 → uniform 모드의 "재등록→재은퇴 루프" 아티팩트 제거.
7. **재현성 우선.** 두 RNG 스트림을 seed에서 유도·분리해, 한쪽 소비량이 변해도 다른
   쪽이 흔들리지 않게 함.

---

## 8. 알려진 한계 / 반드시 알아야 할 gotcha

1. **"접근할 때마다 CE" = CPU 접근이 아니라 DRAM 접근.** CE는 DRAM read(캐시 miss/refill)
   에만 걸린다. hot line은 캐시에 상주해 DRAM 재읽기가 없으니 **같은 64B line의 반복 CE는
   거의 안 나타난다**(통계상 `Errors per Line = 1`). 뭉침은 **한 영역의 여러 line**(row/bank
   누적)으로 나타난다. → 논문 표현은 "**line의 DRAM 재fill당 1 CE**"가 정확. "every access"는
   과장.
2. **밀도가 높으면 CARE ECC(2-way)가 넘친다.** 에러를 한 set에 몰아넣을수록 2-way ECC
   cache가 오버플로 → 대량 DROP → tracked 안 됨. (밀도/interval 조절 또는 `care_ecc_ways`
   상향 필요.)
3. **CARE proactive 발화는 멀티코어 + 긴 sim이 필요.** 은퇴(→proactive counter)는 faulty
   블록의 **DRAM 재읽기**에 의존하는데, single-core는 메모리 압박이 낮아 재읽기가 드물어
   은퇴가 안 일어난다. **멀티코어(공유 LLC 압박)에서 reactive 은퇴가 나고 bias가 오른다**
   (실측: single-core bias 0 → 4-core 50M에서 bias 9/12). 발화(bias≥12)엔 더 긴 누적 필요.
4. **proactive 은퇴 비용은 과소계상됨.** region 모드 발화는 최대 수천 페이지(수 GB)를
   은퇴시키는데, 현재 시뮬은 그 batch를 **1페이지 latency로만** 과금한다(주석에만 명시,
   출력엔 없음). 성능 비교 시 반드시 감안/공개할 것.
5. **`[CARE][PROACTIVE]` 로그의 `victims=N`은 과대보고.** 실제 은퇴 수는 통계
   "Pages Retired (proactive)"를 인용할 것 (로그는 트리거/기은퇴 페이지 포함).
6. **스케일: consume이 O(reads × 결함수).** 결함이 누적되는 긴 run(300M+)에선 시뮬이
   시간 갈수록 느려질 수 있다. 본실험 전 bank→결함 인덱싱 최적화 권장.
7. **offline은 고에러율에서 IPC가 붕괴**한다(retirement penalty 폭주). 이건 버그가 아니라
   결과(offline이 나쁨) → "unusable"로 기록하지 숨기지 말 것.

---

## 9. scheme별 연동 (레이어 2)

주입된 CE는 각 scheme 경로로 그대로 흘러간다 — **주입 모델은 "어느 read가 CE를 받나"만
바꾸고 그 뒤 처리는 안 건드린다** (scheme 간 비교 공정성).

| scheme | 등록된 에러 line 재접근 시 | 은퇴 임계 |
|---|---|---|
| **Baseline (offline)** | 추가 비용 없음 (SEC-DED 인라인 ≈ 0). 페이지에 N개 쌓이면 은퇴 | `baseline_retirement_threshold` |
| **Pinning** | DRAM read 자체가 없음 (LLC 상주). 반복 CE 차단이 이득 | `retirement_threshold` |
| **CARE** | 매 read마다 BCH decode +30cyc, 상태 S1→S2→S3 진행 → 은퇴. 은퇴 누적이 bias→proactive | `retirement_threshold` |

---

## 10. FAQ (흔한 오해)

**Q. error address를 read하면 무조건 CE 아닌가?**
물리적으론 맞다. 하지만 CE는 **DRAM read에만** 걸리고 hot line은 캐시에 있어 DRAM
재읽기가 없다 → 반복 CE는 재fill 때만. (§8-1)

**Q. reuse(0.7/0.3)는 아직 있나?**
`sticky`에는 **없다.** 옛 `clustered`의 개념이다. sticky는 결함이 고정 영역이라 뭉침이
구조적으로 나오므로 reuse 추첨이 불필요.

**Q. BANK 결함이면 그 bank 접근이 전부 에러인가?**
아니다. 밀도 d(예: 5%)만큼의 **흩어진 소수 line만** 고장이고 나머지는 멀쩡. (§4.3, §8-1)

**Q. 결함이 접근 안 되는 random 주소에 생기나?**
아니다. **실제 read에 앵커**되어 항상 working set 안. (§4.2 ②, §7-2)

**Q. uniform/clustered 결과가 sticky 때문에 바뀌나?**
아니다. sticky는 순수 추가(additive)이고 uniform/clustered 코드는 **바이트 단위로
불변**(검증 완료).

---

## 11. 코드 지도 (어디를 보나)

| 파일 | 내용 |
|---|---|
| `inc/error_page_manager.h` | enum `ErrorSpatialModel::STICKY`, `FaultDomain`, 설정 setter, dispatch(`update_cycle_errors`/`consume_cycle_error`) |
| `src/error_page_manager.cc` | sticky 구현: `update_sticky_faults`(출생), `birth_fault`, `is_bad_line`(밀도), `consume_sticky_error`(앵커+CE), `on_page_retired_clustered`(lifecycle), `print_sticky_stats` |
| `src/dram_controller.cc` | `service_packet`에서 read마다 `consume_cycle_error` 호출 (주입 지점) |
| `src/care_ecc_cache.cc`, `inc/care_ecc_cache.h` | CARE ECC cache: 상태기계, replacement, global counter, proactive 트리거 |
| `config/instantiation_file.py` | JSON → C++ 코드 생성 (`error_spatial_model == 'sticky'` 분기) |

**더 읽을 문서:**
- `08_intuition_and_faq.md` — 개념 직관 (헷갈릴 때 여기부터)
- `03_code_walkthrough.md` — 코드 레벨 흐름 (clustered 기준, sticky는 본 문서)
- `07_care_design_analysis.md` — CARE 트리거·victim·지오메트리 상세
- `10_sticky_fault_redesign.md` — sticky 설계 결정 기록

---

*이 매뉴얼은 sticky 모델 구현(`e9c9ab0`)과 3-agent 검증(주입 엄밀성 / CARE ECC+은퇴 /
로그 정확성) 결과를 반영한다. §8의 한계는 모두 코드로 확인된 사실이며, 결과 해석·논문
서술 시 반드시 함께 명시할 것.*
