#!/bin/bash
cd /home/hamoci/Study/ChampSim/

make clean

# 2MB Page - LLC Size Reduction
./config.sh ./sim_configs/cycle_interval_llc/_32GBDRAM/_1.5MBLLC_2MBPage_DRAM.json
make -j
./config.sh ./sim_configs/cycle_interval_llc/_32GBDRAM/_1MBLLC_2MBPage_DRAM.json
make -j
./config.sh ./sim_configs/cycle_interval_llc/_32GBDRAM/_512KBLLC_2MBPage_DRAM.json
make -j
./config.sh ./sim_configs/cycle_interval_llc/_32GBDRAM/_256KBLLC_2MBPage_DRAM.json
make -j

# 2MB Page - Way Reservation
./config.sh ./sim_configs/cycle_interval_llc/_32GBDRAM/_2MBLLC_15ways_2MBPage_DRAM.json
make -j
./config.sh ./sim_configs/cycle_interval_llc/_32GBDRAM/_2MBLLC_14ways_2MBPage_DRAM.json
make -j
./config.sh ./sim_configs/cycle_interval_llc/_32GBDRAM/_2MBLLC_13ways_2MBPage_DRAM.json
make -j
./config.sh ./sim_configs/cycle_interval_llc/_32GBDRAM/_2MBLLC_12ways_2MBPage_DRAM.json
make -j
./config.sh ./sim_configs/cycle_interval_llc/_32GBDRAM/_2MBLLC_11ways_2MBPage_DRAM.json
make -j
./config.sh ./sim_configs/cycle_interval_llc/_32GBDRAM/_2MBLLC_10ways_2MBPage_DRAM.json
make -j
./config.sh ./sim_configs/cycle_interval_llc/_32GBDRAM/_2MBLLC_9ways_2MBPage_DRAM.json
make -j
./config.sh ./sim_configs/cycle_interval_llc/_32GBDRAM/_2MBLLC_8ways_2MBPage_DRAM.json
make -j

# 4KB Page - LLC Size Reduction
./config.sh ./sim_configs/cycle_interval_llc/_32GBDRAM/_1.5MBLLC_4KBPage_DRAM.json
make -j
./config.sh ./sim_configs/cycle_interval_llc/_32GBDRAM/_1MBLLC_4KBPage_DRAM.json
make -j
./config.sh ./sim_configs/cycle_interval_llc/_32GBDRAM/_512KBLLC_4KBPage_DRAM.json
make -j
./config.sh ./sim_configs/cycle_interval_llc/_32GBDRAM/_256KBLLC_4KBPage_DRAM.json
make -j

# 4KB Page - Way Reservation
./config.sh ./sim_configs/cycle_interval_llc/_32GBDRAM/_2MBLLC_15ways_4KBPage_DRAM.json
make -j
./config.sh ./sim_configs/cycle_interval_llc/_32GBDRAM/_2MBLLC_14ways_4KBPage_DRAM.json
make -j
./config.sh ./sim_configs/cycle_interval_llc/_32GBDRAM/_2MBLLC_13ways_4KBPage_DRAM.json
make -j
./config.sh ./sim_configs/cycle_interval_llc/_32GBDRAM/_2MBLLC_12ways_4KBPage_DRAM.json
make -j
./config.sh ./sim_configs/cycle_interval_llc/_32GBDRAM/_2MBLLC_11ways_4KBPage_DRAM.json
make -j
./config.sh ./sim_configs/cycle_interval_llc/_32GBDRAM/_2MBLLC_10ways_4KBPage_DRAM.json
make -j
./config.sh ./sim_configs/cycle_interval_llc/_32GBDRAM/_2MBLLC_9ways_4KBPage_DRAM.json
make -j
./config.sh ./sim_configs/cycle_interval_llc/_32GBDRAM/_2MBLLC_8ways_4KBPage_DRAM.json
make -j

