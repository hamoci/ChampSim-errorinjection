#!/usr/bin/env python3
"""
ChampSim Server Workload Error Rate별 IPC 비교 스크립트 (논문 스타일)
동일 Capacity에서 1e-2 ~ 1e-9 까지의 Error Rate별 IPC 비교
Server Workloads: benchbase, dacapo, renaissance, nodeapp, mwnginxfpm, charlie, delta, merced, whiskey
"""

import os
import re
import matplotlib.pyplot as plt
import numpy as np
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

def parse_results_directory(results_dir):
    """결과 디렉토리에서 모든 결과 파싱"""
    # data[page_size][capacity][workload][error_rate] = ipc
    data = defaultdict(lambda: defaultdict(lambda: defaultdict(dict)))

    # 새로운 Benchmark 식별자 (압축 해제한 trace 파일들)
    new_benchmarks = [
        'benchbase-wikipedia', 'benchbase-twitter', 'benchbase-tpcc',
        'dacapo-kafka', 'dacapo-spring', 'dacapo-tomcat',
        'renaissance-finagle-chirper', 'renaissance-finagle-http',
        'nodeapp-nodeapp', 'nodeapp-nodeapp-small',
        'mwnginxfpm-wiki',
        'charlie', 'delta', 'merced', 'whiskey'
    ]

    for filename in os.listdir(results_dir):
        if not filename.endswith('.txt') or not filename.startswith('champsim_'):
            continue

        file_path = os.path.join(results_dir, filename)

        # 새로운 파일명 패턴: champsim_{pagesize}_error_{capacity}_{error_rate}_{workload}.champsim.trace.gz.txt
        # 예: champsim_2mb_error_128gb_1e-7_benchbase-wikipedia.champsim.trace.gz.txt
        pattern = r'champsim_(\w+)_error_(\w+)_(1e-\d+)_(.+?)\.champsim\.trace\.gz\.txt'
        match = re.search(pattern, filename)

        if match:
            page_size = match.group(1)
            capacity = match.group(2)
            error_rate = match.group(3)
            workload = match.group(4)

            # 벤치마크 필터링 (새로운 벤치마크만)
            if not any(bench in workload for bench in new_benchmarks):
                continue

            ipc = parse_ipc_from_file(file_path)
            if ipc is not None:
                data[page_size][capacity][workload][error_rate] = ipc

    return data

def create_average_comparison_plot(data, page_size='2mb', capacity='128gb', output_dir='results'):
    """Average IPC 비교 그래프 생성 (Server Workloads)"""

    if page_size not in data or capacity not in data[page_size]:
        print(f"데이터 없음: {page_size} {capacity}")
        return

    # 논문용 설정 - 더 큰 폰트와 선
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

    workload_data = data[page_size][capacity]
    workloads = sorted(workload_data.keys())

    # 실제 데이터에서 사용 가능한 error rate만 필터링
    available_error_rates = ['1e-2', '1e-3', '1e-4', '1e-5', '1e-6', '1e-7', '1e-8', '1e-9']

    fig, ax = plt.subplots(figsize=(14, 9))

    # Server Workload 데이터 (실선)
    ipc_values_server = []
    for er in available_error_rates:
        ipcs = [workload_data[wl].get(er, 0) for wl in workloads]
        valid_ipcs = [x for x in ipcs if x > 0]
        if valid_ipcs:
            avg_ipc = geometric_mean(valid_ipcs)
            ipc_values_server.append(avg_ipc)
        else:
            ipc_values_server.append(None)

    # X축 값을 실제 error rate 숫자로 변환
    x_values = [float(er.replace('e-', 'e-')) for er in available_error_rates]

    # Server Workload 그래프 (파란색 실선)
    valid_points = [(x, y) for x, y in zip(x_values, ipc_values_server) if y is not None]
    if valid_points:
        x_plot, y_plot = zip(*valid_points)
        ax.plot(x_plot, y_plot, 'o-', color='#2E86DE', linewidth=4,
               markersize=12, label=f'Server {page_size.upper()}', zorder=3)

        # 마커 위에 수치 표기
        for x, y in zip(x_plot, y_plot):
            ax.text(x, y + 0.01, f'{y:.3f}', ha='center', va='bottom',
                   fontsize=14, fontweight='bold', color='#2E86DE')

    # 4KB 데이터가 있다면 추가
    page_size_4kb = '4kb' if page_size == '2mb' else '2mb'
    has_4kb = page_size_4kb in data and capacity in data[page_size_4kb]

    if has_4kb:
        workload_data_4kb = data[page_size_4kb][capacity]
        workloads_4kb = sorted(workload_data_4kb.keys())

        ipc_values_4kb = []
        for er in available_error_rates:
            ipcs = [workload_data_4kb[wl].get(er, 0) for wl in workloads_4kb]
            valid_ipcs = [x for x in ipcs if x > 0]
            if valid_ipcs:
                avg_ipc = geometric_mean(valid_ipcs)
                ipc_values_4kb.append(avg_ipc)
            else:
                ipc_values_4kb.append(None)

        valid_points_4kb = [(x, y) for x, y in zip(x_values, ipc_values_4kb) if y is not None]
        if valid_points_4kb:
            x_plot_4kb, y_plot_4kb = zip(*valid_points_4kb)
            ax.plot(x_plot_4kb, y_plot_4kb, 'o--', color='#5F27CD', linewidth=4,
                   markersize=12, label=f'Server {page_size_4kb.upper()}', zorder=3)

            # 마커 아래에 수치 표기
            for x, y in zip(x_plot_4kb, y_plot_4kb):
                ax.text(x, y - 0.01, f'{y:.3f}', ha='center', va='top',
                       fontsize=14, fontweight='bold', color='#5F27CD')
    else:
        ipc_values_4kb = [None] * len(available_error_rates)

    ax.set_xscale('log')
    ax.set_xlabel('MTBCE', fontweight='bold', fontsize=22)
    ax.set_ylabel('Average IPC', fontweight='bold', fontsize=22)
    ax.legend(loc='best', frameon=True, fancybox=True, fontsize=20)
    ax.grid(True, alpha=0.3, linewidth=1.5, linestyle='-', color='gray')
    ax.set_facecolor('white')

    # X축 반전
    ax.invert_xaxis()

    # Y축 범위 자동 설정
    all_values = [v for v in ipc_values_server if v is not None]
    if has_4kb:
        all_values.extend([v for v in ipc_values_4kb if v is not None])

    if all_values:
        y_min = min(all_values) * 0.85
        y_max = max(all_values) * 1.15
        ax.set_ylim(y_min, y_max)

    plt.tight_layout()
    output_file = f'/home/hamoci/Study/ChampSim/{output_dir}/server_average_ipc_comparison_{page_size}_{capacity}.png'
    plt.savefig(output_file, dpi=300, bbox_inches='tight', facecolor='white', edgecolor='none')
    print(f"Server 평균 IPC 그래프 저장: {output_file}")

    # IPC 감소율 출력
    print(f"\n{'='*80}")
    print(f"Server IPC 감소율 분석 - {page_size.upper()} {capacity.upper()}")
    print(f"{'='*80}")

    if ipc_values_server[0] is not None:
        baseline_server = ipc_values_server[0]  # 1e-2
        print(f"\n[{page_size.upper()}] Baseline (1e-2): {baseline_server:.4f}")
        print(f"{'Error Rate':<15} {'IPC':<12} {'감소율 (%)':<15} {'절대 감소':<15}")
        print("-" * 60)

        for i, er in enumerate(available_error_rates):
            if ipc_values_server[i] is not None:
                ipc = ipc_values_server[i]
                decrease_pct = ((baseline_server - ipc) / baseline_server) * 100
                abs_decrease = baseline_server - ipc
                print(f"{er:<15} {ipc:<12.4f} {decrease_pct:<15.2f} {abs_decrease:<15.4f}")

    if has_4kb and ipc_values_4kb[0] is not None:
        baseline_4kb = ipc_values_4kb[0]  # 1e-2
        print(f"\n[{page_size_4kb.upper()}] Baseline (1e-2): {baseline_4kb:.4f}")
        print(f"{'Error Rate':<15} {'IPC':<12} {'감소율 (%)':<15} {'절대 감소':<15}")
        print("-" * 60)

        for i, er in enumerate(available_error_rates):
            if ipc_values_4kb[i] is not None:
                ipc = ipc_values_4kb[i]
                decrease_pct = ((baseline_4kb - ipc) / baseline_4kb) * 100
                abs_decrease = baseline_4kb - ipc
                print(f"{er:<15} {ipc:<12.4f} {decrease_pct:<15.2f} {abs_decrease:<15.4f}")

    print(f"{'='*80}\n")

    plt.close()

def create_per_benchmark_plots(data, capacity='128gb', output_dir='results'):
    """벤치마크 그룹별 비교 그래프 (각 그룹마다 별도 그래프)"""

    # 2MB와 4KB 데이터 모두 확인
    if '2mb' not in data or capacity not in data['2mb']:
        return

    workload_data_2mb = data['2mb'][capacity]

    # 4KB 데이터 확인
    has_4kb = '4kb' in data and capacity in data['4kb']
    if has_4kb:
        workload_data_4kb = data['4kb'][capacity]

    # 벤치마크 그룹별로 그룹화
    benchmarks = {}
    for workload in workload_data_2mb.keys():
        # benchbase-wikipedia -> benchbase
        # dacapo-kafka -> dacapo
        # charlie.1006518 -> charlie
        if '.' in workload:
            bench = workload.split('.')[0]
        else:
            bench = workload.rsplit('-', 1)[0] if '-' in workload else workload

        if bench not in benchmarks:
            benchmarks[bench] = []
        benchmarks[bench].append(workload)

    available_error_rates = ['1e-2', '1e-3', '1e-4', '1e-5', '1e-6', '1e-7', '1e-8', '1e-9']

    # 논문용 설정
    plt.rcParams.update({
        'font.size': 14,
        'axes.labelsize': 16,
        'axes.titlesize': 18,
        'xtick.labelsize': 14,
        'ytick.labelsize': 14,
        'legend.fontsize': 14,
        'lines.linewidth': 3,
        'lines.markersize': 8
    })

    # 각 벤치마크별로 그래프 생성
    for bench_name in sorted(benchmarks.keys()):
        fig, ax = plt.subplots(figsize=(12, 8))

        workloads = sorted(benchmarks[bench_name])

        # 색상 팔레트
        colors = plt.cm.tab10(np.linspace(0, 1, max(len(workloads), 4)))

        for idx, workload in enumerate(workloads):
            # X축 값
            x_values = [float(er.replace('e-', 'e-')) for er in available_error_rates]

            # 2MB 데이터
            ipc_values_2mb = [workload_data_2mb[workload].get(er, None) for er in available_error_rates]
            valid_2mb = [(x, y) for x, y in zip(x_values, ipc_values_2mb) if y is not None]

            # 워크로드 이름 정리
            if '.' in workload:
                workload_label = workload.split('.')[1]
            elif '-' in workload:
                workload_label = workload.split('-')[-1]
            else:
                workload_label = workload

            if valid_2mb:
                x_plot, y_plot = zip(*valid_2mb)
                ax.plot(x_plot, y_plot, 'o-', color=colors[idx], linewidth=3,
                       markersize=8, label=f'{workload_label} (2MB)', alpha=0.8)

        # 벤치마크 이름 매핑
        bench_names = {
            'benchbase': 'BenchBase',
            'dacapo': 'DaCapo',
            'renaissance': 'Renaissance',
            'nodeapp': 'Node.js App',
            'mwnginxfpm': 'MediaWiki+Nginx+FPM',
            'charlie': 'Charlie',
            'delta': 'Delta',
            'merced': 'Merced',
            'whiskey': 'Whiskey'
        }

        full_name = bench_names.get(bench_name, bench_name.upper())

        ax.set_title(f'{full_name} ({capacity.upper()})', fontweight='bold', fontsize=18)
        ax.set_xlabel('MTBCE', fontweight='bold', fontsize=16)
        ax.set_ylabel('IPC', fontweight='bold', fontsize=16)
        ax.set_xscale('log')
        ax.invert_xaxis()
        ax.grid(True, alpha=0.3, linewidth=1.2)
        ax.legend(loc='best', fontsize=12, frameon=True, ncol=2 if len(workloads) > 4 else 1)
        ax.set_facecolor('white')

        plt.tight_layout()
        output_file = f'/home/hamoci/Study/ChampSim/{output_dir}/server_{bench_name}_ipc_{capacity}.png'
        plt.savefig(output_file, dpi=300, bbox_inches='tight', facecolor='white', edgecolor='none')
        print(f"Server {bench_name.upper()} 그래프 저장: {output_file}")
        plt.close()

def create_all_benchmarks_comparison(data, page_size='2mb', capacity='128gb', output_dir='results'):
    """모든 벤치마크 그룹의 평균 IPC를 하나의 그래프에 표시"""

    if page_size not in data or capacity not in data[page_size]:
        print(f"데이터 없음: {page_size} {capacity}")
        return

    # 논문용 설정
    plt.rcParams.update({
        'font.size': 14,
        'axes.labelsize': 16,
        'axes.titlesize': 18,
        'xtick.labelsize': 14,
        'ytick.labelsize': 14,
        'legend.fontsize': 13,
        'lines.linewidth': 3,
        'lines.markersize': 8
    })

    workload_data = data[page_size][capacity]

    # 벤치마크 그룹별로 그룹화
    benchmarks = {}
    for workload in workload_data.keys():
        if '.' in workload:
            bench = workload.split('.')[0]
        else:
            bench = workload.rsplit('-', 1)[0] if '-' in workload else workload

        if bench not in benchmarks:
            benchmarks[bench] = []
        benchmarks[bench].append(workload)

    available_error_rates = ['1e-2', '1e-3', '1e-4', '1e-5', '1e-6', '1e-7', '1e-8', '1e-9']

    fig, ax = plt.subplots(figsize=(14, 9))

    # X축 값
    x_values = [float(er.replace('e-', 'e-')) for er in available_error_rates]

    # 벤치마크별 색상 및 마커
    bench_colors = {
        'benchbase': '#E74C3C',
        'dacapo': '#3498DB',
        'renaissance': '#2ECC71',
        'nodeapp': '#F39C12',
        'mwnginxfpm': '#9B59B6',
        'charlie': '#1ABC9C',
        'delta': '#E67E22',
        'merced': '#34495E',
        'whiskey': '#95A5A6'
    }

    bench_markers = {
        'benchbase': 'o',
        'dacapo': 's',
        'renaissance': '^',
        'nodeapp': 'D',
        'mwnginxfpm': 'v',
        'charlie': 'P',
        'delta': '*',
        'merced': 'X',
        'whiskey': 'h'
    }

    bench_names = {
        'benchbase': 'BenchBase',
        'dacapo': 'DaCapo',
        'renaissance': 'Renaissance',
        'nodeapp': 'NodeApp',
        'mwnginxfpm': 'MW+Nginx',
        'charlie': 'Charlie',
        'delta': 'Delta',
        'merced': 'Merced',
        'whiskey': 'Whiskey'
    }

    # 각 벤치마크의 평균 계산 및 플롯
    for bench_name in sorted(benchmarks.keys()):
        workloads = benchmarks[bench_name]

        # 각 error rate에 대한 평균 IPC 계산
        avg_ipcs = []
        for er in available_error_rates:
            ipcs = [workload_data[wl].get(er, 0) for wl in workloads]
            valid_ipcs = [x for x in ipcs if x > 0]
            if valid_ipcs:
                avg_ipc = geometric_mean(valid_ipcs)
                avg_ipcs.append(avg_ipc)
            else:
                avg_ipcs.append(None)

        # 플롯
        valid_points = [(x, y) for x, y in zip(x_values, avg_ipcs) if y is not None]
        if valid_points:
            x_plot, y_plot = zip(*valid_points)
            color = bench_colors.get(bench_name, '#000000')
            marker = bench_markers.get(bench_name, 'o')
            label = bench_names.get(bench_name, bench_name.upper())

            ax.plot(x_plot, y_plot, marker=marker, linestyle='-', color=color,
                   linewidth=3, markersize=8, label=label, zorder=3, alpha=0.85)

    ax.set_xscale('log')
    ax.set_xlabel('MTBCE', fontweight='bold', fontsize=16)
    ax.set_ylabel('Average IPC (Geometric Mean)', fontweight='bold', fontsize=16)
    ax.set_title(f'Server Workloads Average IPC - {page_size.upper()} ({capacity.upper()})',
                 fontweight='bold', fontsize=18, pad=15)
    ax.legend(loc='best', frameon=True, fancybox=True, fontsize=13, shadow=True)
    ax.grid(True, alpha=0.3, linewidth=1.2, linestyle='-', color='gray')
    ax.set_facecolor('white')

    # X축 반전
    ax.invert_xaxis()

    plt.tight_layout()
    output_file = f'/home/hamoci/Study/ChampSim/{output_dir}/server_all_benchmarks_comparison_{page_size}_{capacity}.png'
    plt.savefig(output_file, dpi=300, bbox_inches='tight', facecolor='white', edgecolor='none')
    print(f"Server 전체 벤치마크 비교 그래프 저장: {output_file}")
    plt.close()

def print_summary_table(data, page_size='2mb', capacity='128gb'):
    """결과 요약 테이블 출력"""

    if page_size not in data or capacity not in data[page_size]:
        return

    print("\n" + "="*100)
    print(f"SERVER WORKLOAD ERROR RATE COMPARISON - {page_size.upper()} Page Size, {capacity.upper()} Capacity")
    print("="*100)

    workload_data = data[page_size][capacity]
    error_rates = ['1e-2', '1e-3', '1e-4', '1e-5', '1e-6', '1e-7', '1e-8', '1e-9']

    header = f"{'Workload':<20}"
    for error_rate in error_rates:
        header += f"{error_rate:>12}"
    header += f"{'Avg IPC':>12}{'StdDev':>12}"
    print(header)
    print("-" * len(header))

    for workload in sorted(workload_data.keys()):
        row = f"{workload:<20}"

        ipc_values = []
        for error_rate in error_rates:
            ipc = workload_data[workload].get(error_rate, 0)
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

    for error_rate in error_rates:
        ipcs = [workload_data[wl].get(error_rate, 0) for wl in workload_data.keys()]
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
    results_dir = '/home/hamoci/Study/ChampSim/results'

    print("ChampSim Server Workload Error Rate 비교 결과 파싱 중...")
    data = parse_results_directory(results_dir)

    if not data:
        print("파싱된 Server 데이터가 없습니다.")
        return

    print("\n사용 가능한 Server Workload 구성:")
    for page_size in data.keys():
        for capacity in data[page_size].keys():
            num_workloads = len(data[page_size][capacity])
            print(f"  - {page_size.upper()} / {capacity.upper()}: {num_workloads} workloads")

    # 각 구성별로 그래프 생성
    for page_size in sorted(data.keys()):
        for capacity in sorted(data[page_size].keys()):
            print(f"\n{'='*80}")
            print(f"처리 중: {page_size.upper()} Page Size, {capacity.upper()} Capacity")
            print('='*80)

            # 요약 테이블
            print_summary_table(data, page_size, capacity)

            # 그래프 생성
            print(f"\n{page_size.upper()} {capacity.upper()} 그래프 생성 중...")
            create_average_comparison_plot(data, page_size, capacity)
            create_all_benchmarks_comparison(data, page_size, capacity)

    # 벤치마크별 상세 그래프
    print("\n" + "="*80)
    print("벤치마크 그룹별 상세 그래프 생성 중...")
    print("="*80)

    # 사용 가능한 모든 capacity에 대해 생성
    all_capacities = set()
    for page_size in data.keys():
        all_capacities.update(data[page_size].keys())

    for capacity in sorted(all_capacities):
        print(f"\nCapacity {capacity.upper()} 처리 중...")
        create_per_benchmark_plots(data, capacity)

    print("\n" + "="*80)
    print("완료! 모든 Server 그래프가 results 폴더에 저장되었습니다.")
    print("="*80)
    print("\n생성된 파일:")
    print("  - server_average_ipc_comparison_{pagesize}_{capacity}.png: Server 평균 IPC 비교")
    print("  - server_all_benchmarks_comparison_{pagesize}_{capacity}.png: 모든 Server 벤치마크 비교")
    print("  - server_{benchmark}_ipc_{capacity}.png: 각 벤치마크 그룹별 상세 비교")

if __name__ == "__main__":
    main()
