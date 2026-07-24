#!/bin/bash
# ---------------------------------------------------------------------------
# Build exp2 1e-5/1e-6 binaries (20 configs) with low parallelism while the
# recovery scheduler occupies ~38 cores, then wait until recovery has LAUNCHED
# all of its queue (so recovery keeps strict priority for slots), then start
# the 1e-5/1e-6 scheduler instance. No pkill anywhere; file-based conditions.
# ---------------------------------------------------------------------------
cd /home/hamoci/Study/ChampSim || exit 1
LOG=results/multicore_rev/build_exp2_1e56.log
: > "$LOG"

CFGDIR=sim_configs/multicore_rev/2_retirement_threshold
CFGS=$(ls $CFGDIR/*_1e-5.json $CFGDIR/*_1e-6.json | sort)

echo "$(date '+%F %T') === building 20 exp2 1e-5/1e-6 configs (nice, -j4) ===" | tee -a "$LOG"
for cfg in $CFGS; do
  echo "$(date '+%F %T') config: $cfg" >> "$LOG"
  ./config.sh "$cfg" >> "$LOG" 2>&1 || { echo "CONFIG FAILED: $cfg" | tee -a "$LOG"; exit 1; }
  nice -n 19 make -j4 >> "$LOG" 2>&1 || { echo "BUILD FAILED: $cfg" | tee -a "$LOG"; exit 1; }
done

# sanity: all 20 binaries present
MISS=0
for p in off pin; do for t in 2 4 8 16 32; do for r in 1e-5 1e-6; do
  [ -x "bin/champsim_rev_${p}_thr${t}_${r}" ] || { echo "MISSING bin/champsim_rev_${p}_thr${t}_${r}" | tee -a "$LOG"; MISS=1; }
done; done; done
[ "$MISS" -eq 0 ] || exit 1
echo "$(date '+%F %T') === all 20 binaries built ===" | tee -a "$LOG"

# wait until the recovery instance has launched its entire queue (strict priority)
echo "$(date '+%F %T') waiting for recovery scheduler to launch all jobs..." | tee -a "$LOG"
while ! grep -q "all 54 launched" results/multicore_rev/scheduler_recover.log 2>/dev/null; do
  sleep 300
done
echo "$(date '+%F %T') recovery fully launched -> starting 1e-5/1e-6 scheduler" | tee -a "$LOG"

TARGET=38 nohup ./run_rev_sticky.sh 'champsim_rev_*thr*_1e-[56]' exp2new >/dev/null 2>&1 &
disown
sleep 8
echo "$(date '+%F %T') exp2new queue: $(wc -l < results/multicore_rev/jobs_exp2new.txt) jobs" | tee -a "$LOG"
echo "$(date '+%F %T') === chain done ===" | tee -a "$LOG"
