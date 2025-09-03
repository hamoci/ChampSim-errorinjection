#!/bin/bash
cd /home/hamoci/Study/ChampSim/

nohup bin/champsim_4kb ../start_hpca24_ae/experiments/traces/602.gcc_s-1850B.champsimtrace.xz > /home/hamoci/Study/ChampSim/results/_2MBLLC_4KBPage_gcc.txt &
nohup bin/champsim_4kb_error ../start_hpca24_ae/experiments/traces/602.gcc_s-1850B.champsimtrace.xz > /home/hamoci/Study/ChampSim/results/_2MBLLC_4KBPage_Error_gcc.txt &
nohup bin/champsim_2mb ../start_hpca24_ae/experiments/traces/602.gcc_s-1850B.champsimtrace.xz > /home/hamoci/Study/ChampSim/results/_2MBLLC_2MBPage_gcc.txt &
nohup bin/champsim_2mb_error ../start_hpca24_ae/experiments/traces/602.gcc_s-1850B.champsimtrace.xz > /home/hamoci/Study/ChampSim/results/_2MBLLC_2MBPage_Error_gcc.txt &