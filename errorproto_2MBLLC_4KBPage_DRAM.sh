#!/bin/bash
cd /home/hamoci/Study/ChampSim/

nohup bin/champsim_4kb_ptw-dram ../start_hpca24_ae/experiments/traces/du_test.trace.xz > /home/hamoci/Study/ChampSim/results/champsim_config_2MBLLC_4KBPage_DRAM.txt &
nohup bin/champsim_4kb_ptw-dram-error_proto ../start_hpca24_ae/experiments/traces/du_test.trace.xz > /home/hamoci/Study/ChampSim/results/champsim_config_2MBLLC_4KBPage_DRAM_Error_Proto.txt &