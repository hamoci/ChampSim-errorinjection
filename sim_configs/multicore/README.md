# Multicore (4-core) Mix 실험

LLC Pinning 논문의 멀티코어 확장 실험 (Exp 1: error rate sweep).
목적: 3개 scheme(baseline / conventional page offline / LLC pinning)의 우위가
멀티코어 mix 환경에서도 유지됨을 보이는 리뷰어 대비 IPC 증거.

## 시스템 구성

| 항목 | 값 | 비고 |
|------|-----|------|
| 코어 | 4-core OoO (4GHz, ROB 352) | 싱글코어 실험과 동일 코어 파라미터 |
| LLC | **8MB / 16-way** (8192 sets) | per-core 2MB 유지 (싱글코어 2MB와 비교 논리 일관) |
| Page | 2MB hugepage | 논문 scope |
| DRAM | DDR5-4800, 2ch, 32GB | 싱글코어 실험과 동일 |
| Warmup / Sim | 50M / 250M per core | 아웃라인 Experimental Setup과 동일 |

PTW 주의: 멀티코어 config에서는 `PTW.lower_level`을 **명시하지 않아야**
defaults가 각 코어의 자기 L1D로 배선함 (`cpu0_L1D` 명시 시 전 코어가
cpu0으로 잘못 배선됨). `generate_configs.py` 참조.

## Scheme × Error rate = 바이너리 7개

| Scheme | 바이너리 | 설정 |
|--------|---------|------|
| Baseline (no-error) | `champsim_4core_8mb_noerr` | mode OFF, 정규화 기준 |
| Conventional page offline | `champsim_4core_8mb_off_{1e-6,1e-7,1e-8}` | baseline_retirement_threshold=2 (Linux RAS/CEC 기본) |
| LLC Pinning (ours) | `champsim_4core_8mb_pin_{1e-6,1e-7,1e-8}` | retirement_threshold=32, max_error_ways=8, dynamic latency |

Error rate 라벨은 CE rate 관례를 따름 (1e-8 = 최고 스트레스,
error_cycle_interval 144K cycles; 1e-6 = 14.4M cycles).
1e-8에서 conventional offline은 retirement 페널티(454,568 cycles) 폭증으로
일부 mix가 사실상 완주 불가할 수 있음 → `RUN_TIMEOUT`으로 절단
(그 자체가 "conventional 붕괴" 데이터 포인트).

## Mix 구성 (총 10개)

SPEC CPU 2017 10개 워크로드를 2MB 페이지 **RBMPKI** 순으로 정렬하면 5:5로
갈림 (출처: `stat_script_rev/baseline_workloads_rbmpki_ipc.csv`).
GAP은 사용자 결정으로 제외 (SPEC group만 사용).

### Pool

| Memory pool (High RBMPKI) | RBMPKI | CPU pool (Mid/Low RBMPKI) | RBMPKI |
|---|---|---|---|
| 605.mcf | 21.4 | 607.cactuBSSN | 8.1 |
| 649.fotonik3d | 21.0 | 621.wrf | 6.1 |
| 602.gcc | 17.8 | 654.roms | 5.0 |
| 603.bwaves | 16.3 | 628.pop2 | 4.5 |
| 620.omnetpp | 13.3 | 623.xalancbmk | 2.8 |

### Memory-intensive (M1–M4): memory pool 5개 중 1개씩 제외 (leave-one-out)

| Mix | CPU0 | CPU1 | CPU2 | CPU3 | 제외 |
|-----|------|------|------|------|------|
| M1 | mcf | fotonik3d | gcc | bwaves | omnetpp |
| M2 | mcf | fotonik3d | gcc | omnetpp | bwaves |
| M3 | mcf | fotonik3d | bwaves | omnetpp | gcc |
| M4 | mcf | gcc | bwaves | omnetpp | fotonik3d |

### CPU-intensive (C1–C4): cpu pool leave-one-out

| Mix | CPU0 | CPU1 | CPU2 | CPU3 | 제외 |
|-----|------|------|------|------|------|
| C1 | xalancbmk | pop2 | roms | wrf | cactuBSSN |
| C2 | xalancbmk | pop2 | roms | cactuBSSN | wrf |
| C3 | xalancbmk | pop2 | wrf | cactuBSSN | roms |
| C4 | xalancbmk | roms | wrf | cactuBSSN | pop2 |

### Hybrid (H1–H2): memory 2 + cpu 2

| Mix | CPU0 | CPU1 | CPU2 | CPU3 | 구성 의도 |
|-----|------|------|------|------|----------|
| H1 | mcf | fotonik3d | xalancbmk | pop2 | mem 최상위 2 + cpu 최하위 2 (대비 극대화) |
| H2 | gcc | omnetpp | wrf | roms | mem 중위 2 + cpu 중위 2 |

설계 의도:
- **M**: 에러 흡수 多 + LLC 경쟁 극심 (최악 조건)
- **C**: 메모리 접근 少 → 에러 노출 적은 온화한 조건
- **H**: memory-heavy 코어가 에러를 흡수할 때 CPU-heavy 코어가 error way
  용량 손실로 받는 간섭 측정 (per-CPU 에러 귀속 통계로 분석)
- leave-one-out 5→4 조합 중 M5(mcf 제외)/C5(xalancbmk 제외)는 미사용
  (pool 대표 워크로드 유지). 필요 시 `run_mixes.sh`의 MIXES에 추가.

## 실행

```bash
# 전체 (10 mix × 7 binary = 70 runs)
cd /home/hamoci/Study/ChampSim
MAX_PARALLEL=38 RUN_TIMEOUT=48h nohup ./sim_configs/multicore/run_mixes.sh > /dev/null 2>&1 &

# 일부 mix만
./sim_configs/multicore/run_mixes.sh M1 C1 H1
```

- 결과: `results/multicore/1_error_rate_sweep/champsim_4core_8mb_{scheme}_{mix}.txt`
- 로그: 같은 디렉토리 `run_mixes.log` — DONE/FAIL 라인에 `elapsed=초 (H:MM:SS)` 기록
- 완료 run은 자동 skip (재실행 안전), TIMEOUT run은 재실행 시 재시도
- 진행 확인: `grep -c DONE results/multicore/1_error_rate_sweep/run_mixes.log` (70 = 완료)

## 파싱

```bash
python3 stat_script_rev/parse_multicore_exp1.py
```

출력:
- `multicore_exp1_percpu.csv` — (mix, scheme, cpu)별 IPC / noerr 대비 정규화 IPC / LLC MPKI / per-CPU 에러 귀속(absorbed/first/added/retired)
- `multicore_exp1_summary.csv` — (mix, scheme)별 weighted speedup, 정규화 throughput, 에러/retirement 총계
- 콘솔: mix × scheme weighted speedup 피벗 표

지표 정의:
- **weighted speedup** = Σᵢ (IPCᵢ^scheme / IPCᵢ^noerr), 같은 mix의 noerr run을
  reference로 사용 (max 4.0)
- per-CPU IPC는 ChampSim 출력의 **마지막** "CPU n cumulative IPC" 블록(ROI,
  코어별 자기 250M 명령어 기준)에서 추출 — 첫 블록은 전 코어 종료 대기까지
  포함된 전체 실행 통계라 사용하지 않음
