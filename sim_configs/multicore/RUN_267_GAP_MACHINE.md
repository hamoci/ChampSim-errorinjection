# 옆컴퓨터 실행 지침 — 멀티코어 Exp 2'/6'/7' (GAP 전용, 26코어)

> 기준 커밋: `716ed68` 이상 (clustered fault model + exp267 인프라 포함).
> 본컴퓨터는 동일 조건으로 SPEC(M1/C1/H1) + real-world를 실행 중이므로,
> 옆컴퓨터는 **GAP 동종 4-copy 믹스만** 담당한다.

## 0. 실험 요약

- 4-core, 8MB/16-way LLC, 2MB pages, 32GB DDR5 (멀티코어 Exp1 템플릿 동일)
- 주입: **clustered** fault model (seed 54321, FIT 18.6:8.2:10.0) — Exp7'만 주입 OFF
- warmup 50M + sim 250M per core
- 실험 3종 × GAP 5믹스 = **46 바이너리 × 5 = 230 runs**
  - Exp2' retirement threshold: thr {2,4,8,16,32} × {pin, off} @ 1e-8 (10)
  - Exp6' max errway sweep: max_ways {1,2,4,6,8,10,12} × {1e-5,1e-6,1e-7,1e-8}, pin (28)
  - Exp7' no-error way sweep: LLC ways 8~15, noerr (8; w16은 Exp1 noerr 재사용)

## 1. 준비

```bash
git pull                                  # 716ed68 이상인지 확인: git log --oneline -1
# (최초 1회만) vcpkg 의존성:
git submodule update --init && vcpkg/bootstrap-vcpkg.sh && vcpkg/vcpkg install
# GAP 트레이스 확인 (19개, bc/bfs/cc/pr/sssp):
ls test_traces/gap/*.trace.gz | wc -l     # 다른 경로면 실행 시 TRACE_DIR=<경로> 지정
```

## 2. 빌드 (46개, config당 1회씩 — config.sh에 JSON 여러 개 넘기면 병합되므로 금지)

```bash
JOBS=24 ./sim_configs/multicore/build_267.sh      # 26코어 머신: 빌드도 24로 제한
ls bin/ | grep -cE "thr|mw|noerr_w"               # 46이면 정상
```

## 3. 발사 (26코어 유지, 실험 간 배리어 없음 — 슬롯 비는 즉시 다음 작업 투입)

```bash
mkdir -p results/multicore
nohup env FAMILY=gap MAX_PARALLEL=26 RUN_TIMEOUT=36h \
  ./sim_configs/multicore/run_267.sh all > results/multicore/run_267_gap_nohup.log 2>&1 &
```

- 결과: `results/multicore/{2_retirement_threshold,6_llc_way_sweep,7_no_error_way_sweep}/`
  파일명 `<binary>_<mix>.txt`, 진행 로그는 각 디렉토리의 `run_267.log`
- **재시작 안전**: skip-if-done — 중단됐으면 같은 명령 재실행하면 완료분은 건너뜀
- 예상 소요: 230 runs ÷ 26병렬 ≈ 9웨이브 → **대략 3~4일** (run당 4~12h 가정)

## 4. GAP 믹스 정의 (동종 4-copy; 인스턴스 바꾸려면 run_267.sh의 `T=` 테이블 수정)

| mix | 트레이스 ×4 |
|---|---|
| G_BC | gap/bc-3.trace.gz |
| G_BFS | gap/bfs-3.trace.gz |
| G_CC | gap/cc-5.trace.gz |
| G_PR | gap/pr-3.trace.gz |
| G_SSSP | gap/sssp-3.trace.gz |

## 5. 모니터링 / 문제 대응

```bash
grep -c DONE results/multicore/*/run_267.log          # 완료 수 (총 230)
grep FAIL results/multicore/*/run_267.log             # 실패 확인
tail -2 results/multicore/6_llc_way_sweep/run_267.log # 최근 이벤트
```

- FAIL/timeout run은 전체 완료 후 같은 발사 명령을 한 번 더 실행하면 자동 재시도
- off_thr2 @1e-8 계열은 retirement가 많아 가장 느림 — RUN_TIMEOUT 36h가 안전장치

## 6. 완료 후 결과 회수 (본컴퓨터로)

```bash
rsync -av results/multicore/2_retirement_threshold/*_G_*.txt \
          results/multicore/6_llc_way_sweep/*_G_*.txt \
          results/multicore/7_no_error_way_sweep/*_G_*.txt \
          <본컴>:~/Study/ChampSim/results/multicore/<각 디렉토리>/
```
(run_267.log는 머신별로 유지 — 파일명이 겹치지 않으므로 txt만 옮기면 됨)
