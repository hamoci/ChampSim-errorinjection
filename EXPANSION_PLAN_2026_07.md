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

### B-0b. FreeFault 구현 설계
- faulty line을 **natural set에 상주 pin**: `handle_fill`의 error-way 분기와 별개로, `is_error_data` && scheme==freefault면 victim 선정에서 해당 라인 제외(lock) + 항상 LLC hit 유지
- set당 lock 상한(기본 1 way 상당) 초과 시 초과분은 unprotected (원문 lock-control 방식)
- retire 없음 — CE rate 상승 시 LLC 용량 잠식이 스토리

- [ ] **B-1. CARE 구현** (원문 §III 기준, `papers/19_CARE_*.pdf`)
  - ECC cache: 2-way × 1024 sets(10-bit index: channel/rank/bank/partial-row — ChampSim address_mapping에서 추출)
  - CE 발생(CYCLE 주입) 시 등록(S1). 추적 중 블록의 read에 **+30 cycle BCH 디코딩 latency** (2.5GHz 기준 수치 — 주파수 스케일 여부 결정 필요)
  - State machine 단순화: 우리 주입은 hard error만 존재 → S1 → (write) S2 → (read+err) S3 → (read) retire. soft-error elasticity 미발현은 CARE에 불리하지 않은 보수적 단순화로 논문에 명시
  - Reactive retirement: 기존 retirement 경로(page offline 비용) 재사용, 단 CARE는 4KB 설계 → 우리 2MB 환경 이식 시 증폭 효과가 비교 포인트
  - Proactive retirement: set당 8×4-bit per-bank global counter, max≈15 && (max−min)≥12 시 set 보호 영역 전체 retire
  - replacement: 원문 Pseudocode 1 (min error count 우선, S3 비대체)
- [ ] **B-2. FreeFault 구현** (원문 기준, `papers/freefault.pdf`)
  - faulty line을 **natural set에 line-lock** (reserved way 없음): 기존 `allocate_error_way`/`is_error_data` 변형
  - retire 없음 — lock 수 무제한 누적이 본질 (set당 lock 상한 도달 시 정책은 원문 lock-control 방식 참조)
  - "retired 위치는 항상 LLC hit" — 추가 latency/DRAM 트래픽 없음
  - CE rate 상승 시 LLC 용량 잠식 vs 우리 bounded quarantine way의 대비가 핵심 스토리
- [ ] **B-3. Page-granularity pinning ablation** (공짜 baseline)
  - faulty line이 속한 페이지의 **모든 상주 라인**을 error way에 pin — line granularity 가치를 직접 입증
- [ ] **B-4. 싱글코어 sweep 실행**: CE rate 1e5~1e8 errors/hour × 10 SPEC trace × {CARE, FreeFault, ablation} (기존 3개 scheme 결과 재사용) ≈ **~120 runs**
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
- 스니펫만 확인된 것 (인용 전 원문 확인 필요): Pegasus (HPCA'25, Alibaba — ICCD'21 Du의 후속, 같은 계열 리뷰어 가능성), Cisco PPR 백서("DIMM fault 70% 수리"), MEMSYS'19 predictive offlining

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
