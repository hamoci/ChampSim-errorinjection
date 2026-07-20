#!/bin/bash
# ---------------------------------------------------------------------------
# Rev1 sticky-model multicore batch runner (exp2 retirement-threshold +
# exp6 LLC-way-sweep), re-run under error_spatial_model=sticky, density 0.05.
#
# Keeps the TOTAL number of running champsim processes at ~TARGET across the
# whole machine (counts everything, so it shares with any other champsim runs).
# Resumable: skips (binary x mix) whose output already has "ChampSim completed".
#
# Usage:  nohup ./run_rev_sticky.sh &   (or launched in background)
# ---------------------------------------------------------------------------
cd "$(dirname "$0")" || exit 1

TARGET=40                       # total champsim processes to maintain machine-wide
WARMUP=50000000                 # 50M warmup
SIM=250000000                   # 250M sim  (= 300M total, DPC-3 consistency)
OUTROOT=results/multicore_rev
LOG=$OUTROOT/scheduler.log
TR=test_traces

# --- 7 representative mixes (4 traces each) --------------------------------
declare -A MIX
MIX[C1]="$TR/623.xalancbmk_s-592B.champsimtrace.xz $TR/628.pop2_s-17B.champsimtrace.xz $TR/654.roms_s-1007B.champsimtrace.xz $TR/621.wrf_s-6673B.champsimtrace.xz"
MIX[H1]="$TR/605.mcf_s-994B.champsimtrace.xz $TR/649.fotonik3d_s-10881B.champsimtrace.xz $TR/623.xalancbmk_s-592B.champsimtrace.xz $TR/628.pop2_s-17B.champsimtrace.xz"
MIX[M1]="$TR/605.mcf_s-994B.champsimtrace.xz $TR/649.fotonik3d_s-10881B.champsimtrace.xz $TR/602.gcc_s-1850B.champsimtrace.xz $TR/603.bwaves_s-2931B.champsimtrace.xz"
MIX[XS]="$TR/xsbench_event_large-18.3B.champsimtrace.xz $TR/xsbench_event_large-18.3B.champsimtrace.xz $TR/xsbench_event_large-18.3B.champsimtrace.xz $TR/xsbench_event_large-18.3B.champsimtrace.xz"
MIX[LL]="$TR/llama2.c-llama2_7b.1.champsimtrace.gz $TR/llama2.c-llama2_7b.1.champsimtrace.gz $TR/llama2.c-llama2_7b.1.champsimtrace.gz $TR/llama2.c-llama2_7b.1.champsimtrace.gz"
MIX[RA]="$TR/redis-8.8.0_ycsba.champsimtrace.xz $TR/redis-8.8.0_ycsba.champsimtrace.xz $TR/redis-8.8.0_ycsba.champsimtrace.xz $TR/redis-8.8.0_ycsba.champsimtrace.xz"
MIX[RC]="$TR/redis-8.8.0_ycsbc.champsimtrace.xz $TR/redis-8.8.0_ycsbc.champsimtrace.xz $TR/redis-8.8.0_ycsbc.champsimtrace.xz $TR/redis-8.8.0_ycsbc.champsimtrace.xz"
MIXES="C1 H1 M1 XS LL RA RC"

mkdir -p "$OUTROOT/2_retirement_threshold" "$OUTROOT/6_llc_way_sweep"

# --- build job queue from the built rev binaries --------------------------
JOBS=$OUTROOT/jobs.txt; : > "$JOBS"
for b in $(cd bin && ls champsim_rev_* 2>/dev/null); do
  case "$b" in
    *_thr*) sub=2_retirement_threshold ;;
    *_mw*)  sub=6_llc_way_sweep ;;
    *)      sub=. ;;
  esac
  for m in $MIXES; do
    out="$OUTROOT/$sub/${b#champsim_rev_}_${m}.txt"
    if [ -f "$out" ] && grep -q "ChampSim completed" "$out" 2>/dev/null; then continue; fi
    echo "$b|$m|$out" >> "$JOBS"
  done
done
TOTAL=$(wc -l < "$JOBS")
echo "$(date '+%F %T') === queue: $TOTAL jobs, maintain $TARGET champsim machine-wide ===" | tee -a "$LOG"

# --- scheduler loop: keep ~TARGET champsim running ------------------------
i=0
while [ "$i" -lt "$TOTAL" ]; do
  running=$(ps -eo comm= | grep -c '^champsim')
  while [ "$running" -lt "$TARGET" ] && [ "$i" -lt "$TOTAL" ]; do
    i=$((i+1))
    line=$(sed -n "${i}p" "$JOBS")
    b=${line%%|*}; rest=${line#*|}; m=${rest%%|*}; out=${rest#*|}
    nice -n 15 stdbuf -oL bin/"$b" --warmup-instructions "$WARMUP" --simulation-instructions "$SIM" ${MIX[$m]} > "$out" 2>&1 &
    echo "$(date '+%F %T') [launch $i/$TOTAL] $b x $m" >> "$LOG"
    running=$((running+1))
    sleep 2
  done
  sleep 60
done
echo "$(date '+%F %T') all $TOTAL launched; waiting for completion" | tee -a "$LOG"
wait
echo "$(date '+%F %T') ===== ALL DONE =====" | tee -a "$LOG"
