#!/bin/bash
cd /home/hamoci/Study/ChampSim/

nohup bin/champsim_4kb_ptw-l1d ../start_hpca24_ae/experiments/traces/du_test.trace.xz > /home/hamoci/Study/ChampSim/results/champsim_config_2MBLLC_4KBPage_L1D.txt &
nohup bin/champsim_4kb_ptw-l2c ../start_hpca24_ae/experiments/traces/du_test.trace.xz > /home/hamoci/Study/ChampSim/results/champsim_config_2MBLLC_4KBPage_L2C.txt &
nohup bin/champsim_4kb_ptw-llc ../start_hpca24_ae/experiments/traces/du_test.trace.xz > /home/hamoci/Study/ChampSim/results/champsim_config_2MBLLC_4KBPage_LLC.txt &
nohup bin/champsim_4kb_ptw-dram ../start_hpca24_ae/experiments/traces/du_test.trace.xz > /home/hamoci/Study/ChampSim/results/champsim_config_2MBLLC_4KBPage_DRAM.txt &