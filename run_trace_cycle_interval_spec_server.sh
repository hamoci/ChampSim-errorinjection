#!/bin/bash

# ChampSim 디렉토리로 이동
cd /home/hamoci/Study/ChampSim/

# 결과 디렉토리 생성
mkdir -p results

# 바이너리 파일 목록
binaries=(
    # 2MB Page - LLC Size Reduction
    "champsim_1.5mb_2mb_32gb"
    "champsim_1mb_2mb_32gb"
    "champsim_512kb_2mb_32gb"
    "champsim_256kb_2mb_32gb"

    # 2MB Page - Way Reservation
    "champsim_2mb_15ways_2mb_32gb"
    "champsim_2mb_14ways_2mb_32gb"
    "champsim_2mb_13ways_2mb_32gb"
    "champsim_2mb_12ways_2mb_32gb"
    "champsim_2mb_11ways_2mb_32gb"
    "champsim_2mb_10ways_2mb_32gb"
    "champsim_2mb_9ways_2mb_32gb"
    "champsim_2mb_8ways_2mb_32gb"

    # 4KB Page - LLC Size Reduction
    "champsim_1.5mb_4kb_32gb"
    "champsim_1mb_4kb_32gb"
    "champsim_512kb_4kb_32gb"
    "champsim_256kb_4kb_32gb"

    # 4KB Page - Way Reservation
    "champsim_2mb_15ways_4kb_32gb"
    "champsim_2mb_14ways_4kb_32gb"
    "champsim_2mb_13ways_4kb_32gb"
    "champsim_2mb_12ways_4kb_32gb"
    "champsim_2mb_11ways_4kb_32gb"
    "champsim_2mb_10ways_4kb_32gb"
    "champsim_2mb_9ways_4kb_32gb"
    "champsim_2mb_8ways_4kb_32gb"
)

# 트레이스 파일 목록 (test_traces 폴더 기준)
traces=(
    "602.gcc_s-1850B.champsimtrace.xz"
    "603.bwaves_s-2931B.champsimtrace.xz"
    "605.mcf_s-994B.champsimtrace.xz"
    "607.cactuBSSN_s-2421B.champsimtrace.xz"
    "620.omnetpp_s-141B.champsimtrace.xz"
    "621.wrf_s-6673B.champsimtrace.xz"
    "623.xalancbmk_s-592B.champsimtrace.xz"
    "628.pop2_s-17B.champsimtrace.xz"
    "649.fotonik3d_s-10881B.champsimtrace.xz"
    "654.roms_s-1007B.champsimtrace.xz"
    "benchbase-tpcc.champsim.trace.gz"
    "benchbase-twitter.champsim.trace.gz"
    "benchbase-wikipedia.champsim.trace.gz"
    "charlie.1006518.champsim.trace.gz"
    "dacapo-kafka.champsim.trace.gz"
    "dacapo-spring.champsim.trace.gz"
    "dacapo-tomcat.champsim.trace.gz"
    "delta.507252.champsim.trace.gz"
    "merced.467915.champsim.trace.gz"
    "mwnginxfpm-wiki.champsim.trace.gz"
    "nodeapp-nodeapp.champsim.trace.gz"
    "nodeapp-nodeapp-small.champsim.trace.gz"
    "renaissance-finagle-chirper.champsim.trace.gz"
    "renaissance-finagle-http.champsim.trace.gz"
    "whiskey.426708.champsim.trace.gz"
)

# 최대 병렬 프로세스 수
MAX_PARALLEL=42

# 현재 실행 중인 작업 수를 추적하기 위한 변수
running_jobs=0

# 작업 완료를 기다리는 함수
wait_for_job_slot() {
    while [ $running_jobs -ge $MAX_PARALLEL ]; do
        sleep 1
        # 완료된 작업 수 확인
        running_jobs=$(jobs -r | wc -l)
    done
}

echo "시뮬레이션 시작: $(date)"
echo "총 ${#binaries[@]} 바이너리 × ${#traces[@]} 트레이스 = $((${#binaries[@]} * ${#traces[@]})) 개의 시뮬레이션"
echo "최대 병렬 프로세스: $MAX_PARALLEL"
echo "================================"

# 모든 바이너리와 트레이스 조합으로 시뮬레이션 실행
for binary in "${binaries[@]}"; do
    for trace in "${traces[@]}"; do
        # 트레이스 파일명에서 확장자 제거하여 출력 파일명 생성
        trace_name=$(basename "$trace" .champsimtrace.xz)
        
        # 출력 파일명 생성
        output_file="results/${binary}_${trace_name}.txt"
        
        # 작업 슬롯이 있을 때까지 대기
        wait_for_job_slot
        
        echo "실행 중: bin/$binary test_traces/$trace -> $output_file"
        
        # 백그라운드에서 시뮬레이션 실행
        nohup bin/$binary /home/hamoci/Study/ChampSim/test_traces/$trace > "$output_file" 2>&1 &

        # 실행 중인 작업 수 증가
        ((running_jobs++))
    done
done

# 모든 작업이 완료될 때까지 대기
echo "모든 시뮬레이션이 시작되었습니다. 완료를 기다리는 중..."
wait

echo "================================"
echo "모든 시뮬레이션 완료: $(date)"
echo "결과 파일들이 results/ 디렉토리에 저장되었습니다."

# 결과 파일 목록 출력
echo ""
echo "생성된 결과 파일 목록:"
ls -la results/*.txt | wc -l
echo "개의 결과 파일이 생성되었습니다."
