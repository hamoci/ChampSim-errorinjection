#!/usr/bin/env python3
"""
ChampSim Way (Associativity) Analysis
Baseline 대비 Way 감소에 따른 IPC 비교
SPEC 벤치마크만 사용
"""

import os
import re
import matplotlib.pyplot as plt
import numpy as np
import csv
from collections import defaultdict

def geometric_mean(values):
    """기하평균 계산"""
    if not values or any(v <= 0 for v in values):
        return 0
    return np.exp(np.mean(np.log(values)))

def parse_ipc_from_file(file_path):
    """파일에서 최종 IPC 값을 추출"""
    try:
        with open(file_path, 'r') as f:
            content = f.read()

        # "Simulation complete" 또는 "Simulation finished" 라인에서 최종 IPC 찾기
        match = re.search(r'Simulation (complete|finished).*?cumulative IPC:\s*([0-9.]+)', content)
        if match:
            return float(match.group(2))

        # 만약 찾지 못했다면, 마지막 cumulative IPC 찾기
        matches = re.findall(r'cumulative IPC:\s*([0-9.]+)', content)
        if matches:
            return float(matches[-1])

    except Exception as e:
        print(f"Error parsing {file_path}: {e}")

    return None

def is_spec_benchmark(workload):
    """SPEC 벤치마크인지 확인 (xxx.xxx 형태)"""
    pattern = r'^\d+\.\w+$'
    return bool(re.match(pattern, workload))

def parse_way_results(results_dir):
    """Way 변화 결과 파싱 (page size별로 분리)"""
    # data[page_size][workload][way_config] = ipc
    data = defaultdict(lambda: defaultdict(dict))

    for filename in os.listdir(results_dir):
        if not filename.endswith('.txt'):
            continue

        file_path = os.path.join(results_dir, filename)

        # 파일명 패턴: champsim_2mb_{ways}_{pagesize}_{capacity}_{workload}.txt
        # 예: champsim_2mb_10ways_2mb_32gb_602.gcc_s-1850B.txt
        pattern = r'champsim_2mb_(\d+ways)_(\w+)_\w+_(\d+\.\w+.*?)\.txt'
        match = re.search(pattern, filename)

        if match:
            way_config = match.group(1)
            page_size = match.group(2)  # 2mb 또는 4kb
            workload_full = match.group(3)

            # 워크로드명 정리 (SPEC 형태만)
            workload_match = re.match(r'(\d+)\.(\w+)', workload_full)
            if workload_match:
                workload = f"{workload_match.group(1)}.{workload_match.group(2)}"

                # SPEC 벤치마크만 필터링
                if is_spec_benchmark(workload):
                    ipc = parse_ipc_from_file(file_path)
                    if ipc is not None:
                        data[page_size][workload][way_config] = ipc
                        print(f"  Parsed: {workload} ({page_size}) - {way_config} = {ipc:.4f}")

    return data

def create_way_comparison_plot(way_data, baseline='16ways', output_dir='results/260107_cache_sensitive/way'):
    """Way 감소에 따른 IPC 비교 그래프 - 4kb와 2mb 통합"""

    if not way_data:
        print("Way 데이터 없음")
        return

    # 논문용 설정
    plt.rcParams.update({
        'font.size': 18,
        'axes.labelsize': 22,
        'axes.titlesize': 24,
        'xtick.labelsize': 18,
        'ytick.labelsize': 18,
        'legend.fontsize': 20,
        'lines.linewidth': 4,
        'lines.markersize': 12
    })

    # Way 순서 정의 (16 -> 8)
    way_configs = ['16ways', '15ways', '14ways', '13ways', '12ways', '11ways', '10ways', '9ways', '8ways']
    way_labels = [w.replace('ways', '-way') for w in way_configs]

    fig, ax = plt.subplots(figsize=(14, 9))

    # 페이지 크기별 색상 및 마커 설정
    page_size_config = {
        '4kb': {'color': '#EE5A6F', 'marker': 'o', 'label': '4KB Page'},
        '2mb': {'color': '#4A90E2', 'marker': 's', 'label': '2MB Page'}
    }

    all_y_values = []  # Y축 범위 계산을 위한 모든 값 저장

    # 각 페이지 크기별로 처리
    for page_size in sorted(way_data.keys()):
        data = way_data[page_size]
        config = page_size_config.get(page_size, {'color': 'gray', 'marker': 'o', 'label': page_size})

        # 사용 가능한 way config만 필터링
        available_ways = []
        available_labels = []
        for way, label in zip(way_configs, way_labels):
            # 적어도 하나의 워크로드에서 해당 way config가 있는지 확인
            if any(way in workload_data for workload_data in data.values()):
                available_ways.append(way)
                available_labels.append(label)

        if not available_ways:
            continue

        workloads = sorted(data.keys())

        # 각 way config별 평균 IPC 계산
        avg_ipcs = []
        for way in available_ways:
            ipcs = []
            for workload in workloads:
                if way in data[workload]:
                    ipcs.append(data[workload][way])

            if ipcs:
                avg_ipc = geometric_mean(ipcs)
                avg_ipcs.append(avg_ipc)
            else:
                avg_ipcs.append(None)

        # X축 값 (Way 수를 숫자로)
        x_values = [int(w.replace('ways', '')) for w in available_ways]

        # 그래프 그리기
        valid_points = [(x, y) for x, y in zip(x_values, avg_ipcs) if y is not None]
        if valid_points:
            x_plot, y_plot = zip(*valid_points)
            ax.plot(x_plot, y_plot, marker=config['marker'], linestyle='-',
                   color=config['color'], linewidth=4, markersize=12,
                   label=config['label'], zorder=3)

            # 값 표시
            for x, y in zip(x_plot, y_plot):
                ax.text(x, y + 0.02, f'{y:.3f}', ha='center', va='bottom',
                       fontsize=14, fontweight='bold', color=config['color'])

            all_y_values.extend(y_plot)

    ax.set_xlabel('Cache Associativity (Way)', fontweight='bold', fontsize=22)
    ax.set_ylabel('Average IPC', fontweight='bold', fontsize=22)
    ax.set_title('IPC vs Cache Associativity (4KB vs 2MB Page)', fontweight='bold', fontsize=24, pad=15)
    ax.legend(loc='best', frameon=True, fancybox=True, fontsize=20)
    ax.grid(True, alpha=0.3, linewidth=1.5, linestyle='-', color='gray')
    ax.set_facecolor('white')

    # X축을 log scale로 설정하고 역순으로
    ax.set_xscale('log', base=2)
    ax.invert_xaxis()

    # 모든 way 값을 수집하여 X축 설정
    all_x_values = []
    for way in way_configs:
        x_val = int(way.replace('ways', ''))
        if any(way in workload_data for page_data in way_data.values() for workload_data in page_data.values()):
            all_x_values.append(x_val)

    if all_x_values:
        ax.set_xticks(all_x_values)
        ax.set_xticklabels([w.replace('ways', '-way') for w in way_configs if int(w.replace('ways', '')) in all_x_values])

    # Y축 범위 설정
    if all_y_values:
        y_min = min(all_y_values) * 0.85
        y_max = max(all_y_values) * 1.15
        ax.set_ylim(y_min, y_max)

    plt.tight_layout()
    output_file = f'/home/hamoci/Study/ChampSim/{output_dir}/way_comparison_ipc_combined.png'
    plt.savefig(output_file, dpi=300, bbox_inches='tight', facecolor='white', edgecolor='none')
    print(f"통합 Way 비교 그래프 저장: {output_file}")

    # 페이지 크기별 감소율 분석
    for page_size in sorted(way_data.keys()):
        data = way_data[page_size]

        # 사용 가능한 way config만 필터링
        available_ways = []
        available_labels = []
        avg_ipcs = []

        for way, label in zip(way_configs, way_labels):
            if any(way in workload_data for workload_data in data.values()):
                available_ways.append(way)
                available_labels.append(label)

                # 평균 IPC 계산
                ipcs = []
                for workload in data.keys():
                    if way in data[workload]:
                        ipcs.append(data[workload][way])

                if ipcs:
                    avg_ipcs.append(geometric_mean(ipcs))
                else:
                    avg_ipcs.append(None)

        print(f"\n{'='*80}")
        print(f"IPC 감소율 분석 - {page_size.upper()} Page Size")
        print(f"{'='*80}")

        if baseline in available_ways and avg_ipcs[available_ways.index(baseline)] is not None:
            baseline_ipc = avg_ipcs[available_ways.index(baseline)]
            print(f"\nBaseline ({baseline}): {baseline_ipc:.4f}")
            print(f"{'Configuration':<15} {'IPC':<12} {'감소율 (%)':<15} {'절대 감소':<15}")
            print("-" * 60)

            for way, label, ipc in zip(available_ways, available_labels, avg_ipcs):
                if ipc is not None:
                    decrease_pct = ((baseline_ipc - ipc) / baseline_ipc) * 100
                    abs_decrease = baseline_ipc - ipc
                    print(f"{label:<15} {ipc:<12.4f} {decrease_pct:<15.2f} {abs_decrease:<15.4f}")

        print(f"{'='*80}\n")

    plt.close()

def create_individual_workload_plots(way_data, output_dir='results/260107_cache_sensitive/way'):
    """개별 워크로드별 비교 그래프 - 4kb와 2mb 통합"""

    if not way_data:
        print("Way 데이터 없음")
        return

    # 논문용 설정
    plt.rcParams.update({
        'font.size': 11,
        'axes.labelsize': 12,
        'axes.titlesize': 13,
        'xtick.labelsize': 10,
        'ytick.labelsize': 11,
        'legend.fontsize': 9,
        'lines.linewidth': 2,
        'lines.markersize': 6
    })

    # 모든 페이지 크기의 워크로드를 모음
    all_workloads = set()
    for page_data in way_data.values():
        all_workloads.update(page_data.keys())

    workloads = sorted(all_workloads)
    num_workloads = len(workloads)

    if num_workloads == 0:
        return

    # 레이아웃 계산
    cols = 5
    rows = (num_workloads + cols - 1) // cols

    fig, axes = plt.subplots(rows, cols, figsize=(15, 3 * rows))
    if rows == 1:
        axes = axes.reshape(1, -1)
    axes = axes.flatten()

    # 설정별 정보
    configs = ['16ways', '15ways', '14ways', '13ways', '12ways', '11ways', '10ways', '9ways', '8ways']
    labels = [c.replace('ways', '-way') for c in configs]
    x_values = [int(c.replace('ways', '')) for c in configs]

    # 페이지 크기별 색상 및 마커 설정
    page_size_config = {
        '4kb': {'color': '#EE5A6F', 'marker': 'o', 'label': '4KB'},
        '2mb': {'color': '#4A90E2', 'marker': 's', 'label': '2MB'}
    }

    for idx, workload in enumerate(workloads):
        ax = axes[idx]

        # 각 페이지 크기별로 플롯
        for page_size in sorted(way_data.keys()):
            data = way_data[page_size]

            if workload not in data:
                continue

            config = page_size_config.get(page_size, {'color': 'gray', 'marker': 'o', 'label': page_size})

            # 워크로드별 IPC 값
            ipc_values = []
            for cfg in configs:
                if cfg in data[workload]:
                    ipc_values.append(data[workload][cfg])
                else:
                    ipc_values.append(None)

            # 유효한 포인트만 플롯
            valid_points = [(x, y, l) for x, y, l in zip(x_values, ipc_values, labels) if y is not None]
            if valid_points:
                x_plot, y_plot, _ = zip(*valid_points)
                ax.plot(x_plot, y_plot, marker=config['marker'], linestyle='-',
                       color=config['color'], linewidth=2, markersize=6,
                       label=config['label'])

        # 워크로드 이름
        workload_name = workload.split('.')[1] if '.' in workload else workload
        ax.set_title(f'{workload_name}', fontweight='bold', fontsize=13)
        ax.set_xlabel('Associativity', fontweight='bold', fontsize=11)
        ax.set_ylabel('IPC', fontweight='bold', fontsize=11)
        ax.set_xscale('log', base=2)
        ax.invert_xaxis()

        # X축 레이블 설정
        ax.set_xticks(x_values)
        ax.set_xticklabels(labels, rotation=45)

        ax.grid(True, alpha=0.3, linewidth=0.8)

        # 첫 번째 서브플롯에만 범례 추가
        if idx == 0:
            ax.legend(loc='best', fontsize=9, frameon=True)

    # 빈 서브플롯 숨기기
    for idx in range(len(workloads), len(axes)):
        axes[idx].set_visible(False)

    # 전체 제목
    fig.suptitle(f'Individual Workload IPC - Way Comparison (4KB vs 2MB Page)',
                 fontsize=16, fontweight='bold', y=0.998)

    plt.tight_layout(rect=[0, 0, 1, 0.99])
    output_file = f'/home/hamoci/Study/ChampSim/{output_dir}/individual_way_comparison_combined.png'
    plt.savefig(output_file, dpi=300, bbox_inches='tight', facecolor='white', edgecolor='none')
    print(f"통합 개별 워크로드 way 그래프 저장: {output_file}")
    plt.close()

def save_to_csv(data, output_dir='results/260107_cache_sensitive/way'):
    """데이터를 CSV 파일로 저장"""

    if not data:
        return

    configs = ['15ways', '14ways', '13ways', '12ways', '11ways', '10ways', '9ways', '8ways']
    config_labels = [c.replace('ways', '-way') for c in configs]
    csv_filename = f'{output_dir}/way_comparison.csv'

    # 실제 사용 가능한 config만 필터링
    available_configs = []
    available_labels = []
    for config, label in zip(configs, config_labels):
        if any(config in workload_data for workload_data in data.values()):
            available_configs.append(config)
            available_labels.append(label)

    if not available_configs:
        print(f"CSV 저장 실패: 사용 가능한 way 구성이 없습니다")
        return

    # CSV 파일 작성
    with open(csv_filename, 'w', newline='') as csvfile:
        writer = csv.writer(csvfile)

        # 헤더 작성
        header = ['Workload'] + available_labels + ['Average', 'StdDev']
        writer.writerow(header)

        # 각 워크로드별 데이터
        for workload in sorted(data.keys()):
            row = [workload]
            ipc_values = []

            for config in available_configs:
                ipc = data[workload].get(config, None)
                if ipc is not None:
                    row.append(f"{ipc:.4f}")
                    ipc_values.append(ipc)
                else:
                    row.append('N/A')

            # 통계
            if ipc_values:
                avg_ipc = sum(ipc_values) / len(ipc_values)
                std_dev = np.std(ipc_values) if len(ipc_values) > 1 else 0
                row.append(f"{avg_ipc:.4f}")
                row.append(f"{std_dev:.4f}")
            else:
                row.append('N/A')
                row.append('N/A')

            writer.writerow(row)

        # GMEAN 행 추가
        gmean_row = ['GEOMETRIC MEAN']
        for config in available_configs:
            ipcs = [data[wl].get(config, 0) for wl in data.keys()]
            valid_ipcs = [x for x in ipcs if x > 0]
            if valid_ipcs:
                gmean = geometric_mean(valid_ipcs)
                gmean_row.append(f"{gmean:.4f}")
            else:
                gmean_row.append('N/A')
        gmean_row.extend(['', ''])  # Average와 StdDev는 비워둠
        writer.writerow(gmean_row)

    print(f"CSV 파일 저장: {csv_filename}")

def print_summary_table(data):
    """결과 요약 테이블 출력"""

    if not data:
        return

    print("\n" + "="*100)
    print("WAY COMPARISON SUMMARY - SPEC Benchmarks Only")
    print("="*100)

    configs = ['15ways', '14ways', '13ways', '12ways', '11ways', '10ways', '9ways', '8ways']
    config_labels = [c.replace('ways', '-way') for c in configs]

    # 실제 사용 가능한 config만 필터링
    available_configs = []
    available_labels = []
    for config, label in zip(configs, config_labels):
        if any(config in workload_data for workload_data in data.values()):
            available_configs.append(config)
            available_labels.append(label)

    if not available_configs:
        print(f"사용 가능한 way 구성이 없습니다")
        return

    configs = available_configs
    config_labels = available_labels

    header = f"{'Workload':<20}"
    for label in config_labels:
        header += f"{label:>12}"
    header += f"{'Avg IPC':>12}{'StdDev':>12}"
    print(header)
    print("-" * len(header))

    for workload in sorted(data.keys()):
        row = f"{workload:<20}"

        ipc_values = []
        for config in configs:
            ipc = data[workload].get(config, 0)
            ipc_values.append(ipc)
            row += f"{ipc:>12.4f}" if ipc > 0 else f"{'N/A':>12}"

        # 통계
        valid_ipcs = [x for x in ipc_values if x > 0]
        avg_ipc = sum(valid_ipcs) / len(valid_ipcs) if valid_ipcs else 0
        std_dev = np.std(valid_ipcs) if len(valid_ipcs) > 1 else 0

        row += f"{avg_ipc:>12.4f}" if avg_ipc > 0 else f"{'N/A':>12}"
        row += f"{std_dev:>12.4f}" if std_dev > 0 else f"{'N/A':>12}"
        print(row)

    # GMEAN
    print("-" * len(header))
    gmean_row = f"{'GEOMETRIC MEAN':<20}"

    for config in configs:
        ipcs = [data[wl].get(config, 0) for wl in data.keys()]
        valid_ipcs = [x for x in ipcs if x > 0]
        if valid_ipcs:
            gmean = geometric_mean(valid_ipcs)
            gmean_row += f"{gmean:>12.4f}"
        else:
            gmean_row += f"{'N/A':>12}"

    print(gmean_row)
    print("="*100 + "\n")

def main():
    """메인 함수"""
    results_dir = '/home/hamoci/Study/ChampSim/results/260107_cache_sensitive/way'

    print("ChampSim Way (Associativity) 분석 중...")
    print("SPEC 벤치마크만 사용\n")

    print("="*80)
    print("Way (Associativity) 분석")
    print("="*80)
    way_data = parse_way_results(results_dir)

    if way_data:
        # 통합 출력 디렉토리
        combined_output_dir = 'results/260107_cache_sensitive/way'
        os.makedirs(combined_output_dir, exist_ok=True)

        # 통합 그래프 생성 (4kb와 2mb를 한 그래프에)
        create_way_comparison_plot(way_data, output_dir=combined_output_dir)
        create_individual_workload_plots(way_data, output_dir=combined_output_dir)

        # Page size별로 개별 처리 (CSV 및 요약 테이블)
        for page_size in sorted(way_data.keys()):
            print(f"\n{'='*80}")
            print(f"Page Size: {page_size.upper()}")
            print(f"{'='*80}")

            page_data = way_data[page_size]
            num_workloads = len(page_data)
            print(f"파싱된 SPEC 워크로드: {num_workloads}개")
            print(f"워크로드 목록: {', '.join(sorted(page_data.keys()))}\n")

            # 출력 디렉토리에 page size 추가
            output_dir = f'results/260107_cache_sensitive/way/{page_size}'
            os.makedirs(output_dir, exist_ok=True)

            print_summary_table(page_data)
            save_to_csv(page_data, output_dir=output_dir)
    else:
        print("Way 데이터를 찾을 수 없습니다.\n")

    print("\n" + "="*80)
    print("완료! 모든 그래프가 results/260107_cache_sensitive/way 폴더에 저장되었습니다.")
    print("="*80)
    print("\n생성된 파일:")
    print("  [통합 그래프]")
    print("    - way_comparison_ipc_combined.png: 4KB vs 2MB Page 평균 IPC 통합 그래프")
    print("    - individual_way_comparison_combined.png: 4KB vs 2MB Page 개별 워크로드 통합 그래프")
    print("  [각 page size별]")
    print("    - way_comparison.csv: Way 비교 데이터 (CSV)")

if __name__ == "__main__":
    main()
