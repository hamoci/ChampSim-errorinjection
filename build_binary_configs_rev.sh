#!/bin/bash
cd /home/hamoci/Study/ChampSim/

make clean

./config.sh ./sim_configs/MTBF_sweep/_32GBDRAM/_2MBLLC_4KBPage_DRAM.json
make -j
./config.sh ./sim_configs/MTBF_sweep/_32GBDRAM/_2MBLLC_4KBPage_DRAM_Error_1e-2.json
make -j
./config.sh ./sim_configs/MTBF_sweep/_32GBDRAM/_2MBLLC_4KBPage_DRAM_Error_1e-3.json
make -j
./config.sh ./sim_configs/MTBF_sweep/_32GBDRAM/_2MBLLC_4KBPage_DRAM_Error_1e-4.json
make -j
./config.sh ./sim_configs/MTBF_sweep/_32GBDRAM/_2MBLLC_4KBPage_DRAM_Error_1e-5.json
make -j
./config.sh ./sim_configs/MTBF_sweep/_32GBDRAM/_2MBLLC_4KBPage_DRAM_Error_1e-6.json
make -j

./config.sh ./sim_configs/MTBF_sweep/_32GBDRAM/_2MBLLC_2MBPage_DRAM.json
make -j
./config.sh ./sim_configs/MTBF_sweep/_32GBDRAM/_2MBLLC_2MBPage_DRAM_Error_1e-2.json
make -j
./config.sh ./sim_configs/MTBF_sweep/_32GBDRAM/_2MBLLC_2MBPage_DRAM_Error_1e-3.json
make -j
./config.sh ./sim_configs/MTBF_sweep/_32GBDRAM/_2MBLLC_2MBPage_DRAM_Error_1e-4.json
make -j
./config.sh ./sim_configs/MTBF_sweep/_32GBDRAM/_2MBLLC_2MBPage_DRAM_Error_1e-5.json
make -j
./config.sh ./sim_configs/MTBF_sweep/_32GBDRAM/_2MBLLC_2MBPage_DRAM_Error_1e-6.json
make -j


./config.sh ./sim_configs/MTBF_sweep/_64GBDRAM/_2MBLLC_4KBPage_DRAM.json
make -j
./config.sh ./sim_configs/MTBF_sweep/_64GBDRAM/_2MBLLC_4KBPage_DRAM_Error_1e-2.json
make -j
./config.sh ./sim_configs/MTBF_sweep/_64GBDRAM/_2MBLLC_4KBPage_DRAM_Error_1e-3.json
make -j
./config.sh ./sim_configs/MTBF_sweep/_64GBDRAM/_2MBLLC_4KBPage_DRAM_Error_1e-4.json
make -j
./config.sh ./sim_configs/MTBF_sweep/_64GBDRAM/_2MBLLC_4KBPage_DRAM_Error_1e-5.json
make -j
./config.sh ./sim_configs/MTBF_sweep/_64GBDRAM/_2MBLLC_4KBPage_DRAM_Error_1e-6.json
make -j

./config.sh ./sim_configs/MTBF_sweep/_64GBDRAM/_2MBLLC_2MBPage_DRAM.json
make -j
./config.sh ./sim_configs/MTBF_sweep/_64GBDRAM/_2MBLLC_2MBPage_DRAM_Error_1e-2.json
make -j
./config.sh ./sim_configs/MTBF_sweep/_64GBDRAM/_2MBLLC_2MBPage_DRAM_Error_1e-3.json
make -j
./config.sh ./sim_configs/MTBF_sweep/_64GBDRAM/_2MBLLC_2MBPage_DRAM_Error_1e-4.json
make -j
./config.sh ./sim_configs/MTBF_sweep/_64GBDRAM/_2MBLLC_2MBPage_DRAM_Error_1e-5.json
make -j
./config.sh ./sim_configs/MTBF_sweep/_64GBDRAM/_2MBLLC_2MBPage_DRAM_Error_1e-6.json
make -j

./config.sh ./sim_configs/MTBF_sweep/_128GBDRAM/_2MBLLC_4KBPage_DRAM.json
make -j
./config.sh ./sim_configs/MTBF_sweep/_128GBDRAM/_2MBLLC_4KBPage_DRAM_Error_1e-2.json
make -j
./config.sh ./sim_configs/MTBF_sweep/_128GBDRAM/_2MBLLC_4KBPage_DRAM_Error_1e-3.json
make -j
./config.sh ./sim_configs/MTBF_sweep/_128GBDRAM/_2MBLLC_4KBPage_DRAM_Error_1e-4.json
make -j
./config.sh ./sim_configs/MTBF_sweep/_128GBDRAM/_2MBLLC_4KBPage_DRAM_Error_1e-5.json
make -j
./config.sh ./sim_configs/MTBF_sweep/_128GBDRAM/_2MBLLC_4KBPage_DRAM_Error_1e-6.json
make -j

./config.sh ./sim_configs/MTBF_sweep/_128GBDRAM/_2MBLLC_2MBPage_DRAM.json
make -j
./config.sh ./sim_configs/MTBF_sweep/_128GBDRAM/_2MBLLC_2MBPage_DRAM_Error_1e-2.json
make -j
./config.sh ./sim_configs/MTBF_sweep/_128GBDRAM/_2MBLLC_2MBPage_DRAM_Error_1e-3.json
make -j
./config.sh ./sim_configs/MTBF_sweep/_128GBDRAM/_2MBLLC_2MBPage_DRAM_Error_1e-4.json
make -j
./config.sh ./sim_configs/MTBF_sweep/_128GBDRAM/_2MBLLC_2MBPage_DRAM_Error_1e-5.json
make -j
./config.sh ./sim_configs/MTBF_sweep/_128GBDRAM/_2MBLLC_2MBPage_DRAM_Error_1e-6.json
make -j