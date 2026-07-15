# Paper Figures

논문 outline에 사용 중인 figure들을 한 곳에 모은 디렉토리.
스크립트는 그대로 실행 가능 (`python figN_*.py`).
출력은 같은 디렉토리에 떨어짐.

## Figure 매핑

| 신규 ID | 기존 ID | Script | 결과 파일 | 설명 |
|---|---|---|---|---|
| **fig0** | (was fig6c) | `fig0_baseline_llc_mpki.py` | `fig0_baseline_llc_mpki.{csv,pdf,png}` | No-error baseline LLC MPKI (2MB LLC) |
| **fig1** | (was fig0_vertical) | `fig1_baseline_page.py` | `fig1_baseline_page.{csv,pdf,png}` | 4KB vs 2MB page IPC speedup |
| **fig2** | (was fig6) | `fig2_pinning_vs_offline.py` | `fig2_pinning_vs_offline.{csv,pdf,png}` | LLC Pinning vs Page Offline (GMEAN + per-workload) |
| **fig3** | (was fig7d) | `fig3_protected_lines.py` | `fig3_protected_lines.{csv,pdf,png}` + `_workloads.csv` | Retirement threshold별 IPC와 protected line coverage |
| **fig4** | (was fig8) | `fig4_capacity_waste.py` | `fig4_capacity_waste.{csv,pdf,png}` | DRAM capacity waste vs MTBCE |
| **fig5** | (was fig8b) | `fig5_migration_reduction.py` | `fig5_migration_reduction.{pdf,png}` + `_summary.csv` + `_workloads_1e-8.csv` | Page migration 감소율 |
| **fig6** | (was fig11_2MB_1e-8) | `fig6_max_errway_2MB_1e-8.py` | `fig6_max_errway_2MB_1e-8.{csv,pdf,png}` | 2MB LLC, 1e-8 rate에서 max error-way 별 IPC와 protected lines |
| **fig7** | (was fig12) | `fig7_no_error_way_sweep.py` | `fig7_no_error_way_sweep.{csv,pdf,png}` | No-error way reservation sensitivity |
| **fig8** | (was fig13) | `fig8_no_error_vs_offline.py` | `fig8_no_error_vs_offline.{csv,pdf,png}` | No-error baseline vs Conventional Page Offline (capacity waste overlay) |

## 사용법

```bash
cd normal_evaluation_script/paper_figures
python fig0_baseline_llc_mpki.py
python fig1_baseline_page.py
# ... 등등
```

전체 일괄 재생성:
```bash
for f in fig*.py; do python "$f"; done
```

## 의존성 메모

- 모든 스크립트는 상위 디렉토리(`../`)의 `common_normal.py`를 `sys.path` 주입으로 사용함. 이 파일이 사라지면 작동 안함.
- `fig8_no_error_vs_offline.py`는 같은 디렉토리의 `fig4_capacity_waste.csv`를 읽어 capacity waste 마커를 그림. **fig4를 먼저 실행**해야 그 overlay가 표시됨.
- `fig1_baseline_page.py`는 `results/normal_evaluation_0506/baseline/`에서 데이터를 읽음 (다른 figure들은 `results/normal_evaluation/`을 씀).
- `fig6`는 sweep 결과 중 **2MB LLC, 1e-8 rate**만 추출하도록 slim 처리. 원본 `../11_max_errway_sweep.py`는 다른 size/rate variant도 함께 생성하지만 이 paper 버전은 한 variant만 출력.

## GAP 벤치마크 + panic 처리

실험 2/6/7(`retirement_threshold`, `llc_way_sweep`, `no_error_way_sweep`)은 SPEC에
더해 GAP 벤치마크(`bc/bfs/cc/pr/sssp-N`)도 함께 파싱한다.

- **데이터 소스**: GAP 결과는 `results/normal_evaluation/*_gap/`(repo 최상위)에 있고,
  `generate_raw_data.py`의 `resolve_sources()`가 SPEC(`paper_figures/results/`)와
  GAP을 함께 읽어 한 시트로 합친다. 각 행에 `suite`(SPEC/GAP), `completed` 컬럼 추가.
- **suite 분리 / 색 인코딩**:
  - suite만 구분(fig0, fig11): 색으로 — SPEC 파랑 `#2E6FDB` / GAP raspberry `#E5487E`
    (paper-wide accent pair와 동일).
  - method×suite(fig9, fig10, fig4, fig12): **색조=method**(blue pinning /
    raspberry offline), **밝기=suite**(SPEC 진함 / GAP 연함)로 paired 음영.
    hatch는 안 씀.
    `BAR_COLOR`: off SPEC `#E5487E`/GAP `#F4A6C2`, on SPEC `#2E6FDB`/GAP `#9FBEF0`.
    (fig12는 2-panel이라 패널로 suite 구분, 막대는 method 색만 사용)
  - fig13/14는 위치로 suite 구분 + `SPEC GMEAN`/`GAP GMEAN` 두 컬럼 (way는 파랑 gradient).
- **panic(미완료) 처리**: 최종 `CPU 0 cumulative IPC` 라인이 없는 run은 panic으로 보고
  `completed=False`로 표시. ChampSim heartbeat가 IPC<0.01에서 abort한 경우다(주로
  threshold=2, 1e-8).
  - **IPC**: panic은 IPC=0으로 간주하고 기하평균에 **포함** → 0이 하나라도 있으면 해당
    config 막대가 0으로 붕괴(`gmean(..., include_zeros=True)`).
  - **page/coverage 류 메트릭**: panic run의 통계는 오염 우려로 **완전 제외**(NaN).
    그래서 GAP의 1e-8 page-offline은 전부 panic이라 fig10/12에서 비어 보인다.

## 결과 파일 종류

- **`.pdf`** — 논문 삽입용 (vector, fonttype=42)
- **`.png`** — 프리뷰 (400 dpi)
- **`.csv`** — raw data

## 원본 위치

원본 스크립트는 상위 `normal_evaluation_script/` 폴더에 그대로 보존:

| 신규 | 원본 |
|---|---|
| fig0 | `../6c_baseline_llc_mpki.py` |
| fig1 | `../0b_baseline_page_comparison_vertical.py` (+ `../0_baseline_page_comparison.py` 로더) |
| fig2 | `../6_pinning_vs_offline.py` |
| fig3 | `../7d_retirement_threshold_protected_lines.py` |
| fig4 | `../8_capacity_waste_vs_offline.py` |
| fig5 | `../8b_page_migration_reduction.py` |
| fig6 | `../11_max_errway_sweep.py` |
| fig7 | `../12_no_error_way_sweep.py` |
| fig8 | `../13_no_error_vs_offline.py` |
