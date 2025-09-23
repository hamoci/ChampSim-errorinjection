#!/usr/bin/env python3
"""
ChampSim 시뮬레이션 결과 파싱 및 그래프 생성 스크립트
4KB, 4KB Error, 2MB, 2MB Error 설정에 대한 각 워크로드별 IPC 비교
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
            
        # "Simulation complete" 라인에서 최종 IPC 찾기
        match = re.search(r'Simulation complete.*?cumulative IPC:\s*([0-9.]+)', content)
        if match:
            return float(match.group(1))
        
        # 만약 찾지 못했다면, 마지막 cumulative IPC 찾기
        matches = re.findall(r'cumulative IPC:\s*([0-9.]+)', content)
        if matches:
            return float(matches[-1])
            
    except Exception as e:
        print(f"Error parsing {file_path}: {e}")
        
    return None

def parse_results_directory(results_dir):
    """결과 디렉토리에서 모든 결과 파싱"""
    data = defaultdict(lambda: defaultdict(dict))
    
    # 파일 패턴: champsim_{config}_{workload}.txt
    # config: 4kb, 4kb_error, 2mb, 2mb_error
    
    for filename in os.listdir(results_dir):
        if not filename.endswith('.txt'):
            continue
            
        file_path = os.path.join(results_dir, filename)
        
        # 파일명 파싱
        if filename.startswith('champsim_'):
            parts = filename.replace('champsim_', '').replace('.txt', '').split('_')
            
            # 설정 및 워크로드 추출
            if len(parts) >= 3:
                if 'error' in filename:
                    if '4kb_error' in filename:
                        config = '4KB Error'
                        workload_part = filename.split('4kb_error_')[1].replace('.txt', '')
                    elif '2mb_error' in filename:
                        config = '2MB Error'  
                        workload_part = filename.split('2mb_error_')[1].replace('.txt', '')
                    else:
                        continue
                else:
                    if filename.startswith('champsim_4kb_'):
                        config = '4KB'
                        workload_part = filename.split('4kb_')[1].replace('.txt', '')
                    elif filename.startswith('champsim_2mb_'):
                        config = '2MB'
                        workload_part = filename.split('2mb_')[1].replace('.txt', '')
                    else:
                        continue
                
                # 워크로드명 추출 (숫자.이름 형태)
                workload_match = re.match(r'(\d+)\.([^-]+)', workload_part)
                if workload_match:
                    workload_num = workload_match.group(1)
                    workload_name = workload_match.group(2)
                    workload = f"{workload_num}.{workload_name}"
                    
                    # IPC 값 추출
                    ipc = parse_ipc_from_file(file_path)
                    if ipc is not None:
                        data[workload][config] = ipc
                        print(f"Parsed {filename}: {workload} -> {config} = {ipc}")
    
    return data

def create_comparison_plots(data):
    """비교 그래프 생성"""
    # 논문용 폰트 크기 설정 - 더 큰 글자
    plt.rcParams.update({
        'font.size': 20,
        'axes.titlesize': 24,
        'axes.labelsize': 22,
        'xtick.labelsize': 18,
        'ytick.labelsize': 18,
        'legend.fontsize': 18,
        'figure.titlesize': 26,
        'font.weight': 'bold'
    })
    
    # 워크로드별로 정렬
    workloads = sorted(data.keys())
    configs = ['4KB', '4KB Error', '2MB', '2MB Error']
    colors = ['#648FFF', '#785EF0', '#DC267F', '#FE6100']
    
    # 더 컴팩트한 그래프 크기
    plt.figure(figsize=(10, 7))
    
    # 서브플롯 1: 모든 워크로드 비교 (위로 이동)
    plt.subplot(2, 1, 1)
    
    x = np.arange(len(workloads))
    width = 0.18  # 바 폭 축소
    
    for i, config in enumerate(configs):
        ipc_values = []
        
        for workload in workloads:
            ipc = data[workload].get(config, 0)
            ipc_values.append(ipc)
        
        plt.bar(x + i * width, ipc_values, width, label=config, color=colors[i], alpha=0.8)
    
    plt.xlabel('Workloads', fontweight='bold', fontsize=22)
    plt.ylabel('IPC', fontweight='bold', fontsize=22)
    plt.xticks(x + width * 1.5, workloads, rotation=45, ha='right', fontsize=16)
    plt.legend(ncol=2, loc='upper right', frameon=True, fancybox=True, shadow=True, fontsize=16)
    plt.grid(True, alpha=0.3, linewidth=1.5)
    
    # 서브플롯 2: Error Impact 분석 (아래로 이동)
    plt.subplot(2, 1, 2)
    
    # 4KB vs 4KB Error, 2MB vs 2MB Error 비교
    impact_4kb = []
    impact_2mb = []
    workloads_with_data = []
    
    for workload in workloads:
        if '4KB' in data[workload] and '4KB Error' in data[workload]:
            baseline = data[workload]['4KB']
            error = data[workload]['4KB Error']
            if baseline > 0:
                impact_4kb.append(abs((error - baseline) / baseline * 100))  # 절댓값 적용
                if workload not in workloads_with_data:
                    workloads_with_data.append(workload)
            else:
                impact_4kb.append(0)
        else:
            impact_4kb.append(0)
            
        if '2MB' in data[workload] and '2MB Error' in data[workload]:
            baseline = data[workload]['2MB']
            error = data[workload]['2MB Error']
            if baseline > 0:
                impact_2mb.append(abs((error - baseline) / baseline * 100))  # 절댓값 적용
            else:
                impact_2mb.append(0)
        else:
            impact_2mb.append(0)
    
    x = np.arange(len(workloads))
    width = 0.3  # 바 폭 축소
    
    plt.bar(x - width/2, impact_4kb, width, label='4KB Error Impact', color='#FE6100', alpha=0.8)
    plt.bar(x + width/2, impact_2mb, width, label='2MB Error Impact', color='#FFB000', alpha=0.8)
    
    # Impact GMEAN 계산 및 표시 (범례에서 제거, 점선 아래에 텍스트로 표시)
    valid_impact_4kb = [x for x in impact_4kb if x != 0]
    valid_impact_2mb = [x for x in impact_2mb if x != 0]
    
    if valid_impact_4kb:
        abs_values = [x for x in valid_impact_4kb if x > 0]
        if abs_values:
            gmean_4kb = geometric_mean(abs_values)
            plt.axhline(y=gmean_4kb, color='red', linestyle='--', alpha=0.8, linewidth=2)
            # 점선의 맨 왼쪽에 텍스트 표시 
            plt.text(-0.7, gmean_4kb+0.8, f'4KB: {gmean_4kb:.1f}%', 
                    color='red', fontweight='bold', ha='left', fontsize=14)
    
    if valid_impact_2mb:
        abs_values = [x for x in valid_impact_2mb if x > 0]
        if abs_values:
            gmean_2mb = geometric_mean(abs_values)
            plt.axhline(y=gmean_2mb, color='darkred', linestyle='--', alpha=0.8, linewidth=2)
            # 점선의 맨 왼쪽에 텍스트 표시 
            plt.text(-0.7, gmean_2mb+0.8, f'2MB: {gmean_2mb:.1f}%', 
                    color='darkred', fontweight='bold', ha='left', fontsize=14)
    
    plt.xlabel('Workloads', fontweight='bold', fontsize=22)
    plt.ylabel('Performance Impact (%)', fontweight='bold', fontsize=22)
    plt.xticks(x, workloads, rotation=45, ha='right', fontsize=16)
    plt.legend(loc='upper right', frameon=True, fancybox=True, shadow=True, fontsize=16)
    plt.grid(True, alpha=0.3, linewidth=1.5)
    
    plt.tight_layout(pad=2.5)
    plt.savefig('/home/hamoci/Study/ChampSim/results/performance_comparison.png', 
                dpi=300, bbox_inches='tight', facecolor='white', edgecolor='none')
    plt.show()
    
    # 개별 워크로드별 상세 그래프 (논문용으로 축소)
    fig, axes = plt.subplots(2, 5, figsize=(14, 7))
    axes = axes.flatten()
    
    for idx, workload in enumerate(workloads[:10]):  # 최대 10개 워크로드
        if idx < len(axes):
            ax = axes[idx]
            
            configs_present = []
            ipc_values = []
            colors_present = []
            
            for i, config in enumerate(configs):
                if config in data[workload]:
                    configs_present.append(config)
                    ipc_values.append(data[workload][config])
                    colors_present.append(colors[i])
            
            if ipc_values:
                bars = ax.bar(configs_present, ipc_values, color=colors_present, alpha=0.8, width=0.6)
                ax.set_title(f'{workload}', fontsize=16, fontweight='bold')
                ax.set_ylabel('IPC', fontsize=14, fontweight='bold')
                ax.grid(True, alpha=0.3, linewidth=1.2)
                ax.tick_params(axis='x', rotation=45, labelsize=12)
                ax.tick_params(axis='y', labelsize=12)
                
                # 값 표시 (더 큰 폰트)
                for bar, value in zip(bars, ipc_values):
                    ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.02,
                           f'{value:.2f}', ha='center', va='bottom', fontsize=12, fontweight='bold')
    
    # 빈 서브플롯 숨기기
    for idx in range(len(workloads), len(axes)):
        axes[idx].set_visible(False)
    
    plt.tight_layout(pad=2.5)
    plt.savefig('/home/hamoci/Study/ChampSim/results/detailed_comparison.png', 
                dpi=300, bbox_inches='tight', facecolor='white', edgecolor='none')
    plt.show()

def print_summary_table(data):
    """결과 요약 테이블 출력"""
    print("\n" + "="*80)
    print("CHAMPSIM PERFORMANCE SUMMARY")
    print("="*80)
    
    configs = ['4KB', '4KB Error', '2MB', '2MB Error']
    
    # 헤더 출력
    header = f"{'Workload':<20}"
    for config in configs:
        header += f"{config:>12}"
    header += f"{'4KB Impact':>12}{'2MB Impact':>12}"
    print(header)
    print("-" * len(header))
    
    # 각 워크로드별 데이터 출력
    for workload in sorted(data.keys()):
        row = f"{workload:<20}"
        
        # 각 설정별 IPC 값
        ipc_values = {}
        for config in configs:
            ipc = data[workload].get(config, 0)
            ipc_values[config] = ipc
            row += f"{ipc:>12.4f}" if ipc > 0 else f"{'N/A':>12}"
        
        # Impact 계산
        impact_4kb = 0
        impact_2mb = 0
        
        if ipc_values['4KB'] > 0 and ipc_values['4KB Error'] > 0:
            impact_4kb = (ipc_values['4KB Error'] - ipc_values['4KB']) / ipc_values['4KB'] * 100
            
        if ipc_values['2MB'] > 0 and ipc_values['2MB Error'] > 0:
            impact_2mb = (ipc_values['2MB Error'] - ipc_values['2MB']) / ipc_values['2MB'] * 100
        
        row += f"{impact_4kb:>11.2f}%" if impact_4kb != 0 else f"{'N/A':>12}"
        row += f"{impact_2mb:>11.2f}%" if impact_2mb != 0 else f"{'N/A':>12}"
        
        print(row)

def main():
    """메인 함수"""
    results_dir = '/home/hamoci/Study/ChampSim/results'
    
    print("ChampSim 결과 파싱 중...")
    data = parse_results_directory(results_dir)
    
    if not data:
        print("파싱된 데이터가 없습니다. 파일명 패턴을 확인해주세요.")
        return
    
    print(f"\n총 {len(data)}개 워크로드의 데이터를 파싱했습니다.")
    
    # 요약 테이블 출력
    print_summary_table(data)
    
    # 그래프 생성
    print("\n그래프 생성 중...")
    create_comparison_plots(data)
    
    print("\n완료! 그래프가 results 폴더에 저장되었습니다.")
    print("- performance_comparison.png: 전체 비교 및 에러 영향")
    print("- detailed_comparison.png: 워크로드별 상세 비교")

if __name__ == "__main__":
    main()
