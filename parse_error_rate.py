#!/usr/bin/env python3
"""
ChampSim Error Rate별 IPC 비교 스크립트 (논문 스타일)
동일 Capacity에서 1e-2 ~ 1e-6 까지의 Error Rate별 IPC 비교
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
    
    for filename in os.listdir(results_dir):
        if not filename.endswith('.txt') or not filename.startswith('champsim_'):
            continue
            
        file_path = os.path.join(results_dir, filename)
        
        # 파일명 파싱: champsim_{pagesize}_error_{capacity}_{error_rate}_{workload}.txt
        pattern = r'champsim_(\w+)_error_(\w+)_(1e-\d+)_(\d+\.\w+.*?)\.txt'
        match = re.search(pattern, filename)
        
        if match:
            page_size = match.group(1)
            capacity = match.group(2)
            error_rate = match.group(3)
            workload_full = match.group(4)
            
            # 워크로드명 정리
            workload_match = re.match(r'(\d+)\.([^-]+)', workload_full)
            if workload_match:
                workload = f"{workload_match.group(1)}.{workload_match.group(2)}"
                
                ipc = parse_ipc_from_file(file_path)
                if ipc is not None:
                    data[page_size][capacity][workload][error_rate] = ipc
    
    return data

def create_average_comparison_plot(data, page_size='4kb', capacity='128gb', output_dir='results'):
    """Average IPC 비교 그래프 생성 (첫 번째 이미지 스타일)"""
    
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
    
    # SPEC 4KB (실선) - 실제로는 사용 가능한 데이터
    ipc_values_4kb = []
    for er in available_error_rates:
        ipcs = [workload_data[wl].get(er, 0) for wl in workloads]
        valid_ipcs = [x for x in ipcs if x > 0]
        if valid_ipcs:
            avg_ipc = geometric_mean(valid_ipcs)
            ipc_values_4kb.append(avg_ipc)
        else:
            ipc_values_4kb.append(None)
    
    # X축 값을 실제 error rate 숫자로 변환
    x_values = [float(er.replace('e-', 'e-')) for er in available_error_rates]
    
    # 4KB 그래프 (파란색 실선)
    valid_points = [(x, y) for x, y in zip(x_values, ipc_values_4kb) if y is not None]
    if valid_points:
        x_plot, y_plot = zip(*valid_points)
        ax.plot(x_plot, y_plot, 'o-', color='#2E86DE', linewidth=4, 
               markersize=12, label=f'SPEC {page_size.upper()}', zorder=3)
        
        # 4KB 마커 위에 수치 표기
        for x, y in zip(x_plot, y_plot):
            ax.text(x, y + 0.03, f'{y:.3f}', ha='center', va='bottom', 
                   fontsize=14, fontweight='bold', color='#2E86DE')
    
    # 2MB 데이터가 있다면 추가
    page_size_2mb = '2mb' if page_size == '4kb' else '4kb'
    has_2mb = page_size_2mb in data and capacity in data[page_size_2mb]
    
    if has_2mb:
        workload_data_2mb = data[page_size_2mb][capacity]
        workloads_2mb = sorted(workload_data_2mb.keys())
        
        ipc_values_2mb = []
        for er in available_error_rates:
            ipcs = [workload_data_2mb[wl].get(er, 0) for wl in workloads_2mb]
            valid_ipcs = [x for x in ipcs if x > 0]
            if valid_ipcs:
                avg_ipc = geometric_mean(valid_ipcs)
                ipc_values_2mb.append(avg_ipc)
            else:
                ipc_values_2mb.append(None)
        
        valid_points_2mb = [(x, y) for x, y in zip(x_values, ipc_values_2mb) if y is not None]
        if valid_points_2mb:
            x_plot_2mb, y_plot_2mb = zip(*valid_points_2mb)
            ax.plot(x_plot_2mb, y_plot_2mb, 'o--', color='#5F27CD', linewidth=4,
                   markersize=12, label=f'SPEC {page_size_2mb.upper()}', zorder=3)
            
            # 2MB 마커 아래에 수치 표기
            for x, y in zip(x_plot_2mb, y_plot_2mb):
                ax.text(x, y - 0.03, f'{y:.3f}', ha='center', va='top', 
                       fontsize=14, fontweight='bold', color='#5F27CD')
    else:
        ipc_values_2mb = [None] * len(available_error_rates)
    
    ax.set_xscale('log')
    ax.set_xlabel('MTBCE', fontweight='bold', fontsize=22)
    ax.set_ylabel('Average IPC', fontweight='bold', fontsize=22)
    ax.legend(loc='best', frameon=True, fancybox=True, fontsize=20)
    ax.grid(True, alpha=0.3, linewidth=1.5, linestyle='-', color='gray')
    ax.set_facecolor('white')
    
    # X축 반전
    ax.invert_xaxis()
    
    # Y축 범위 설정
    ax.set_ylim(0, 1.3)
    
    plt.tight_layout()
    output_file = f'/home/hamoci/Study/ChampSim/{output_dir}/average_ipc_comparison_{page_size}_{capacity}.png'
    plt.savefig(output_file, dpi=300, bbox_inches='tight', facecolor='white', edgecolor='none')
    print(f"평균 IPC 그래프 저장: {output_file}")
    
    # IPC 감소율 출력
    print(f"\n{'='*80}")
    print(f"IPC 감소율 분석 - {page_size.upper()} {capacity.upper()}")
    print(f"{'='*80}")
    
    if ipc_values_4kb[0] is not None:
        baseline_4kb = ipc_values_4kb[0]  # 1e-2
        print(f"\n[{page_size.upper()}] Baseline (1e-2): {baseline_4kb:.4f}")
        print(f"{'Error Rate':<15} {'IPC':<12} {'감소율 (%)':<15} {'절대 감소':<15}")
        print("-" * 60)
        
        for i, er in enumerate(available_error_rates):
            if ipc_values_4kb[i] is not None:
                ipc = ipc_values_4kb[i]
                decrease_pct = ((baseline_4kb - ipc) / baseline_4kb) * 100
                abs_decrease = baseline_4kb - ipc
                print(f"{er:<15} {ipc:<12.4f} {decrease_pct:<15.2f} {abs_decrease:<15.4f}")
    
    if has_2mb and ipc_values_2mb[0] is not None:
        baseline_2mb = ipc_values_2mb[0]  # 1e-2
        print(f"\n[{page_size_2mb.upper()}] Baseline (1e-2): {baseline_2mb:.4f}")
        print(f"{'Error Rate':<15} {'IPC':<12} {'감소율 (%)':<15} {'절대 감소':<15}")
        print("-" * 60)
        
        for i, er in enumerate(available_error_rates):
            if ipc_values_2mb[i] is not None:
                ipc = ipc_values_2mb[i]
                decrease_pct = ((baseline_2mb - ipc) / baseline_2mb) * 100
                abs_decrease = baseline_2mb - ipc
                print(f"{er:<15} {ipc:<12.4f} {decrease_pct:<15.2f} {abs_decrease:<15.4f}")
    
    print(f"{'='*80}\n")
    
    plt.close()

def create_individual_workload_plots(data, capacity='128gb', output_dir='results'):
    """개별 워크로드 비교 - 모든 워크로드 표시 (4KB vs 2MB)"""
    
    # 4KB와 2MB 데이터 모두 확인
    if '4kb' not in data or capacity not in data['4kb']:
        return
    if '2mb' not in data or capacity not in data['2mb']:
        return
    
    workload_data_4kb = data['4kb'][capacity]
    workload_data_2mb = data['2mb'][capacity]
    
    # 공통 워크로드 찾기
    workloads_4kb = set(workload_data_4kb.keys())
    workloads_2mb = set(workload_data_2mb.keys())
    workloads = sorted(workloads_4kb.intersection(workloads_2mb))
    
    if not workloads:
        return
    
    available_error_rates = ['1e-2', '1e-3', '1e-4', '1e-5', '1e-6', '1e-7', '1e-8', '1e-9']
    
    # 논문용 설정
    plt.rcParams.update({
        'font.size': 11,
        'axes.labelsize': 12,
        'axes.titlesize': 13,
        'xtick.labelsize': 10,
        'ytick.labelsize': 11,
        'legend.fontsize': 11,
        'lines.linewidth': 2,
        'lines.markersize': 6
    })
    
    # 모든 워크로드 사용
    plot_workloads = workloads
    num_workloads = len(plot_workloads)
    
    # 레이아웃 계산 (한 줄에 최대 5개)
    cols = 5
    rows = (num_workloads + cols - 1) // cols
    
    fig, axes = plt.subplots(rows, cols, figsize=(15, 3 * rows))
    if rows == 1:
        axes = axes.reshape(1, -1)
    axes = axes.flatten()
    
    for idx, workload in enumerate(plot_workloads):
        ax = axes[idx]
        
        # X축 값
        x_values = [float(er.replace('e-', 'e-')) for er in available_error_rates]
        
        # 4KB 데이터
        ipc_values_4kb = [workload_data_4kb[workload].get(er, None) for er in available_error_rates]
        valid_4kb = [(x, y) for x, y in zip(x_values, ipc_values_4kb) if y is not None]
        
        if valid_4kb:
            x_plot, y_plot = zip(*valid_4kb)
            ax.plot(x_plot, y_plot, 'o-', color='#2E86DE', linewidth=2,
                   markersize=6, label='4KB')
        
        # 2MB 데이터
        ipc_values_2mb = [workload_data_2mb[workload].get(er, None) for er in available_error_rates]
        valid_2mb = [(x, y) for x, y in zip(x_values, ipc_values_2mb) if y is not None]
        
        if valid_2mb:
            x_plot_2mb, y_plot_2mb = zip(*valid_2mb)
            ax.plot(x_plot_2mb, y_plot_2mb, 'o-', color='#EE5A6F', linewidth=2,
                   markersize=6, label='2MB')
        
        # 워크로드 이름 정리
        workload_name = workload.split('.')[1] if '.' in workload else workload
        ax.set_title(f'{workload_name}', fontweight='bold', fontsize=13)
        ax.set_xlabel('MTBCE', fontweight='bold', fontsize=11)
        ax.set_ylabel('IPC', fontweight='bold', fontsize=11)
        ax.set_xscale('log')
        ax.invert_xaxis()
        ax.grid(True, alpha=0.3, linewidth=0.8)
        ax.legend(loc='best', fontsize=10, frameon=True)
        
        # X축 레이블 회전
        ax.tick_params(axis='x', rotation=45)
    
    # 빈 서브플롯 숨기기
    for idx in range(len(plot_workloads), len(axes)):
        axes[idx].set_visible(False)
    
    # 전체 제목
    fig.suptitle(f'Supplementary: SPEC IPC - 4KB vs 2MB ({capacity.upper()})', 
                 fontsize=16, fontweight='bold', y=0.998)
    
    plt.tight_layout(rect=[0, 0, 1, 0.99])
    output_file = f'/home/hamoci/Study/ChampSim/{output_dir}/supplementary_spec_ipc_{capacity}.png'
    plt.savefig(output_file, dpi=300, bbox_inches='tight', facecolor='white', edgecolor='none')
    print(f"개별 워크로드 그래프 저장: {output_file}")
    plt.close()

def create_gmean_comparison_plot(data, page_size='4kb', capacity='128gb', output_dir='results'):
    """전체 워크로드 평균 IPC 비교 그래프 (Geometric Mean)"""
    
    if page_size not in data or capacity not in data[page_size]:
        print(f"데이터 없음: {page_size} {capacity}")
        return
    
    # 논문용 설정
    plt.rcParams.update({
        'font.size': 14,
        'axes.labelsize': 16,
        'axes.titlesize': 18,
        'xtick.labelsize': 13,
        'ytick.labelsize': 14,
        'legend.fontsize': 14,
        'lines.linewidth': 3,
        'lines.markersize': 10
    })
    
    workload_data = data[page_size][capacity]
    workloads = sorted(workload_data.keys())
    available_error_rates = ['1e-2', '1e-3', '1e-4', '1e-5', '1e-6', '1e-7', '1e-8', '1e-9']
    
    # 2MB 데이터 확인
    page_size_2mb = '2mb' if page_size == '4kb' else '4kb'
    has_2mb = page_size_2mb in data and capacity in data[page_size_2mb]
    
    fig, ax = plt.subplots(figsize=(12, 7))
    
    # X축 값
    x_values = [float(er.replace('e-', 'e-')) for er in available_error_rates]
    
    # 4KB 평균 IPC (Geometric Mean)
    gmean_4kb = []
    for er in available_error_rates:
        ipcs = [workload_data[wl].get(er, 0) for wl in workloads]
        valid_ipcs = [x for x in ipcs if x > 0]
        if valid_ipcs:
            gmean = geometric_mean(valid_ipcs)
            gmean_4kb.append(gmean)
        else:
            gmean_4kb.append(None)
    
    # 4KB 그래프
    valid_points = [(x, y) for x, y in zip(x_values, gmean_4kb) if y is not None]
    if valid_points:
        x_plot, y_plot = zip(*valid_points)
        ax.plot(x_plot, y_plot, 'o-', color='#2E86DE', linewidth=3, 
               markersize=10, label=f'{page_size.upper()}', zorder=3)
        
        # 값 표시
        for x, y in zip(x_plot, y_plot):
            ax.text(x, y + 0.03, f'{y:.3f}', ha='center', va='bottom', 
                   fontsize=11, fontweight='bold', color='#2E86DE')
    
    # 2MB 평균 IPC
    if has_2mb:
        workload_data_2mb = data[page_size_2mb][capacity]
        workloads_2mb = sorted(workload_data_2mb.keys())
        
        gmean_2mb = []
        for er in available_error_rates:
            ipcs = [workload_data_2mb[wl].get(er, 0) for wl in workloads_2mb]
            valid_ipcs = [x for x in ipcs if x > 0]
            if valid_ipcs:
                gmean = geometric_mean(valid_ipcs)
                gmean_2mb.append(gmean)
            else:
                gmean_2mb.append(None)
        
        valid_points_2mb = [(x, y) for x, y in zip(x_values, gmean_2mb) if y is not None]
        if valid_points_2mb:
            x_plot_2mb, y_plot_2mb = zip(*valid_points_2mb)
            ax.plot(x_plot_2mb, y_plot_2mb, 's-', color='#EE5A6F', linewidth=3,
                   markersize=10, label=f'{page_size_2mb.upper()}', zorder=3)
            
            # 값 표시
            for x, y in zip(x_plot_2mb, y_plot_2mb):
                ax.text(x, y - 0.04, f'{y:.3f}', ha='center', va='top', 
                       fontsize=11, fontweight='bold', color='#EE5A6F')
    
    ax.set_xscale('log')
    ax.set_xlabel('MTBCE', fontweight='bold', fontsize=16)
    ax.set_ylabel('Average IPC (Geometric Mean)', fontweight='bold', fontsize=16)
    ax.set_title(f'Average IPC Across All Workloads - {capacity.upper()} Capacity', 
                 fontweight='bold', fontsize=18, pad=15)
    ax.legend(loc='best', frameon=True, fancybox=True, fontsize=15, shadow=True)
    ax.grid(True, alpha=0.3, linewidth=1, linestyle='-', color='gray')
    ax.set_facecolor('white')
    
    # X축 반전
    ax.invert_xaxis()
    
    # Y축 범위 설정
    all_values = [v for v in gmean_4kb if v is not None]
    if has_2mb:
        all_values.extend([v for v in gmean_2mb if v is not None])
    
    if all_values:
        y_min = min(all_values) * 0.9
        y_max = max(all_values) * 1.1
        ax.set_ylim(y_min, y_max)
    
    plt.tight_layout()
    output_file = f'/home/hamoci/Study/ChampSim/{output_dir}/gmean_ipc_comparison_{page_size}_{capacity}.png'
    plt.savefig(output_file, dpi=300, bbox_inches='tight', facecolor='white', edgecolor='none')
    print(f"전체 평균 IPC 그래프 저장: {output_file}")
    plt.close()

def print_summary_table(data, page_size='4kb', capacity='128gb'):
    """결과 요약 테이블 출력"""
    
    if page_size not in data or capacity not in data[page_size]:
        return
    
    print("\n" + "="*100)
    print(f"ERROR RATE COMPARISON SUMMARY - {page_size.upper()} Page Size, {capacity.upper()} Capacity")
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
    
    print("ChampSim Error Rate 비교 결과 파싱 중...")
    data = parse_results_directory(results_dir)
    
    if not data:
        print("파싱된 데이터가 없습니다.")
        return
    
    print("\n사용 가능한 구성:")
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
            
            # 논문 스타일 그래프 생성
            print(f"\n{page_size.upper()} {capacity.upper()} 그래프 생성 중...")
            create_average_comparison_plot(data, page_size, capacity)
            create_gmean_comparison_plot(data, page_size, capacity)
    
    # Supplementary 그래프는 capacity별로 한 번만 생성 (4KB vs 2MB 비교)
    print("\n" + "="*80)
    print("Supplementary 그래프 생성 중 (4KB vs 2MB 비교)...")
    print("="*80)
    
    # 사용 가능한 모든 capacity에 대해 생성
    all_capacities = set()
    for page_size in data.keys():
        all_capacities.update(data[page_size].keys())
    
    for capacity in sorted(all_capacities):
        print(f"\nCapacity {capacity.upper()} 처리 중...")
        create_individual_workload_plots(data, capacity)
    
    print("\n" + "="*80)
    print("완료! 모든 그래프가 results 폴더에 저장되었습니다.")
    print("="*80)
    print("\n생성된 파일:")
    print("  - average_ipc_comparison_{pagesize}_{capacity}.png: 평균 IPC 비교 (6개)")
    print("  - gmean_ipc_comparison_{pagesize}_{capacity}.png: 전체 워크로드 평균 IPC (6개)")
    print("  - supplementary_spec_ipc_{capacity}.png: 모든 워크로드 상세 비교 4KB vs 2MB (3개)")

if __name__ == "__main__":
    main()
