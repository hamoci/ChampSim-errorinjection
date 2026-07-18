# 06. CARE 구현 재검토 및 정렬 계획 (2026-07-16)

코드 수정 전 검토 문서. 대상: `inc/care_ecc_cache.h`, `src/care_ecc_cache.cc`,
clustered fault model(01~03 문서), CARE 논문 (HPCA'21) Section III–IV 원문 대조.

## A. 검토 결과 — 논문과 일치하는 부분

| 항목 | 상태 |
|---|---|
| Block state machine S0→S1(error)→S2(write)→S3(read)→retire(read) | ✓ 일치 (Fig. 3) |
| S2→read→S3 무조건 승격 | ✓ hard-fault-only 가정 하에서 정합 — hard fault는 모든 read가 재검출 (soft repair 경로는 미모델, 아래 D4) |
| Pseudocode 1 replacement (S3 있으면 교체 금지, min-err 비교, tie-break) | ✓ 구현. 단 등록 시 err_count=1 고정이라 사실상 "빈 way에만 삽입"으로 퇴화 — 논문의 contention 분석(2-way에서 충돌 확률 ~1e-10)상 현실적 에러율에서는 무해. smoke의 43% drop은 과속 주입 탓 |
| BCH decode 30 cycles, 1024 set × 2 way | ✓ (paper III.A, III.B.3) |
| Proactive trigger: counter 포화(15) AND max−min ≥ 12 (95% 신뢰), round reset | ✓ (paper III.C) |
| Retire 시 local→global 누적 타이밍 | ✓ (S3 read에서 account) |

## B. 검토 결과 — 논문과 어긋나는 부분 (핵심)

### D1. Set index가 물리적 region이 아님
- **논문**: index = `channel | rank | bank | row 상위 4bit` (III.B.3; 2ch·4rank·8bank → 10bit).
  한 set = **특정 bank의 특정 row-region 하나** (8GB 서버 기준 set당 연속 8MB).
  proactive trigger 시 "그 set이 보호하는 region의 모든 page"(= 4KB 기준 2048개)를 통째 retire.
- **우리**: `(line_addr >> 6) & (sets-1)` — 물리적 의미 없는 해시 버킷.
  proactive victim도 "set에 상주 중인 entry들의 page"로 축소되어 있음.
- **영향**: proactive의 "region 단위 선제 격리"라는 의미 자체가 소실. 뭉친 에러가
  같은 set에 모이지도 않음 (index가 지역성을 버리므로).

### D2. Global counter의 의미가 다름 (사용자 지적 사항 — 정확함)
- **논문**: set index에 bank가 이미 포함되므로 per-set counter 8개는 bank 구분용이
  아님. 64B 블록의 **byte column 8개(0B~7B) = x8 DIMM의 8개 chip(byte lane)** 에
  대응 (Fig. 1, 2(b)). local 2-bit counter i(column i 에러 수)가 retire 시 global
  counter i로 누적(III.B.2) → 편향 = "특정 **chip**의 (해당 bank/row-region) 회로
  고장" 감지. III.C의 "one counter for a DRAM bank" 문장은 chip 내부의 bank라는
  뜻으로 읽어야 하는 loose wording ("biased toward a particular chip or bank").
- **우리**: 에러를 소비한 접근의 DRAM bank id mod 8 → 완전히 다른 축.
- **영향**: 편향 통계가 논문의 물리적 서사(칩 하나가 죽어간다)와 무관한 값을 셈.

### D3. Local counter 단순화
- 논문: 블록당 8×2-bit (byte column별). 우리: 단일 err_count (read마다 ++, cap 255;
  global 기여는 3으로 cap). → chip 축이 없으니 D2와 함께 물리적 의미 소실.

### D4. Transient(soft) error 미모델 — 의도된 scope
- 논문 Table II의 Transient FIT 열(단일비트 14.2 등)과 S2→(clean read)→S0 경로,
  CARE의 "elasticity"(soft 블록 보호 해제)는 모델 밖. hard-only 단순화로 문서화 유지.

### D5. Proactive의 스케일 전제 (관찰 — 결함 아님)
- 논문 평가(IV): **R1W(1주치 fault 누적)에서는 retire 0건, 성능영향 <1%**.
  proactive는 **R1Y(1년치 누적, 저자들 스스로 "unrealistic, highly biased against
  CARE"라 명시)에서만, 5개 메모리 집약 워크로드에서 발화**.
- 결론: proactive 발화는 "1년치 fault가 쌓인 극한 시나리오"의 현상. 우리 smoke에서
  안 열린 것은 정상이며, 열리는 실험을 원하면 그에 상응하는 fault 누적 시나리오를
  명시적으로 구성해야 함 (아래 P7).

## C. Fault model 쪽 검토

| 항목 | 현재 | 판단 |
|---|---|---|
| mode 가중치 | 0.5 / 0.1 / 0.4 (임의) | **Table II Permanent FIT로 교체**: cell 18.6, row 8.2, bank 10.0 (합으로 정규화하므로 FIT 값을 config에 그대로) |
| 미모델 mode | word(0.3)→cell에 흡수해도 0.8% 차이, column(5.6)·multi-bank(1.4)·multi-rank(2.8) 제외 | 문서에 제외 근거 명시 |
| ROW mode 존치 | 구현됨 | **유지 권장** — 같은 page의 서로 다른 line 에러를 만드는 유일한 집중 생성기 (retirement threshold·PERT·protected lines 실험의 전제). CARE 전용 실험은 `fault_weight_row: 0` |
| chip 축 | 없음 | **추가 필요** (D2 수정의 전제): fault 생성 시 chip 0~7 균등 추첨. 물리적으로도 cell/row/bank fault는 모두 "한 chip 안"의 결함이므로 자연스러움 |

## D. 실행 계획 (승인 후 진행)

| # | 작업 | 규모 | 비고 |
|---|---|---|---|
| P1 | 기본 가중치를 FIT(18.6/8.2/10.0)로 교체 — **완료 (2026-07-16)**. FIT는 공간 구성비로만 차용, 시간축은 기존 1e-5~1e-8 interval 스케일 유지 (절대 FIT를 cycle 환산하면 sim 창에서 이벤트 0건이므로) | 설정+문서만 | 논문 인용 가능 |
| P2 | FaultDomain에 `chip`(0~7) 속성 추가, manifestation이 chip을 갖고 흐르게 배관 (EPM→care_on_injected_error→Entry) — **완료 (2026-07-16)** | ~40줄 | |
| P3 | ECC set index를 논문식(ch\|rank·bank fold\|row MSB)으로 교체 + global counter를 chip별로 + proactive victim을 "region 관측 error page"로 — **완료 (2026-07-16)**. 추가 결정: 트리거 기본값 OR(포화∨bias, `care_proactive_or: false`로 논문 AND 복원), victim = region 관측 페이지(등록/중복/DROP 증거, 07 문서 §2). 단위테스트 15케이스 재작성. V1 pin bit-identical 유지 확인 | ~120–150줄 | 기존 CARE uniform 결과(raw_data)는 재생성 필요 |
| P3b | Retirement 이벤트 상시 로그 — **완료 (2026-07-16, P3와 함께)**: `[CARE][RETIRE] page=.. trigger_cl=.. set=.. chip=.. err_count=.. cpu=..` / `[CARE][PROACTIVE] set=.. biased_chip=.. bias=.. bank_key=.. row_group=.. victims=N pages=[..]` — debug 게이트 없음, grep 가능한 고정 포맷 | ~30줄 | |
| P4 | 검증: ① uniform 비-CARE 경로 bit-identical 재확인 ② 단일 bank-fault(chip 고정) 시나리오에서 특정 set에 chip-lane 편향 누적→트리거 발화 확인 ③ FIT 가중치+현실 interval 스모크 | 스모크 3–4회 | |
| P5 | 문서 갱신: 02(FIT 표), 03(chip 축·index), 05(재검증) | | |
| P6 | 본실험 매트릭스 재정의: {noerr, offline, pinning, CARE, CARE-pro} × {uniform, clustered} × interval sweep × seed 3개 | 별도 협의 | |
| P7 | (선택) "사전 누적 fault map" 모드 — 논문 R1W/R1Y처럼 t=0에 FIT 비율로 fault N개를 미리 깔고 시작 | ~60줄, 후순위 | proactive 스트레스 실험용 |

### 주의사항 (승인 전 인지 필요)
1. **P3는 CARE 실행 결과를 바꿉니다** — 비-CARE 경로(uniform pinning/offline)는
   bit-identical 유지되지만, 기존 CARE uniform 결과(raw_data의 CARE 행들)는 재구현
   후 재생성이 필요해요. 어차피 clustered 전환으로 재실험 예정이면 부담은 겹침.
2. P3 이후에도 proactive가 "일반" 설정에서 발화하는 건 기대하면 안 됨 (D5) —
   발화 실험은 P7 또는 bank-storm류 시나리오로 별도 설계.
