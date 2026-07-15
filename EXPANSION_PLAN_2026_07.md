# 실험 확장 계획 (2026-07)

> 목표: LLC Pinning 논문(아웃라인 `LLC_pinning_outline_short.pdf`)의 평가를 3개 축으로 확장
> 1. SPEC/GAP 멀티코어 mix 실험
> 2. SPEC/GAP 외 신규 워크로드 추가
> 3. 동일 도메인 비교 기법 2개 추가 (CARE, FreeFault)
>
> 참고: 기존 `evaluation_plan.md`는 ETT bloom filter 시절(제거됨) 문서로 outdated.

---

## 확정된 결정 사항

| 항목 | 결정 | 근거 |
|------|------|------|
| 멀티코어 LLC | 4-core, **8MB/16way** (per-core 2MB 유지) | 싱글코어 결과와 비교 논리 유지, 실서버 유사 |
| 페이지 크기 | 2MB hugepage 유지 | 논문 scope. `page_base` 2MB 하드코딩 문제 회피 |
| 비교 기법 #1 | **CARE (HPCA'21)** — metadata 계열 | 원문 PDF 전문 검증 완료 (`papers/19_CARE_*.pdf`). 도메인 정합성 최고 (운영 CE + threshold retirement + 데이터센터) |
| 비교 기법 #2 | **FreeFault (HPCA'15)** — cache-reuse 계열 | 원문 PDF 전문 검증 완료 (`papers/freefault.pdf`). LLC pinning의 직계 조상, 리뷰어 필수 요구 예상 |
| 탈락 | ArchShield → related work 인용만 | CARE 원문 확보로 스왑. manufacture-time 결함 대상이라 셋팅 상이 |
| 탈락 | CiDRA, RelaxFault → related work 인용만 | CiDRA: per-access 페널티 0이라 비교 그래프 무의미. RelaxFault: IPC 관점에서 FreeFault 하위 변형 |
| 신규 워크로드 | llama.cpp → XSBench → (여유 시) YCSB+Redis 순 | Pin 툴체인 1회 셋업 후 한계비용 낮음. LLM/HPC/KV-store 도메인 스프레드 |

---

## Phase 0 — 멀티코어 대응 코드 (선행 작업)

- [x] **P0-1. per-CPU 에러 통계** (2026-07-07 완료: 4-core smoke + 싱글코어 회귀 bit-identical 검증)
  - `ErrorPageManager`에 코어별 카운터 추가: first/added/already-known/retired + 에러 흡수(consume) 횟수
  - 주입 지점 `DRAM_CHANNEL::service_packet`(src/dram_controller.cc:391)에서 `pkt->value().cpu`로 집계
  - 최종 stat 출력에 per-CPU 섹션 추가
  - 필요 이유: pending error를 "다음 read"가 소비하는 구조라 memory-heavy 코어가 에러 대부분을 흡수 → 코어별 통계 없이는 mix 해석 불가
- [ ] ~~P0-2. TLB shootdown 멀티코어 페널티 모델~~ — **미구현 확정 (2026-07-08, 옵션 A)**: remote 코어 shootdown은 "특정 프로세스의 매핑이 어느 코어 TLB에 상주하는지"를 제어/관측할 수 없어 엄밀한 실측이 불가하다고 판단. 트랙 A는 미모델 상태로 진행하며, 논문에는 "remote shootdown 비용 보수적 미포함 → 우리 이득의 하한(lower bound); 모델링 시 conventional의 offline 비용만 증가하므로 이득 확대 방향"으로 명시 (아웃라인 §8.B 서술과 일관)
  - 현재: page offline 비용(454,568 cycles)이 해당 DRAM 패킷 1개에만 부과 → 타 코어 무영향
  - 목표: offline(retirement) 발생 시 **모든 코어에 shootdown stall 부과** (아웃라인 §8.B의 future work가 바로 이것 — "shootdown 비용은 코어 수에 비례 증폭")
  - 구현 방향: retirement 이벤트 시 O3_CPU별 stall 주입 (fixed penalty per core). ChampSim에 IPI 모델이 없으므로 고정 페널티로 근사, 페널티 값은 4KB/2MB 각각 실측치 기반 스케일
  - 논문 기재: IPI 정밀 모델이 아닌 고정 stall 근사임을 명시
- [x] **P0-3. 4-core config 생성 + smoke test** (2026-07-07 완료: `sim_configs/multicore/` 5개 config, PTW 배선/ptws 순서 검증, 1e-7 pinning smoke 통과)
  - `num_cores: 4`, LLC 8MB(8192 sets)/16way, 2MB page, DRAM 등은 기존 설정 유지
  - 생성 후 `.csconfig/` 확인: ptw_ptrs 순서가 cpu0→cpu3인지 (4코어는 사전순=인덱스순이라 안전 — 검증 완료, 10코어+에서만 깨짐)
  - 동일 트레이스 4개로 짧은 run → per-CPU 주입/흡수 로그 확인
- [ ] **P0-4. (보류) TLB 스캔 필터**
  - `calculate_dynamic_error_latency`의 `caches` 루프(src/dram_controller.cc:798)가 TLB까지 스캔 — TLB 태그는 VA라 PTE PA와 우연 매치 시 latency 과소평가 (싱글코어에도 존재하는 버그)
  - **수정 시 기존 싱글코어 결과 숫자가 미세하게 바뀔 수 있음** → 기존 결과 재사용 계획과 함께 별도 결정

## 트랙 A — 멀티코어 mix 실험 (Phase 0 직후)

- [x] **A-1. mix 구성** (2026-07-08 완료): **SPEC only** (사용자 지시로 GAP 제외). 2MB RBMPKI 랭킹 기준 pool이 정확히 5:5로 갈림
  - memory pool: mcf(21.4) fotonik3d(21.0) gcc(17.8) bwaves(16.3) omnetpp(13.3) → M1~M4 (leave-one-out)
  - cpu pool: cactuBSSN(8.1) wrf(6.1) roms(5.0) pop2(4.5) xalancbmk(2.8) → C1~C4 (leave-one-out)
  - hybrid: H1(mcf fotonik3d xalancbmk pop2), H2(gcc omnetpp wrf roms)
- [ ] **A-2. 실행 매트릭스** — 싱글코어와 동일한 실험 번호 체계로 구성 (2026-07-08 결정, Tier 구분 폐기):
  - **Exp 1 (error rate sweep)**: 10 mix × 7 binary(noerr + off/pin × {1e-6,1e-7,1e-8}) = **70 runs** → `results/multicore/1_error_rate_sweep/`
    - `sim_configs/multicore/run_mixes.sh` — DONE/FAIL 라인에 elapsed 초 기록, RUN_TIMEOUT env(1e-8 무한 run 대비), skip-if-done
    - 1e-8(=1e8 errors/hour stress)에서 conventional off는 일부 mix가 사실상 안 끝날 수 있음(아웃라인 Fig10에서 panic 제외한 것과 동일 현상) — RUN_TIMEOUT으로 자르고 결과에는 미완료 표기
  - **Exp 2' (retirement threshold)** / **Exp 6' (max errway sweep)** / **Exp 7' (no-error way sweep)**: 대표 mix(M1/C1/H1)만, config/스크립트는 Exp1 결과 확인 후 작성 → `results/multicore/{2_retirement_threshold,6_llc_way_sweep,7_no_error_way_sweep}/`
  - **검증 완료 (2026-07-08)**: raw_data.xlsx 파이프라인은 baseline을 별도로 받지 않고 "Way sweep in No error" 시트의 2MB/w16을 사용 → exp7' w16이 baseline 겸용 (config 필드 단위 동일성 확인). 단 기존 0506 baseline 결과는 warmup0/전체트레이스 실행이라 50M/250M 결과와 혼용 금지. fig2(4KB vs 2MB)만 별도 baseline dir 필요
  - MAX_PARALLEL=38 (48코어 중 10 여유, 사용자 결정). Exp1 70 runs ≈ 2웨이브 ≈ 24-30h
- [ ] **A-3. stat 파이프라인 멀티코어 대응**
  - 멀티코어 출력 파싱 (코어별 IPC 섹션)
  - Weighted speedup, per-core IPC 저하율, per-core 에러 흡수, error way 점유/간섭
- [ ] **A-4. (선택) CARE/FreeFault 멀티코어 확장** — 싱글코어 트랙 B 결과 본 후 결정

## 트랙 B — 비교 기법 구현 (트랙 A 시뮬과 병행)

### B-0. CARE 구현 설계 (2026-07-08 고정, 원문 papers/19_CARE_*.pdf §III-IV 기준)
- **위치**: `ErrorPageManager`에 CARE 모드 추가 (`scheme: "care"` config 키) + `DRAM_CHANNEL::service_packet`의 기존 CYCLE 주입 분기에 3번째 경로. LLC pinning 코드는 건드리지 않음
- **ECC cache**: 2-way × 1024 set (10-bit index = channel/rank/bank/partial-row 비트 — ChampSim `address_mapping`의 슬라이서에서 추출). Entry: 유효비트 + 태그 + 8×2-bit local counter (BCH 코드 자체는 저장 불필요, 존재 여부만 모델링)
- **동작**: (1) 에러 주입 시 해당 64B 블록을 ECC cache에 등록(S1), replacement는 원문 Pseudocode 1 (S3 있으면 무대체 / min-error-count 우선 / S0-S1 우선 대체) (2) 추적 중 블록의 read → **+30 cycle BCH decode latency** (3) state machine: S1 --write--> S2 --read+err--> S3 --read--> retire (우리 주입은 전부 hard error → soft elasticity 미발현, CARE에 불리하지 않은 보수적 단순화로 논문 명시)
- **Retirement**: 기존 `retire_page()` 재사용하되 CARE는 4KB 단위 설계 → 2MB 환경 이식이 비교 포인트. Proactive retirement(set당 8×4-bit global counter, max≥15 && max-min≥12)는 2차 구현(옵션)
- **BCH 30 cycles**: 원문 2.5GHz 기준. 4GHz 스케일 시 48 cycles — **열린 결정 #1**, 기본은 30 cycle 유지(보수적)
- **검증**: (a) noerr 대비 bit-identical (scheme off일 때) (b) 에러 없는 조건에서 CARE == noerr (c) tiny run에서 state 전이 로그 수동 확인

### B-1c. Proactive retirement — 구현 완료, bank-fault 주입만 제외 (2026-07-13 결정 수정)
- 2026-07-10에는 "제외"였으나 2026-07-13 사용자 결정으로 **구조는 구현하되 에러 주입 모델은 불변**으로 수정: "구현했고 균일 주입에서 설계 의도대로 침묵함"이 "미구현"보다 강한 방어 위치
- 구현 (커밋 참조): set당 8×4-bit global counter, reactive retire 시 entry의 bank(op_idx fold mod 8) counter에 기여 누적(상한 3 = 원문 2-bit local counter 최대), 포화(15) && 편중(max−min≥12) 시 set 상주 페이지 일괄 retire, 포화-무편중 시 라운드 리셋. `care_proactive` config (기본 off). Peak Counter/Peak Bias 통계로 문턱 대비 여유를 실측 출력
- 검증 (mcf 30M @1e-8): ① proactive off pre/post bit-identical ② on에서 트리거 0 + off와 동작 동일(통계 블록 외 diff 0) ③ **Peak Counter 3/15, Peak Bias 3/12** — 문턱의 1/5, 1/4 수준으로 침묵 (chi-square 균일성 증거와 정합) ④ 단위테스트 14케이스/120 assertions (proactive 5케이스: 동일-bank 5회 retire로 포화+트리거, 기여 상한, 비활성 무영향, victim 목록)
- bank-fault 주입 확장은 계속 제외 (에러 주입 regime 일관성 훼손 사유, 2026-07-10 논리 유지)
- **전 워크로드 250M 스케일 proactive probe 완료 (2026-07-15, `results/normal_evaluation/8_care_proactive_or/`)**: scrub+proactive+OR트리거 @1e-8 × (SPEC 10 + GAP 19). 결과 — **원문 AND 조건 발동 0회/29** (Peak Counter 최대 12/15, mcf는 retire 888건에도 9/15), 완화된 OR 조건조차 2회/29 (pr-3, sssp-10 각 1회, 정확히 12/12 경계값, proactive page 각 1개 = 영향 무시 가능). Peak 값이 전부 3의 배수(3/6/9/12) = 동일 (set,bank) counter 피격 횟수 1~4회 — 8,192개 counter에 수백 건이 흩어지는 생일문제 구조상 5회(포화)는 미도달. **결론: 트리거 조건을 AND→OR로 완화해도 proactive는 실질 침묵 → 원문 AND 유지 확정, OR variant는 탐색 기록으로만 보존**
- 논문 서술: full CARE 구조 구현 + "균일 cell-fault 체제에서 proactive는 설계상·실측상 침묵(Peak Bias 3/12)" → reactive(+scrub) 결과가 곧 full CARE 결과
- demand-scrub 정당화 최종 프레임 (2026-07-13): ①메커니즘 불변(정정 write도 Fig5 write path의 정당한 write) ②원문 fleet의 patrol scrubbing이 모든 faulty line에 유계 시간 내 확정 write 보장 → S1 영구주차는 유한 시뮬 창 아티팩트 ③hard fault 결정성으로 scrub 타이밍은 retire "시점"만 좌우 → scrub-ON=창내 비용 상한/OFF=하한 (bracketing) ④양쪽 보고: CARE-DS(주)/CARE-AW(민감도) ⑤결론은 어느 모델에서도 성립
- **원문 직접 언급 부재 확인 (2026-07-14)**: "scrub이 S1→S2를 유발한다"는 문장은 원문에 **없음** — S1→S2는 "if there is a write access to this block"으로 출처 불문 서술뿐. 인용 가능한 scrub 문장은 2개: 각주1 p.533 "The servers use SEC-DED protection with patrol memory scrubbing"(fleet 환경), §IV-B2 p.541 "One can reduce such silent data corruption by using memory scrubbing in conjunction with CARE"(병용 권장). **서술 규칙**: demand-scrub은 "원문 명시"가 아니라 "해석"으로 쓸 것. 앵커: CARE-AW="원문 gem5 평가와 동일 조건"(write 게이팅을 의미 있게 서술한 것 자체가 원문 평가에 scrub 미모델 시사), CARE-DS="원문이 권장하는 scrub 병용 배치의 모델링"(§IV-B2 인용) + 시간압축 일관성 논거. "원문에 따라 scrub이 S1→S2"라는 표현 금지

### B-1b. CARE demand-scrub 모델 (2026-07-10 구현, 커밋 77f92ef)
- 문제: 현행 S1→S2가 애플리케이션 writeback에만 게이트되어 hard line의 86%가 S1에 영구 주차 (mcf 1e-8: 등록 2,259 중 write 확정 325) → retire 희소 → CARE IPC가 noerr 수준으로 과대평가 + coverage 과소평가
- 해법: `care_demand_scrub` config (기본 off). ON 시 등록 직후 `on_write` 1회 = MC demand scrub의 corrective write 모델링 (원문 fleet은 scrubbing 사용, p.533 각주1; Fig 5 write path가 scrub write에도 그대로 적용됨). 에러 주입 모델 자체는 무변경
- 검증: scrub off 수정 전후 bit-identical / mcf 30M@1e-8에서 S1→S2 48→779(=전체 등록), retire 2→38, cycle 증가 +16.4M ≈ 38×454,568 산술 일치 / pytest 228 OK
- 논문 서술: scrub-ON을 주 결과로(실제 서버 RAS 관행), OFF를 민감도로(원문 gem5 평가와 동일 조건). **proactive 평가의 전제조건** — global counter가 retirement당 증가하므로 scrub 없이는 bank-fault 주입만으로 counter 포화 불가

### B-0b. FreeFault 구현 설계
- faulty line을 **natural set에 상주 pin**: `handle_fill`의 error-way 분기와 별개로, `is_error_data` && scheme==freefault면 victim 선정에서 해당 라인 제외(lock) + 항상 LLC hit 유지
- set당 lock 상한(기본 1 way 상당) 초과 시 초과분은 unprotected (원문 lock-control 방식)
- retire 없음 — CE rate 상승 시 LLC 용량 잠식이 스토리

- [x] **B-1. CARE 구현** (2026-07-09 완료 — reactive-only 간략화 설계, 사용자 확정)
  - 신규: `inc/care_ecc_cache.h` + `src/care_ecc_cache.cc` (순수 로직 클래스) + `test/cpp/src/048-care-ecc-cache.cc` (9 케이스 65 assertion 통과)
  - 수정: `error_page_manager.{h,cc}` (care API/stats), `dram_controller.{h,cc}` (service_packet 훅 + request_type care 메모 — write-mode swap 재서비스 중복 방지), `cache.cc` (OFF 분기 stat 출력), `config/{defaults,instantiation_file}.py`
  - config 키: `care`(bool), `care_bch_decode_cycles`(30), `care_ecc_sets`(1024), `care_ecc_ways`(2). `care`+`cache_pinning` 동시 설정 시 fail-fast abort
  - 검증 완료: (a) pre/post 바이너리 stdout bit-identical (noerr/pin/off × mcf 10M, 벽시계 제외) (b) care ON+주입 OFF == noerr (c) mcf 10M 1.44M interval에서 전체 궤적 실증 (REG→S1S2→S2S3→retire 1건) (d) 스트레스 런(10k interval) 2,492 주소 궤적 위반 0건, set 만석 DROP 839건 관측 (coverage 붕괴 스토리 데이터 확보 가능) (e) make pytest 228 통과
  - 원문 대비 편차 대장은 구현 계획 문서와 `care_ecc_cache.h` 헤더 주석에 고정
  - **명명·방어 프레임 확정 (2026-07-10, 외부 비판 반영)**: 우리 구현 = **원문이 스스로 정의한 PR_3 구성(reactive-only CARE)** — 논문에서 "CARE"가 아니라 "CARE (reactive-only, = PR_3 in [CARE])"로 명명할 것. 방어 논리는 축별로 분리:
    - 신뢰도 축: **비교 주장 자체를 안 함** (FIT vs FIT 결정). PR_3가 full CARE 대비 신뢰도 1/5(원문 Fig 6)라는 공격은 우리가 신뢰도 수치를 제시하지 않으므로 과녁이 없음 — 단, 이를 본문에 선제 명시 (proactive의 신뢰도 기여 인정 + scope 제외 선언)
    - 성능·용량 축(우리가 주장하는 축): PR_3 선택은 CARE에 유리한 보수적 설정 (proactive는 트리거당 set 보호 영역 = DRAM용량/1024set 일괄 retire — 원문 8GB 시스템 기준 8MB=2048×4KB(p.541 명시), 우리 32GB/2MB페이지 환경 기준 32MB=16 hugepages → full CARE의 성능/용량은 우리 수치보다 나쁘거나 같음 = 하한 논증) [2026-07-14 정정: 이전 "2048페이지=4GB"는 원문 페이지 수에 우리 페이지 크기를 오곱한 것]
    - proactive 미구현의 실측 근거 (가정→측정으로 교체): 주입 에러 주소 1,886개(디버그 런 2종)의 물리 bank 분포(슬라이서 실측: ch=bit6, bg=bits7-9, bank=bits10-11, 총 64 bank)가 **chi-square 25.3 (df=63, 95% 임계 82.5) → 균일 분포와 통계적으로 구별 불가**. counter는 retire당 +1인데 run당 retire ≤62가 64 bank·다수 set-영역으로 분산 → bank당 기대 counter ≈1로 max≥15(포화)와 max−min≥12(편중) 둘 다 자릿수 단위로 미달. 트리거 이중 불발 확정
  - **멀티에이전트 코드리뷰 후 수정 (2026-07-09)**: (1) 주입 소비를 CARE에서 first-service로 제한 — swap_write_mode 재서비스가 pending error를 이중 소비하던 결함 수정. retire하는 read도 소비를 다음 read로 이연 (WRITE skip과 동일 규칙). **pinning/baseline의 재서비스 이중 소비는 기존 artifact로 무변경(bit-identical 제약) → CARE만 클린한 비대칭은 편차 대장에 기재** (2) CARE retire는 `retire_page(_, queue_llc_sweep=false)` — pinning-gated 소비자 탓에 무한 증가하던 큐 방지 (3) `care_ecc_sets` 2^n 검증: config 단(ValueError) + 런타임(fail-fast abort) 이중화 (4) codegen을 care=true일 때만 방출 — 기존 config의 `.csconfig` byte-identical (5) 2MB page mask 단일화(`CareEccCache::PAGE_BASE_MASK`), on_error 단일 조회(enum 반환), per-CPU 출력 일원화 (6) retired 라인 재주입 시 coverage 이중 계산은 baseline과 공유하는 기존 artifact로 문서화(코드 주석) (7) pick_victim의 도달 불가 tie-break는 원문 충실성 사유로 의도적 유지
- ~~B-1 상세 (구현 전 설계 메모)~~ (원문 §III 기준, `papers/19_CARE_*.pdf`)
  - ECC cache: 2-way × 1024 sets(10-bit index: channel/rank/bank/partial-row — ChampSim address_mapping에서 추출)
  - CE 발생(CYCLE 주입) 시 등록(S1). 추적 중 블록의 read에 **+30 cycle BCH 디코딩 latency** (2.5GHz 기준 수치 — 주파수 스케일 여부 결정 필요)
  - State machine 단순화: 우리 주입은 hard error만 존재 → S1 → (write) S2 → (read+err) S3 → (read) retire. soft-error elasticity 미발현은 CARE에 불리하지 않은 보수적 단순화로 논문에 명시
  - Reactive retirement: 기존 retirement 경로(page offline 비용) 재사용, 단 CARE는 4KB 설계 → 우리 2MB 환경 이식 시 증폭 효과가 비교 포인트
  - Proactive retirement: set당 8×4-bit per-bank global counter, max≈15 && (max−min)≥12 시 set 보호 영역 전체 retire
  - replacement: 원문 Pseudocode 1 (min error count 우선, S3 비대체)
- [ ] ~~**B-2. FreeFault 구현**~~ — **생략 확정 (2026-07-09 사용자 결정)**: 비교 축을 성능(IPC 하락)으로 좁힘. 보호율/신뢰도 축은 FIT vs FIT (FaultSim류) 없이는 공정 비교 불가하므로 논문에서 주장하지 않음. FreeFault는 related work 서술로 강등 (B-0b 설계 메모는 기록용 유지)
  - faulty line을 **natural set에 line-lock** (reserved way 없음): 기존 `allocate_error_way`/`is_error_data` 변형
  - retire 없음 — lock 수 무제한 누적이 본질 (set당 lock 상한 도달 시 정책은 원문 lock-control 방식 참조)
  - "retired 위치는 항상 LLC hit" — 추가 latency/DRAM 트래픽 없음
  - CE rate 상승 시 LLC 용량 잠식 vs 우리 bounded quarantine way의 대비가 핵심 스토리
- [ ] **B-3. Page-granularity pinning ablation** (공짜 baseline)
  - faulty line이 속한 페이지의 **모든 상주 라인**을 error way에 pin — line granularity 가치를 직접 입증
- [ ] **B-4. 싱글코어 sweep 실행** (2026-07-10 착수): CARE × 4 rates × 10 SPEC = **40 runs**
  - 실험 8번으로 편입: `sim_configs/normal_evaluation/8_care_comparison/` (generate_configs.py `gen_8_care_comparison`, `build_all.sh 8`, `run_8_care_comparison.sh`)
  - exe `care_{1e-5..1e-8}`, EPM_CARE = CYCLE + care:true + 30cyc/1024set/2way 명시 + offline 454568 (pin/off와 동일 비용 모델)
  - 기존 pin_on/pin_off(exp1) + noerr(exp7 w16) 결과 재사용 → 4-scheme 비교. ablation(B-3)은 별도 결정
  - 결과: `results/normal_evaluation/8_care_comparison/`
- [ ] **B-5. stat 스크립트에 scheme 축 추가** (5-scheme 비교 그래프)

## 트랙 C — 신규 워크로드 (조기 착수, 백그라운드)

- [ ] **C-1. Pin 툴체인 셋업**: `tracer/pin` ChampSim tracer 빌드, 임의 바이너리로 추출 검증
- [ ] **C-2. llama.cpp**: TinyLlama-1.1B Q4 양자화, single-thread(`-t 1`), THP 활성화, decode steady-state에서 500M~1B 명령어 추출
- [ ] **C-3. XSBench**: event-based 모드, 빌드/트레이싱 단순 — 툴체인 검증 겸용
- [ ] **C-4. 트레이스 특성 검증**: MPKI/footprint/RBMPKI 측정 → 기존 워크로드 표(Table 3)에 편입
- [ ] **C-5. 싱글코어 매트릭스 편입** + (선택) mix 투입
- [ ] **C-6. (여유 시) YCSB+Redis**: 클라이언트-서버 구조라 Pin attach 셋업 번거로움 — 최후순위

## 논문 반영 사항 (서베이 결과, 2026-07-07)

- 2024–26 직접 경쟁 학술논문 **없음** — 노벨티 안전
- Related Work 추가 예정:
  - NVIDIA GPU row remapping (공식 문서 확인) — "offlining 회피" 명분 선점 → row granularity/spare 고갈/리부트 의존으로 반박 + CPU-side 부재 강조
  - CXL 3.1 sPPR/hPPR/sparing 표준화 — "왜 PPR 안 쓰나" 선제 대응
  - Linux HugeTLB HGM 패치 시리즈(머지 거부, LWN 확인) — **OS-only 해법 실패의 강력한 모티베이션 근거**
  - CATalyst (HPCA'16, PDF 확인) — CAT pseudo-locking 실용성 선례
  - Victima (MICRO'23), Jung&Erez fault model (MICRO'23), ADDDC 벤더 문서(학술 성능 연구 부재 = 우리가 채우는 공백)
- **Pegasus (HPCA'25) 원문 검증 완료 (2026-07-09, `papers/Predicting_DRAM-Caused_Risky_VMs_*.pdf`)**: baseline 아님, related work 인용 확정
  - 정체: AIOps/ML 운영 기법 — XGBoost(304 features)로 DRAM-caused risky VM(DCRV)을 예측해 node 대신 VM만 migration. 300k+ 노드 배포, node-level 대비 비용 70.3%↓. 아키텍처 변경/데이터패스 개입 전무 → IPC 비교 불가능, "왜 비교 안 했나" 리스크 없음
  - CARE 선정 방어: 같은 Alibaba 계열의 최신 후속이 아키텍처가 아닌 fleet-level ML로 감 → metadata 계열 아키텍처 기법은 CARE(HPCA'21)가 여전히 최신·최근접
  - 우리 논문에 유용한 인용: (a) 프로덕션 클라우드 VM 메모리 할당 단위가 2MB/1GB hugepage, DIMM 연속 row 배치 (§V-A, §VI) — 2MB offline 문제의 실증 근거 (b) page offlining 불충분 — UE 주소 중 CE 이력 보유 ≤12%, peak 시간대 대량 offlining의 성능 영향 명시 (§III-A) (c) 에러 공간 클러스터링: >98% single-bank, 에러 노드의 63%가 단일 VM 집중 (d) CE 발생량이 위험 VM 지표 — DCRV의 CE 수가 타 VM 대비 한 자릿수 이상 큼 (Table VI)
  - 주의: (b)의 ≤12%는 CARE의 "UE 58%가 동일 블록 CE 선행" 관찰과 긴장 관계 (주소/페이지 granularity, 관측 윈도 상이) — 우리 모티베이션은 "CE→UE 예측 정확도"가 아니라 "성급한 2MB offline 회피 + bounded 보호"로 서술
- 스니펫만 확인된 것 (인용 전 원문 확인 필요): Cisco PPR 백서("DIMM fault 70% 수리"), MEMSYS'19 predictive offlining

## 열린 결정 (진행하며 확정)

1. CARE BCH 30-cycle을 4GHz로 스케일할지 그대로 쓸지 (원문 2.5GHz 기준)
2. P0-4 TLB 필터 수정 여부 (기존 싱글코어 결과 재실행 여부와 연동)
3. 멀티코어 shootdown 고정 페널티 값 (실측 454,568 cycles의 코어당 배분 방식)
4. 트랙 A에서 CE rate 2개를 어느 interval로 (기존 INTERVAL_MAP 기준 1e-6/1e-7 상당 제안)

## 진행 순서

```
Phase 0 (P0-1 ~ P0-3) ──→ 트랙 A 실행 ──→ (선택) A-4
                      └─→ 트랙 B 구현/실행 (병행)
트랙 C: C-1 툴체인만 먼저 착수, 이후 백그라운드
```
