#!/bin/bash
cd /home/hamoci/Study/ChampSim/

#make clean

./config.sh ./sim_configs/cache_pinning_MTBF_sweep/_32GBDRAM/_2MBLLC_2MBPage_DRAM_Error_1e-6.json
make -j
./config.sh ./sim_configs/cache_pinning_MTBF_sweep/_32GBDRAM/_2MBLLC_2MBPage_DRAM_Error_1e-7.json
make -j
./config.sh ./sim_configs/cache_pinning_MTBF_sweep/_32GBDRAM/_2MBLLC_2MBPage_DRAM_Error_1e-8.json
make -j
./config.sh ./sim_configs/cache_pinning_MTBF_sweep/_32GBDRAM/_2MBLLC_2MBPage_DRAM_Error_1e-9.json
make -j

./config.sh ./sim_configs/cache_pinning_MTBF_sweep/_32GBDRAM/_2MBLLC_4KBPage_DRAM_Error_1e-6.json
make -j
./config.sh ./sim_configs/cache_pinning_MTBF_sweep/_32GBDRAM/_2MBLLC_4KBPage_DRAM_Error_1e-7.json
make -j
./config.sh ./sim_configs/cache_pinning_MTBF_sweep/_32GBDRAM/_2MBLLC_4KBPage_DRAM_Error_1e-8.json
make -j
./config.sh ./sim_configs/cache_pinning_MTBF_sweep/_32GBDRAM/_2MBLLC_4KBPage_DRAM_Error_1e-9.json
make -j

