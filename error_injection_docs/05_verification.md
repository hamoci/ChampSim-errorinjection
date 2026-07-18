# 05. 검증 (Smoke Test)

전 워크로드 재실행 대신 빠른 smoke test로 5가지 속성을 검증한다.
트레이스: `605.mcf_s-994B`, CARE proactive config(`care_proscrub_1e-8.json`) 기반,
`error_cycle_interval`은 에러를 빨리 쌓기 위한 smoke 전용 값 (CARE 20000 / pin 100000).

## 검증 항목

| # | 속성 | 방법 | 통과 기준 |
|---|---|---|---|
| V1 | **레거시 보존** | 패치 전(HEAD) 바이너리 vs 패치 후 바이너리, 같은 uniform config 2종(care/pinning)으로 실행 후 diff | 시간 표기 줄 제외 완전 동일 (bit-identical) |
| V2 | **재현성** | clustered 같은 바이너리(같은 seed) 2회 실행 diff | 완전 동일 |
| V3 | **Seed 독립성 + 총량 보존** | seed 54321 vs 777 실행 비교 | 분포는 다르고, 총 에러 수는 Poisson 기대범위(≈cycles/interval ± 몇 %) |
| V4 | **공간 뭉침** | clustered vs uniform의 bank 분포/fault 통계 비교 | fault당 발현 수가 1/(1−reuse_prob) 이론값과 일치, bank 편중 형성 |
| V5 | **CARE 자극** | bank-storm 시나리오(bank 100%, reuse 0.95)에서 CARE proactive 카운터 | uniform에서 0이던 카운터/bias가 실제로 누적 |

## 실행 절차 (재현용)

```bash
# 1. smoke config 생성 (uniform 2종 + clustered 3종: pin/care/pin-seed777)
#    scratchpad/smoke_*.json — error_cycle_interval=20000, executable_name 구분

# 2. 패치 전 HEAD에서 uniform 2종 빌드 → 실행 → 출력 저장 (V1의 기준선)
./config.sh smoke_uniform_care.json && make -j36   # config 하나당 한 번씩!
./config.sh smoke_uniform_pin.json  && make -j36

# 3. 패치 적용 후 5종 전부 재빌드 → 6개 실행
#    (uniform care/pin, clustered pin ×2, clustered pin seed777, clustered care)
bin/smoke_* --warmup-instructions 2000000 --simulation-instructions 20000000 \
    test_traces/605.mcf_s-994B.champsimtrace.xz

# 4. 비교 (Simulation time 등 벽시계 줄만 제거하고 diff)
diff <(grep -v "Simulation time" base_uniform_care.txt) \
     <(grep -v "Simulation time" patched_uniform_care.txt)
```

## 결과 (2026-07-15, 605.mcf_s-994B)

### V1 — 레거시 보존: **통과 (bit-identical)**

| 경로 | 실행 | 결과 |
|---|---|---|
| CARE (proactive+scrub, 20M instr) | HEAD 바이너리 vs 패치 바이너리 | 벽시계 줄 제외 diff 완전 없음 |
| Pinning (dynamic latency, 10M instr) | HEAD 바이너리 vs 패치 바이너리 | 벽시계 줄 제외 diff 완전 없음 |

uniform 경로는 RNG 스트림까지 보존되므로 **기존 실험 결과는 재실행 없이 그대로 유효**하다.

### V2 — 재현성: **통과**

`smoke_clustered_pin`(seed 54321)을 두 번 실행 → 출력 완전 동일.

### V3 — Seed 독립성 + 총량 보존: **통과**

| | seed 54321 | seed 777 | uniform | Poisson 기대 |
|---|---|---|---|---|
| 총 에러 | 454 | 456 | 453 | ≈444 (sim 44.4M cycles / 100000) |
| faults (cell/row/bank) | 138 (79/9/50) | 142 (67/14/61) | — | |
| Top bank | 0/23 | 0/23, 상위권 구성 상이 | — | |

세 실행 모두 기대값의 ±3% (Poisson 노이즈 √444≈21 이내). seed에 따라 fault 구성과
bank 분포가 달라지되 총량은 유지된다. CARE 20M 실행도 동일 (3837/3839 vs 기대 3888/3911).

### V4 — 공간 뭉침: **통과**

| 지표 | uniform | clustered (54321) | 해석 |
|---|---|---|---|
| 에러 페이지 수 (단일/다중) | 238 (130/108) | 189 (88/101) | 같은 에러 수가 더 적은 page에 집중 |
| 에러/page 평균 | 1.90 | 2.40 | +26% 뭉침 |
| fault당 발현 (avg) | — | 3.3 | 이론값 1/(1−0.7)=3.33 일치 |
| Top-1 bank share | (~1.6% 균등 기대) | 5.3% | bank 편중 형성 |
| 기아 이탈 (any-widened) | — | 27/454 (5.9%) | staged widening으로 bank 내 유지 |

### V5 — CARE 자극: **부분 통과 (메커니즘 동작, 트리거는 스케일 한계)**

bank-storm 시나리오 (weights 0/0/1, reuse 0.95, interval 5000, 20M instr):

| 지표 | uniform (기존 full-scale probe) | clustered 기본 | bank-storm |
|---|---|---|---|
| Peak Counter | 발화 불가 (AND 0/29) | 3/15 | **6/15** |
| Peak Bias | — | 3/12 | **6/12** |
| S2→S3 hard 확인 | 희박 | 825 | 다수 |

proactive 글로벌 카운터가 **실제로 누적되기 시작**했다 (uniform에서는 수학적으로 불가).
트리거 자체(한 ECC set에 saturation 15 + bias 12)는 "reactive retirement ~15개가 같은
set에 몰려야" 하는 조건이라, 짧은 smoke(74 retirements / 1024 sets)에서는 도달 불가 —
이는 기존 plan 문서의 스케일 분석(paper 8MB region vs 우리 32MB LLC)과 일치하는
정직한 한계이며, 장시간/고밀도 시나리오 sweep은 연구 항목이다.

### V6 — Fault lifecycle (hard-fault 영속성, 2026-07-15 추가): **통과**

Page retire를 영구화하고(CELL/ROW fault는 죽고 BANK는 생존, 죽은 몫은 재샘플)
재검증한 결과 (`clu_care_v3`, CARE 20M):

| 지표 | lifecycle 이전 (v2) | lifecycle 이후 (v3) | 해석 |
|---|---|---|---|
| CARE reactive retirements | 55 | 53 | v2에는 같은 page 재-retire 중복 포함, v3는 전부 고유 page (Retired Pages permanent = 53과 일치) |
| Faults Killed | — | 186 (cell 162, row 24) | retire된 page 53개에 fault가 평균 3.5개 앵커 — 뭉침의 직접 증거 |
| Resampled Manifestations | — | 23 | 죽은 fault 몫이 재샘플되어 총량 보존 (arrivals 3796 ≈ v2 3839) |
| IPC | 0.2557 | 0.2587 | 중복 retire 페널티 제거로 소폭 상승 (방향 타당) |

레거시 보존 재확인: lifecycle 코드는 `retire_page()` 내부에서 CLUSTERED 게이트 뒤에
있어, uniform V1 diff가 여전히 **bit-identical** (patched_pin_v3 vs HEAD 기준선).
재현성 V2도 재확인 (같은 seed 2회 완전 동일). Pin smoke는 threshold 32 미도달로
retirement 0회 → lifecycle 통계 0, 출력 이전과 동일 (일관성 ✓).

### V7 — FIT 구성비 전환 (2026-07-16): **통과**

기본 가중치를 CARE Table II permanent FIT(18.6:8.2:10.0 = 50.5%/22.3%/27.2%)로
교체 후 재검증. 시간축은 기존 interval 스케일 유지 (FIT는 공간 구성비로만 차용).

| 검증 | 결과 |
|---|---|
| 재현성 (같은 seed 2회, interval 100000) | 완전 동일 |
| mode 구성비 (n=138 faults) | cell 57.2% / row 16.7% / bank 26.1% — 기대치 대비 표본 노이즈(±1.6σ) 이내 |
| 실험 스케일 sanity (interval 144000 = 1e-8, mcf 20M instr) | 390 에러 ≈ 기대 386 (55.65M cycles/144000), any-widened 기아 이탈 7.9%, pending peak 20 — 모두 정상 |

실험 스케일에서 fault 115개·발현 390회·fault당 3.4회 — 현실적 rate에서도
뭉침 구조(bank-widened가 bank 안에 유지)가 잘 형성됨.

### V8 — CARE 재구현 검증 (2026-07-16, P2/P3/P3b + OR 트리거 + victim 재정의)

**단위 테스트**: 16 케이스 / 166 assertion 전부 통과 (Catch2 standalone 빌드 —
`make test` 전체는 upstream 602 테스트가 fork의 VirtualMemory 변경과 안 맞아
깨져 있는 별개 이슈). 트리거 로직(같은 chip 4회=OR bias, 5회=포화, 분산 시 억제),
Pseudocode 1, victim 목록(DROP 포함·retire 시 제거) 포함.

**레거시 보존**: CARE 전면 재작업 후에도 uniform pin 경로 **bit-identical** 유지.

**시스템 레벨 — proactive 발화의 필요조건을 실패 사례로 규명한 사슬** (mcf, 20~42M instr):

| 실행 | Peak/Bias | 결과 | 규명된 조건 |
|---|---|---|---|
| clu_care_v5_or (일반 rate) | 3 / 3 | 미발화 | 정상 — retirement가 set들에 산개 (논문 R1W와 일관) |
| bankstorm_v3_or (fault 855개) | 3 / 3 | 미발화 | bank fault의 retirement가 **rowgroup 16개 set으로 분산** → 회계 집중 필요 |
| singlestorm (reuse 0.999) | 6 / 6 | 미발화 | 이벤트 15.6k면 fault ~16개 생성 → **단일 fault 지배** 필요 |
| demo1 (sets=64, 2-way) | 3 / 3 | 미발화 | bank 전체가 2-way set 하나 → **ECC 추적 용량** 병목 (등록 대부분 DROP) |
| demo2 (sets=64·ways=32) | 9 / 9 | 미발화 | 에러율(interval 5k)이 bank read 트래픽의 7배 → **86% any-widened 산란** |
| **demo3** (+ interval 40k, 기아확장 off) | **12 / 12** | **✔ 발화** | 기아 이탈 0, retirement 4건 전부 set 51·chip 2 → bias 12 → OR 트리거, `[CARE][PROACTIVE] set=51 biased_chip=2 bias=12 victims=389` |

**결론**: proactive 발화 = ① 단일 fault 지배(reuse↑) ∧ ② 회계 집중(retirement가
같은 set으로) ∧ ③ 전달 집중(에러율 ≤ 해당 bank 트래픽) ∧ ④ 추적 용량 여유 —
동시 충족 필요. demo3는 메커니즘 검증용 극한 구성이며, **현실적 rate에서
proactive가 희귀 이벤트라는 결론은 논문 자체 평가(R1W 0건, R1Y에서만 발화)와
일치**. paper index(64 banks×16 rowgroups), chip별 counter, P3b 상시 로그,
증거 기반 victim(관측 page 389개 일괄 retire) 전 구간 동작 확인.

### 운영 사고 기록 (2026-07-16)

07-15의 죽음의 나선 pin 실행(454k cycle 페널티 + interval 20000) 3개를 죽일 때
`pkill -f "A\|B"`를 사용 — pkill 패턴은 ERE라 `\|`가 리터럴로 해석되어 **아무것도
죽지 않았고**, 해당 프로세스들이 22시간 동안 CPU 3개를 점유한 채 3M instruction도
완주하지 못함 (에러 페널티 중 새 에러가 페널티보다 빨리 쌓이는 양성 피드백 →
IPC ~0.008 이하로 붕괴, 사실상 종료 불가). PID 지정 kill로 정리 완료.
교훈: pkill alternation은 따옴표 안 `|` (백슬래시 없이), 죽였으면 pgrep으로 확인.

1. **기아는 트래픽 대비 에러율의 함수** — bank-storm(interval 5000)은 이 워크로드의
   DRAM read(132k)에 비해 에러(17k)가 과다해 기아가 많았다. 현실적 interval
   (144000, read 대비 ~264배 여유)에서는 기아가 드물다. `Pending Peak`와
   `Any-Widened` 통계로 모니터링할 것.
2. **CELL fault와 LLC의 상호작용** — anchor line이 LLC(특히 pinning 보호)에 있는 동안
   같은 line의 DRAM 재읽기가 없어 CELL 재발현이 지연되는 것은 물리적으로도 옳은
   동작이다 (fault는 있지만 DRAM을 안 읽으면 CE도 없음). staged widening이 이를
   bank 단위 뭉침으로 흡수한다.
3. **IPC 영향** — clustered 0.2252 vs uniform 0.2268 (pinning, 10M): 뭉침이 retirement를
   앞당겨 미세하게 느려짐. 방향성 타당.
