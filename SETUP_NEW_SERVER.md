# 새 서버 셋업 — Clone부터 CARE clustered 실험까지

> 대상: 완전히 새로 세팅하는 머신. 이 문서대로 하면 clone → 빌드 → CARE 멀티코어
> 실험(60 runs)까지 바로 이어진다. (GAP exp2'/6'/7'용은 `sim_configs/multicore/RUN_267_GAP_MACHINE.md` 참조)

## 0. 사전 요구사항 (Ubuntu 기준)

```bash
sudo apt install -y build-essential g++ git cmake curl zip unzip tar pkg-config python3
# g++ 12 이상 권장 (본 서버는 12), python3는 config.sh용
```

## 1. Clone + 의존성 (최초 1회, ~10분)

```bash
git clone https://github.com/hamoci/ChampSim-errorinjection ChampSim
cd ChampSim
git submodule update --init          # vcpkg
vcpkg/bootstrap-vcpkg.sh
vcpkg/vcpkg install                  # CLI11/fmt/lzma/zlib/bz2/Catch2
```

## 2. 트레이스 전송 (본 서버 → 새 서버)

멀티코어 mix에 필요한 것은 SPEC 10개뿐 (전체 68GB 중 일부만):

```bash
# 본 서버에서 실행 (NEW=새 서버 주소):
cd /home/hamoci/Study/ChampSim
rsync -av --progress \
  test_traces/602.gcc_s-1850B.champsimtrace.xz \
  test_traces/603.bwaves_s-2931B.champsimtrace.xz \
  test_traces/605.mcf_s-994B.champsimtrace.xz \
  test_traces/607.cactuBSSN_s-2421B.champsimtrace.xz \
  test_traces/620.omnetpp_s-141B.champsimtrace.xz \
  test_traces/621.wrf_s-6673B.champsimtrace.xz \
  test_traces/623.xalancbmk_s-592B.champsimtrace.xz \
  test_traces/628.pop2_s-17B.champsimtrace.xz \
  test_traces/649.fotonik3d_s-10881B.champsimtrace.xz \
  test_traces/654.roms_s-1007B.champsimtrace.xz \
  $NEW:~/ChampSim/test_traces/
```

다른 경로에 두면 실행 시 `TRACE_DIR=<경로>` env로 지정.

## 3. 빌드 (CARE clustered 6종 + noerr 1종)

```bash
JOBS=<코어수-4> ./sim_configs/multicore/build_care_clustered.sh
ls bin/ | grep -c "care.*clu\|noerr"     # 7이면 정상
```

주의 (이 저장소의 두 가지 함정):
- **config.sh에 JSON을 여러 개 넘기면 병합**되어 오염된 바이너리가 나온다 — 반드시 하나씩 (빌드 스크립트가 이미 그렇게 함).
- 모든 `error_page_manager` 설정(seed 포함)은 **컴파일 타임에 박힌다** — 설정 변경 = 재빌드.

## 4. 발사 — CARE clustered Exp1 (6 binaries × 10 mixes = 60 runs)

```bash
mkdir -p results/multicore
nohup env MAX_PARALLEL=<코어수-4> RUN_TIMEOUT=36h \
  ./sim_configs/multicore/run_mixes_care_clustered.sh \
  > results/multicore/run_mixes_care_clustered_nohup.log 2>&1 &
```

- 예상 소요: run당 4~12시간 (mix 무게에 따라), 병렬로 하루 안팎.
- skip-if-done: 중단 후 재실행하면 완료된 run은 건너뜀.
- 모니터링:
  ```bash
  tail -f results/multicore/1_error_rate_sweep_care_clustered/run_mixes.log
  grep -c DONE results/multicore/1_error_rate_sweep_care_clustered/run_mixes.log   # /60
  ```

## 5. 분석에 필요한 기준선

Weighted speedup 분모는 **같은 mix의 noerr run**:
- 옵션 A (권장): 본 서버의 기존 결과 복사 —
  `rsync -av 본서버:~/Study/ChampSim/results/multicore/1_error_rate_sweep/champsim_4core_8mb_noerr_*.txt results/multicore/1_error_rate_sweep/`
- 옵션 B: 새 서버에서 재실행 (noerr 바이너리는 build 스크립트에 포함, 10 runs 추가)

uniform CARE와의 비교가 필요하면 기존 `results/multicore/1_error_rate_sweep/champsim_4core_8mb_care*_*.txt`도 복사
(단, **CARE는 07-16 재구현으로 기존 uniform CARE 결과가 무효** — 재비교하려면 uniform CARE도 재실행 필요.
uniform 재실행은 `sim_configs/multicore/care*/` 그대로 빌드하면 됨).

## 6. 결과 해석 도구

- `stat_script_rev/compare_multicore_clustered.py` — off/pin uniform vs clustered 비교 (CARE 추가는 RE_CLU 정규식에 `care[a-z_]*` 확장)
- `[CARE][RETIRE]` / `[CARE][PROACTIVE]` 상시 로그가 각 run 출력에 기록됨 (grep 가능 고정 포맷)
- 배경 문서: `error_injection_docs/` 01~09 (특히 07 CARE 설계 분석, 08 모델 직관, 09 멀티코어 결과)

## 7. 실험 매트릭스 요약 (이 세팅이 커버하는 것)

| 축 | 값 |
|---|---|
| Scheme | care(reactive) / care_scrub / care_proscrub(proactive, **OR 트리거 기본**) |
| Rate | 1e-7 (interval 1.44M) / 1e-8 (144k) |
| 주입 | clustered (seed 54321, FIT 18.6:8.2:10.0, reuse 0.7) |
| Mix | M1-4 / C1-4 / H1-2 (SPEC 4-copy) |
| 실행 | warmup 50M + sim 250M per core |

AND 트리거 ablation이 필요하면 config에 `"care_proactive_or": false` 추가 후 재빌드.
