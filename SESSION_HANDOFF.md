# 세션 핸드오프 (2026-07-08)

> 다른 머신에서 작업을 이어받기 위한 문서. 새 세션의 Claude는 이 파일과
> `EXPANSION_PLAN_2026_07.md`를 먼저 읽을 것.

## 프로젝트 한 줄 요약

ChampSim 포크로 **DRAM CE 발생 시 faulty cache line을 LLC quarantine way에
pinning하여 2MB hugepage offline을 지연**시키는 기법(LLC Pinning)을 평가하는
논문 작업. 논문 아웃라인은 `LLC_pinning_outline_short.pdf` (git 미포함, 아래 참조).

## 문서 지도

| 파일 | 내용 | 신뢰도 |
|------|------|--------|
| `EXPANSION_PLAN_2026_07.md` | **메인 작업 계획** — 3개 트랙(A 멀티코어 / B 비교기법 / C 신규 워크로드), 완료 체크, 구현 설계 | 최신 (이 세션에서 관리) |
| `sim_configs/multicore/README.md` | 멀티코어 Exp 1 상세 (mix 구성, 바이너리, 실행/파싱법) | 최신 |
| `CLAUDE.md` | 저장소 일반 안내 | **일부 outdated**: ETT/EPT 설명은 제거된 옛 구현. ETT는 commit c88df85에서 제거됨 — 현재는 정확한 주소 추적(`error_addresses` set) |
| `evaluation_plan.md` | ETT 시절 평가 계획 | outdated, 참고만 |

## 절대 규칙 (사용자 지시)

1. **git 커밋에 `Co-Authored-By: Claude ...` trailer 절대 금지.** public repo이고
   보안상 사용자(hamoci) 이름만 남겨야 함. 과거 trailer는 filter-branch로 전부
   제거하고 force-push까지 완료된 상태 — 다시 넣으면 안 됨.
2. **논문 아웃라인 PDF/DOCX, papers/ 디렉토리(유료 논문 PDF 포함)를 public
   repo에 커밋하지 말 것.** 저작권 + 미발표 연구물.
3. 실험 config는 커밋, 결과물(png/csv/xlsx/txt 로그)은 커밋하지 않는 컨벤션.

## 이 세션에서 완료된 것 (모두 push됨)

- `707259c` per-CPU 에러 귀속 통계 (`PerCpuErrorStats`) — 싱글코어 bit-identical 검증 완료
- `a9a0947`~`734f6ec` 4-core config (8MB/16way LLC, 2MB page) + Exp 1 run 스크립트
  (`sim_configs/multicore/run_mixes.sh`: elapsed 로깅, RUN_TIMEOUT, skip-if-done)
- `81ebb1c` 멀티코어 파서 `stat_script_rev/parse_multicore_exp1.py`
  (per-CPU IPC는 출력의 **마지막** "CPU n cumulative IPC" 블록 = ROI 사용)
- `e9b3c84` 멀티코어 README, `ca42b14` CARE/FreeFault 구현 설계 고정
- 비교 기법 확정: **CARE (HPCA'21) + FreeFault (HPCA'15)** — 원문 PDF 전문 검증
  완료 (근거는 EXPANSION_PLAN 참조). ArchShield/CiDRA/RelaxFault는 related work만
- 리서치: 2024-26 직접 경쟁 학술논문 없음. 포지셔닝 위협: NVIDIA row remapping,
  CXL 3.1 sPPR/hPPR, Pegasus(HPCA'25). 신규 must-cite: Linux HugeTLB HGM(머지 거부),
  CATalyst(HPCA'16), Victima(MICRO'23)

## 현재 진행 중 (원래 머신에서)

- **Exp 1 (멀티코어 error rate sweep)**: 10 mix × 7 binary = 70 runs,
  MAX_PARALLEL=38로 실행 중. 결과는 원래 머신의
  `results/multicore/1_error_rate_sweep/`에 쌓임 (git 밖).
  완료 후 `python3 stat_script_rev/parse_multicore_exp1.py`로 파싱.
- 1e-8(최고 스트레스)에서 conventional offline(off_*)은 완주 못 할 수 있음 —
  의도된 현상 (RUN_TIMEOUT으로 절단, "conventional 붕괴" 데이터로 사용)

## 새 머신에서 할 일 (우선순위순)

### 1. 트랙 B: CARE 구현 (메인 코딩 작업)
- **설계는 `EXPANSION_PLAN_2026_07.md`의 "B-0. CARE 구현 설계" 섹션에 고정되어
  있음** — 그대로 따를 것 (ECC cache 2-way×1024set, +30cyc BCH, S1→S2→S3→retire,
  hard-error-only 단순화)
- 구현 위치: `ErrorPageManager` + `DRAM_CHANNEL::service_packet`
  (src/dram_controller.cc ~line 391의 CYCLE 주입 분기) — **기존 pinning 코드 무변경**
- 검증 필수: (a) scheme 미사용 시 기존과 bit-identical (b) 에러 0이면 noerr와
  동일 (c) tiny run state 전이 로그 수동 확인. 검증 방법 예시: 같은 config로
  수정 전/후 바이너리 빌드(git stash 활용) 후 출력 diff
- 그다음 FreeFault (설계 B-0b), 그다음 page-granularity pinning ablation

### 2. 트랙 C: 신규 워크로드 트레이싱
- Pin 3.22 툴체인은 **커널 6.8에서 동작 검증 완료** (원래 머신). 새 머신에서도
  `tracer/pin/` 그대로 사용: tracer .so 빌드 후
  `pin -t obj-intel64/champsim_tracer.so -o out.trace -s <skip> -t <count> -- <prog>`
- llama.cpp: TinyLlama-1.1B Q4_K_M, single-thread(`-t 1`), decode steady-state
  구간에서 500M~1B 명령어. 이후 XSBench. (셋업 명령은 EXPANSION_PLAN C-1~C-4 참조)
- 생성 트레이스는 xz 압축 후 ChampSim에 그대로 입력 가능 (검증됨)

### 3. (실험 머신 여유 생기면) Exp 1 결과 파싱 + weighted speedup 분석

## git에 없는 자산 (필요 시 원래 머신에서 scp로 복사)

| 경로 | 내용 | 새 머신 필요성 |
|------|------|---------------|
| `papers/` | CARE/FreeFault/ArchShield/CiDRA 원문 PDF | **트랙 B에 필요** — CARE 구현 시 §III 참조. scp 권장 (public repo 커밋 금지) |
| `LLC_pinning_outline_short.pdf` | 논문 아웃라인 (14p) | 참조용 |
| `test_traces/` | SPEC/GAP 트레이스 (~57GB) | 실험 돌릴 때만. B 코딩 검증용은 SPEC 1-2개면 충분 |
| `results/` | 기존 싱글코어 + 진행 중 멀티코어 결과 | 파싱/그림 작업 시 |
| `stat_script_rev/baseline_workloads_rbmpki_ipc.csv` | RBMPKI 랭킹 (mix 구성 근거) | **git 미추적 주의** — mix 재검토 시 필요 |

scp 예시 (원래 머신 IP를 HOST로):
```bash
scp -r HOST:~/Study/ChampSim/papers ./papers
scp HOST:~/Study/ChampSim/LLC_pinning_outline_short.pdf .
scp HOST:~/Study/ChampSim/test_traces/605.mcf_s-994B.champsimtrace.xz ./test_traces/
```

## 새 머신 셋업 절차

```bash
git clone https://github.com/hamoci/ChampSim-errorinjection ChampSim && cd ChampSim
git submodule update --init
vcpkg/bootstrap-vcpkg.sh && vcpkg/vcpkg install
./config.sh <config.json> && make -j$(nproc)   # config마다 반복
```

## 코드베이스 핵심 사실 (새 세션 Claude용)

- 에러 주입은 **CYCLE 모드만** 실제 동작 (`DRAM_CHANNEL::service_packet`,
  src/dram_controller.cc:391 부근). WRITE 패킷에는 주입 안 함
- Pinning ON: `record_error()` → threshold(32) 도달 시 `retire_page()` + LLC 스윕.
  Pinning OFF(conventional): `record_baseline_error()` → `baseline_retirement_threshold`(2)
- `page_base`는 2MB 정렬 하드코딩 (error_page_manager.h `get_page_base_pa`,
  cache.cc 스윕) — 4KB page config에서 멀티코어 돌리면 안 됨 (2MB config만 사용)
- 멀티코어 config에서 `PTW.lower_level`은 **명시하지 말 것** (defaults가 코어별
  자기 L1D로 배선; "cpu0_L1D" 명시하면 전 코어 오배선)
- dynamic error latency의 caches 스캔에 TLB 포함 버그 존재 (dram_controller.cc
  ~798) — 수정 보류 중 (기존 결과 변동 이슈, EXPANSION_PLAN P0-4)
- deadlock 감지는 1e9 cycle로 상향, livelock은 경고만 출력하도록 무력화됨
