#!/usr/bin/env python3
"""
ChampSim 전체 워크로드 RBMPKI & IPC 분석 스크립트
SPEC, Server, GAP 3개 카테고리에 대한 메모리 집약도 분석
"""

import os
import re
import csv
import matplotlib.pyplot as plt
import numpy as np

def parse_metrics_from_file(file_path):
    """파일에서 IPC와 RBMPKI 값을 추출"""
    try:
        with open(file_path, 'r') as f:
            content = f.read()

        ipc = None
        rbmpki = None

        # IPC 추출
        match = re.search(r'Simulation (complete|finished).*?cumulative IPC:\s*([0-9.]+)', content)
        if match:
            ipc = float(match.group(2))
        else:
            matches = re.findall(r'cumulative IPC:\s*([0-9.]+)', content)
            if matches:
                ipc = float(matches[-1])

        # Instructions 수 추출
        instructions_match = re.search(r'CPU 0 cumulative IPC:.*?instructions:\s*(\d+)', content)

        if not instructions_match:
            return ipc, None

        instructions = int(instructions_match.group(1))

        # RBMPKI 계산 - DRAM Statistics 섹션에서 모든 채널의 ROW_BUFFER_MISS 합산
        rb_miss_matches = re.findall(r'^\s*ROW_BUFFER_MISS:\s*(\d+)', content, re.MULTILINE)

        if rb_miss_matches and instructions > 0:
            # 모든 채널의 Row Buffer Miss 합산 (RQ + WQ)
            total_rb_misses = sum(int(miss) for miss in rb_miss_matches)
            rbmpki = (total_rb_misses / instructions) * 1000  # Per Kilo Instructions
        else:
            rbmpki = None

        return ipc, rbmpki

    except Exception as e:
        print(f"Error parsing {file_path}: {e}")
        return None, None

def parse_category_directory(category_dir, category_name, target_error_rate='1e-7', target_capacity='64gb'):
    """카테고리별 디렉토리에서 결과 파싱"""
    data = {}

    if not os.path.exists(category_dir):
        print(f"디렉토리가 존재하지 않습니다: {category_dir}")
        return data

    for filename in os.listdir(category_dir):
        if not filename.endswith('.txt') or not filename.startswith('champsim_'):
            continue

        file_path = os.path.join(category_dir, filename)

        # 파일명 패턴 파싱
        # Server: champsim_{pagesize}_error_{capacity}_{error_rate}_{workload}.champsim.trace.gz.txt
        # GAP: champsim_{pagesize}_error_{capacity}_{error_rate}_{workload}.trace.gz.txt
        # SPEC: champsim_{pagesize}_error_{capacity}_{error_rate}_{workload}.txt

        # Server 패턴 (*.champsim.trace.gz.txt)
        pattern_server = r'champsim_(\w+)_error_(\w+)_(1e-\d+)_(.+?)\.champsim\.trace\.gz\.txt'
        # GAP 패턴 (*.trace.gz.txt)
        pattern_gap = r'champsim_(\w+)_error_(\w+)_(1e-\d+)_(.+?)\.trace\.gz\.txt'
        # SPEC 패턴 (*.txt)
        pattern_spec = r'champsim_(\w+)_error_(\w+)_(1e-\d+)_(.+?)\.txt'

        match = re.search(pattern_server, filename)
        if not match:
            match = re.search(pattern_gap, filename)
        if not match:
            match = re.search(pattern_spec, filename)

        if not match:
            continue

        page_size = match.group(1)
        capacity = match.group(2)
        error_rate = match.group(3)
        workload = match.group(4)

        # Error rate 필터링
        if error_rate != target_error_rate:
            continue

        # Capacity 필터링
        if capacity != target_capacity:
            continue

        ipc, rbmpki = parse_metrics_from_file(file_path)

        if ipc is not None:
            key = (category_name, workload, page_size)
            data[key] = {
                'category': category_name,
                'workload': workload,
                'page_size': page_size,
                'capacity': capacity,
                'error_rate': error_rate,
                'ipc': ipc,
                'rbmpki': rbmpki
            }

    return data

def save_to_csv(data, output_file):
    """데이터를 CSV 파일로 저장"""
    if not data:
        print("저장할 데이터가 없습니다.")
        return

    with open(output_file, 'w', newline='') as csvfile:
        fieldnames = ['Category', 'Workload', 'Page_Size', 'IPC', 'RBMPKI', 'Memory_Intensity']
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)

        writer.writeheader()

        # 정렬: category, workload, page_size (4KB 먼저)
        for metrics in sorted(data.values(), key=lambda x: (x['category'], x['workload'], -ord(x['page_size'][0]))):
            # RBMPKI 기준으로 메모리 집약도 분류
            if metrics['rbmpki'] is not None:
                if metrics['rbmpki'] > 10:
                    intensity = 'High'
                elif metrics['rbmpki'] > 5:
                    intensity = 'Medium'
                else:
                    intensity = 'Low'
            else:
                intensity = 'Unknown'

            writer.writerow({
                'Category': metrics['category'],
                'Workload': metrics['workload'],
                'Page_Size': metrics['page_size'].upper(),
                'IPC': f"{metrics['ipc']:.4f}" if metrics['ipc'] else 'N/A',
                'RBMPKI': f"{metrics['rbmpki']:.4f}" if metrics['rbmpki'] else 'N/A',
                'Memory_Intensity': intensity
            })

    print(f"CSV 파일 저장 완료: {output_file}")

def create_bar_chart_by_category(data, output_file):
    """카테고리별 평균 RBMPKI 비교 막대 그래프"""
    if not data:
        return

    valid_data = {k: v for k, v in data.items() if v['rbmpki'] is not None}

    if not valid_data:
        print("RBMPKI 데이터가 없어 그래프를 생성할 수 없습니다.")
        return

    # 카테고리별 평균 계산
    category_rbmpki = {}
    for metrics in valid_data.values():
        cat = metrics['category']
        if cat not in category_rbmpki:
            category_rbmpki[cat] = []
        category_rbmpki[cat].append(metrics['rbmpki'])

    categories = []
    avg_rbmpkis = []
    colors_list = []

    category_colors = {
        'SPEC': '#E74C3C',
        'Server': '#3498DB',
        'GAP': '#2ECC71'
    }

    for cat in sorted(category_rbmpki.keys()):
        categories.append(cat)
        avg_rbmpkis.append(np.mean(category_rbmpki[cat]))
        colors_list.append(category_colors.get(cat, '#000000'))

    # 그래프 생성 - 논문 스타일
    plt.rcParams.update({
        'font.size': 20,
        'font.weight': 'bold',
        'axes.labelsize': 24,
        'axes.labelweight': 'bold',
        'axes.titlesize': 26,
        'xtick.labelsize': 22,
        'ytick.labelsize': 20,
        'legend.fontsize': 18,
        'lines.linewidth': 2.5,
    })

    fig, ax = plt.subplots(figsize=(10, 6))

    x_pos = np.arange(len(categories))
    bars = ax.bar(x_pos, avg_rbmpkis, color=colors_list, alpha=0.85, edgecolor='black', linewidth=2.5, width=0.6)

    # 값 표시 - 굵고 크게
    for i, (cat, val) in enumerate(zip(categories, avg_rbmpkis)):
        ax.text(i, val + 0.3, f'{val:.2f}', ha='center', va='bottom', fontsize=20, fontweight='bold')

    ax.set_xticks(x_pos)
    ax.set_xticklabels(categories, fontweight='bold')
    ax.set_ylabel('Average RBMPKI', fontweight='bold', fontsize=24)
    ax.set_ylim(0, max(avg_rbmpkis) * 1.15)
    ax.grid(axis='y', alpha=0.35, linewidth=1.8, linestyle='--')
    ax.set_facecolor('white')
    ax.spines['top'].set_linewidth(2)
    ax.spines['right'].set_linewidth(2)
    ax.spines['bottom'].set_linewidth(2)
    ax.spines['left'].set_linewidth(2)

    plt.tight_layout()
    plt.savefig(output_file, dpi=300, bbox_inches='tight', facecolor='white', edgecolor='none')
    print(f"카테고리별 비교 그래프 저장: {output_file}")
    plt.close()

def create_combined_bar_chart_by_rbmpki(data, output_file):
    """전체 워크로드 RBMPKI 막대 그래프 (RBMPKI 높은 순) + IPC 오버랩"""
    if not data:
        return

    valid_data = {k: v for k, v in data.items() if v['rbmpki'] is not None}

    if not valid_data:
        print("RBMPKI 데이터가 없어 막대 그래프를 생성할 수 없습니다.")
        return

    # 워크로드명과 RBMPKI, IPC 값 추출
    workloads = []
    rbmpkis = []
    ipcs = []
    colors_list = []

    category_colors = {
        'SPEC': '#E74C3C',
        'Server': '#3498DB',
        'GAP': '#2ECC71'
    }

    for metrics in sorted(valid_data.values(), key=lambda x: x['rbmpki'], reverse=True):
        label = f"{metrics['category']}: {metrics['workload']} ({metrics['page_size'].upper()})"
        workloads.append(label)
        rbmpkis.append(metrics['rbmpki'])
        ipcs.append(metrics['ipc'])
        colors_list.append(category_colors.get(metrics['category'], '#000000'))

    # 그래프 생성 - 논문 스타일 (컴팩트)
    plt.rcParams.update({
        'font.size': 14,
        'font.weight': 'bold',
        'axes.labelsize': 20,
        'axes.labelweight': 'bold',
        'axes.titlesize': 22,
        'xtick.labelsize': 18,
        'ytick.labelsize': 13,
        'lines.linewidth': 2.0,
    })

    fig, ax1 = plt.subplots(figsize=(14, max(12, len(workloads) * 0.25)))

    y_pos = np.arange(len(workloads))
    ax1.barh(y_pos, rbmpkis, color=colors_list, alpha=0.85, edgecolor='black', linewidth=1.5, height=0.7)

    ax1.set_yticks(y_pos)
    ax1.set_yticklabels(workloads, fontweight='bold')
    ax1.set_xlabel('RBMPKI (Row Buffer Misses Per Kilo Instructions)', fontweight='bold', fontsize=20)
    ax1.grid(axis='x', alpha=0.35, linewidth=1.8, linestyle='--')
    ax1.set_facecolor('white')
    for spine in ax1.spines.values():
        spine.set_linewidth(2)

    # IPC를 두 번째 x축으로 오버랩
    ax2 = ax1.twiny()
    ipc_text_color = '#8B0000'  # 검붉은색 (텍스트)
    
    # IPC 축 범위를 0부터 시작하도록 설정
    max_ipc = max(ipcs) if ipcs else 1.0
    ax2.set_xlim(0, max_ipc * 1.1)  # 약간의 여유 공간
    
    # 점선으로 축과 점 연결 (0부터 시작)
    for i, (ipc, y) in enumerate(zip(ipcs, y_pos)):
        ax2.plot([0, ipc], [y, y], ':', color=ipc_text_color, linewidth=1.5, alpha=0.6, zorder=4)
    
    # 빨간 점에 검정 테두리 - 크기 증가
    ax2.plot(ipcs, y_pos, 'o', color='red', markersize=10, markeredgecolor='black', markeredgewidth=2, zorder=5)
    
    # IPC 값 표시 - 크기 증가
    for i, (ipc, y) in enumerate(zip(ipcs, y_pos)):
        ax2.text(ipc + max_ipc * 0.02, y, f'{ipc:.2f}', va='center', ha='left', fontsize=12, color=ipc_text_color, fontweight='bold')
    
    ax2.set_xlabel('IPC (Instructions Per Cycle)', fontweight='bold', fontsize=20, color=ipc_text_color)
    ax2.tick_params(axis='x', labelcolor=ipc_text_color, labelsize=18, width=2, length=6)

    plt.tight_layout()
    plt.savefig(output_file, dpi=300, bbox_inches='tight', facecolor='white', edgecolor='none')
    print(f"전체 워크로드 RBMPKI 순위 그래프 저장: {output_file}")
    plt.close()

def create_combined_bar_chart_by_name(data, output_file):
    """전체 워크로드 RBMPKI 막대 그래프 (이름순 정렬) + IPC 오버랩"""
    if not data:
        return

    valid_data = {k: v for k, v in data.items() if v['rbmpki'] is not None}

    if not valid_data:
        print("RBMPKI 데이터가 없어 막대 그래프를 생성할 수 없습니다.")
        return

    # 워크로드명과 RBMPKI, IPC 값 추출
    workloads = []
    rbmpkis = []
    ipcs = []
    colors_list = []

    category_colors = {
        'SPEC': '#E74C3C',
        'Server': '#3498DB',
        'GAP': '#2ECC71'
    }

    # 카테고리, 워크로드명, 페이지 크기 순으로 정렬 (4KB 먼저)
    for metrics in sorted(valid_data.values(), key=lambda x: (x['category'], x['workload'], -ord(x['page_size'][0]))):
        label = f"{metrics['category']}: {metrics['workload']} ({metrics['page_size'].upper()})"
        workloads.append(label)
        rbmpkis.append(metrics['rbmpki'])
        ipcs.append(metrics['ipc'])
        colors_list.append(category_colors.get(metrics['category'], '#000000'))

    # 그래프 생성 - 논문 스타일 (컴팩트)
    plt.rcParams.update({
        'font.size': 14,
        'font.weight': 'bold',
        'axes.labelsize': 20,
        'axes.labelweight': 'bold',
        'axes.titlesize': 22,
        'xtick.labelsize': 18,
        'ytick.labelsize': 13,
        'lines.linewidth': 2.0,
    })

    fig, ax1 = plt.subplots(figsize=(14, max(12, len(workloads) * 0.25)))

    y_pos = np.arange(len(workloads))
    ax1.barh(y_pos, rbmpkis, color=colors_list, alpha=0.85, edgecolor='black', linewidth=1.5, height=0.7)

    ax1.set_yticks(y_pos)
    ax1.set_yticklabels(workloads, fontweight='bold')
    ax1.set_xlabel('RBMPKI (Row Buffer Misses Per Kilo Instructions)', fontweight='bold', fontsize=20)
    ax1.grid(axis='x', alpha=0.35, linewidth=1.8, linestyle='--')
    ax1.set_facecolor('white')
    for spine in ax1.spines.values():
        spine.set_linewidth(2)

    # IPC를 두 번째 x축으로 오버랩
    ax2 = ax1.twiny()
    ipc_text_color = '#8B0000'  # 검붉은색 (텍스트)
    
    # IPC 축 범위를 0부터 시작하도록 설정
    max_ipc = max(ipcs) if ipcs else 1.0
    ax2.set_xlim(0, max_ipc * 1.1)  # 약간의 여유 공간
    
    # 점선으로 축과 점 연결 (0부터 시작)
    for i, (ipc, y) in enumerate(zip(ipcs, y_pos)):
        ax2.plot([0, ipc], [y, y], ':', color=ipc_text_color, linewidth=1.5, alpha=0.6, zorder=4)
    
    # 빨간 점에 검정 테두리 - 크기 증가
    ax2.plot(ipcs, y_pos, 'o', color='red', markersize=10, markeredgecolor='black', markeredgewidth=2, zorder=5)
    
    # IPC 값 표시 - 크기 증가
    for i, (ipc, y) in enumerate(zip(ipcs, y_pos)):
        ax2.text(ipc + max_ipc * 0.02, y, f'{ipc:.2f}', va='center', ha='left', fontsize=12, color=ipc_text_color, fontweight='bold')
    
    ax2.set_xlabel('IPC (Instructions Per Cycle)', fontweight='bold', fontsize=20, color=ipc_text_color)
    ax2.tick_params(axis='x', labelcolor=ipc_text_color, labelsize=18, width=2, length=6)

    plt.tight_layout()
    plt.savefig(output_file, dpi=300, bbox_inches='tight', facecolor='white', edgecolor='none')
    print(f"전체 워크로드 이름순 그래프 저장: {output_file}")
    plt.close()

def print_summary(data):
    """요약 통계 출력"""
    if not data:
        print("데이터가 없습니다.")
        return

    print("\n" + "="*120)
    print("ALL WORKLOADS MEMORY INTENSITY ANALYSIS (Error Rate: 1e-7, Capacity: 64GB)")
    print("="*120)
    print(f"{'Category':<10} {'Workload':<30} {'Page':<6} {'IPC':<10} {'RBMPKI':<12} {'Memory Intensity':<20}")
    print("-" * 120)

    # 카테고리별 통계
    category_stats = {}

    for metrics in sorted(data.values(), key=lambda x: (x['category'], x['workload'], -ord(x['page_size'][0]))):
        cat = metrics['category']
        ipc = metrics['ipc']
        rbmpki = metrics['rbmpki']
        workload = metrics['workload']
        page_size = metrics['page_size'].upper()

        if cat not in category_stats:
            category_stats[cat] = []

        if rbmpki is not None:
            category_stats[cat].append(rbmpki)
            if rbmpki > 10:
                intensity = 'High (Memory-Bound)'
            elif rbmpki > 5:
                intensity = 'Medium'
            else:
                intensity = 'Low (Compute-Bound)'
        else:
            intensity = 'Unknown'

        ipc_str = f"{ipc:.4f}" if ipc else 'N/A'
        rbmpki_str = f"{rbmpki:.4f}" if rbmpki else 'N/A'

        print(f"{cat:<10} {workload:<30} {page_size:<6} {ipc_str:<10} {rbmpki_str:<12} {intensity:<20}")

    # 카테고리별 요약
    print("\n" + "="*120)
    print("CATEGORY SUMMARY")
    print("="*120)

    for cat in sorted(category_stats.keys()):
        rbmpkis = category_stats[cat]
        if rbmpkis:
            print(f"\n{cat}:")
            print(f"  Total Workloads: {len([k for k in data.keys() if data[k]['category'] == cat])}")
            print(f"  Average RBMPKI: {np.mean(rbmpkis):.4f}")
            print(f"  Median RBMPKI: {np.median(rbmpkis):.4f}")
            print(f"  Min RBMPKI: {np.min(rbmpkis):.4f}")
            print(f"  Max RBMPKI: {np.max(rbmpkis):.4f}")

            high = sum(1 for x in rbmpkis if x > 10)
            medium = sum(1 for x in rbmpkis if 5 < x <= 10)
            low = sum(1 for x in rbmpkis if x <= 5)

            print(f"  High (>10): {high}, Medium (5-10): {medium}, Low (≤5): {low}")

    print("="*120 + "\n")

def main():
    """메인 함수"""
    base_dir = '/home/hamoci/Study/ChampSim/results'
    output_dir = '/home/hamoci/Study/ChampSim/results'

    # 카테고리별 디렉토리
    categories = {
        'SPEC': os.path.join(base_dir, 'SPEC'),
        'Server': os.path.join(base_dir, 'server'),
        'GAP': os.path.join(base_dir, 'gaps')
    }

    print("ChampSim 전체 워크로드 RBMPKI & IPC 분석 시작...")
    print("="*100)

    all_data = {}

    for cat_name, cat_dir in categories.items():
        print(f"\n{cat_name} 카테고리 파싱 중...")
        cat_data = parse_category_directory(cat_dir, cat_name)
        all_data.update(cat_data)
        print(f"  → {len(cat_data)}개 워크로드 파싱 완료")

    if not all_data:
        print("파싱된 데이터가 없습니다.")
        return

    print(f"\n총 {len(all_data)}개의 워크로드 데이터를 파싱했습니다.")

    # 요약 통계 출력
    print_summary(all_data)

    # CSV 파일 저장
    csv_file = os.path.join(output_dir, 'all_workloads_rbmpki_ipc.csv')
    save_to_csv(all_data, csv_file)

    # 그래프 생성
    print("\n그래프 생성 중...")

    # 카테고리별 평균 비교
    cat_comparison_file = os.path.join(output_dir, 'rbmpki_category_comparison.png')
    create_bar_chart_by_category(all_data, cat_comparison_file)

    # 전체 워크로드 순위 (RBMPKI 순)
    all_ranking_file = os.path.join(output_dir, 'rbmpki_all_ranking.png')
    create_combined_bar_chart_by_rbmpki(all_data, all_ranking_file)

    # 전체 워크로드 (이름순)
    all_by_name_file = os.path.join(output_dir, 'rbmpki_all_by_name.png')
    create_combined_bar_chart_by_name(all_data, all_by_name_file)

    print("\n" + "="*100)
    print("분석 완료!")
    print("="*100)
    print("\n생성된 파일:")
    print(f"  - {csv_file}: 전체 워크로드 RBMPKI 및 IPC 데이터 CSV")
    print(f"  - {cat_comparison_file}: 카테고리별 평균 RBMPKI 비교 그래프")
    print(f"  - {all_ranking_file}: 전체 워크로드 RBMPKI 순위 그래프")
    print(f"  - {all_by_name_file}: 전체 워크로드 이름순 그래프")
    print("\n메모리 집약적 워크로드 분류 기준:")
    print("  - High (Memory-Bound): RBMPKI > 10")
    print("  - Medium: 5 < RBMPKI ≤ 10")
    print("  - Low (Compute-Bound): RBMPKI ≤ 5")

if __name__ == "__main__":
    main()
