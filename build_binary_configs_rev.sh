#!/bin/bash
cd /home/hamoci/Study/ChampSim/

make clean

# ./config.sh ./sim_configs/cycle_interval/_32GBDRAM/_2MBLLC_4KBPage_DRAM.json
# make -j
# ./config.sh ./sim_configs/cycle_interval/_32GBDRAM/_2MBLLC_4KBPage_DRAM_Error_1e7.json
# make -j
# ./config.sh ./sim_configs/cycle_interval/_32GBDRAM/_2MBLLC_4KBPage_DRAM_Error_1e8.json
# make -j
# ./config.sh ./sim_configs/cycle_interval/_32GBDRAM/_2MBLLC_4KBPage_DRAM_Error_1e9.json
# make -j

./config.sh ./sim_configs/cycle_interval/_32GBDRAM/_2MBLLC_2MBPage_DRAM.json
make -j
./config.sh ./sim_configs/cycle_interval/_32GBDRAM/_2MBLLC_2MBPage_DRAM_Error_1e7.json
make -j
./config.sh ./sim_configs/cycle_interval/_32GBDRAM/_2MBLLC_2MBPage_DRAM_Error_1e8.json
make -j
./config.sh ./sim_configs/cycle_interval/_32GBDRAM/_2MBLLC_2MBPage_DRAM_Error_1e9.json
make -j

./config.sh ./sim_configs/cycle_interval/_32GBDRAM/_2MBLLC_1GBPage_DRAM.json
make -j
./config.sh ./sim_configs/cycle_interval/_32GBDRAM/_2MBLLC_1GBPage_DRAM_Error_1e7.json
make -j
./config.sh ./sim_configs/cycle_interval/_32GBDRAM/_2MBLLC_1GBPage_DRAM_Error_1e8.json
make -j
./config.sh ./sim_configs/cycle_interval/_32GBDRAM/_2MBLLC_1GBPage_DRAM_Error_1e9.json
make -j


# ./config.sh ./sim_configs/cycle_interval/_64GBDRAM/_2MBLLC_4KBPage_DRAM.json
# make -j
# ./config.sh ./sim_configs/cycle_interval/_64GBDRAM/_2MBLLC_4KBPage_DRAM_Error_1e7.json
# make -j
# ./config.sh ./sim_configs/cycle_interval/_64GBDRAM/_2MBLLC_4KBPage_DRAM_Error_1e8.json
# make -j
# ./config.sh ./sim_configs/cycle_interval/_64GBDRAM/_2MBLLC_4KBPage_DRAM_Error_1e9.json
# make -j

./config.sh ./sim_configs/cycle_interval/_64GBDRAM/_2MBLLC_2MBPage_DRAM.json
make -j
./config.sh ./sim_configs/cycle_interval/_64GBDRAM/_2MBLLC_2MBPage_DRAM_Error_1e7.json
make -j
./config.sh ./sim_configs/cycle_interval/_64GBDRAM/_2MBLLC_2MBPage_DRAM_Error_1e8.json
make -j
./config.sh ./sim_configs/cycle_interval/_64GBDRAM/_2MBLLC_2MBPage_DRAM_Error_1e9.json
make -j

./config.sh ./sim_configs/cycle_interval/_64GBDRAM/_2MBLLC_1GBPage_DRAM.json
make -j
./config.sh ./sim_configs/cycle_interval/_64GBDRAM/_2MBLLC_1GBPage_DRAM_Error_1e7.json
make -j
./config.sh ./sim_configs/cycle_interval/_64GBDRAM/_2MBLLC_1GBPage_DRAM_Error_1e8.json
make -j
./config.sh ./sim_configs/cycle_interval/_64GBDRAM/_2MBLLC_1GBPage_DRAM_Error_1e9.json
make -j

# ./config.sh ./sim_configs/cycle_interval/_128GBDRAM/_2MBLLC_4KBPage_DRAM.json
# make -j
# ./config.sh ./sim_configs/cycle_interval/_128GBDRAM/_2MBLLC_4KBPage_DRAM_Error_1e7.json
# make -j
# ./config.sh ./sim_configs/cycle_interval/_128GBDRAM/_2MBLLC_4KBPage_DRAM_Error_1e8.json
# make -j
# ./config.sh ./sim_configs/cycle_interval/_128GBDRAM/_2MBLLC_4KBPage_DRAM_Error_1e9.json
# make -j

./config.sh ./sim_configs/cycle_interval/_128GBDRAM/_2MBLLC_2MBPage_DRAM.json
make -j
./config.sh ./sim_configs/cycle_interval/_128GBDRAM/_2MBLLC_2MBPage_DRAM_Error_1e7.json
make -j
./config.sh ./sim_configs/cycle_interval/_128GBDRAM/_2MBLLC_2MBPage_DRAM_Error_1e8.json
make -j
./config.sh ./sim_configs/cycle_interval/_128GBDRAM/_2MBLLC_2MBPage_DRAM_Error_1e9.json
make -j

./config.sh ./sim_configs/cycle_interval/_128GBDRAM/_2MBLLC_1GBPage_DRAM.json
make -j
./config.sh ./sim_configs/cycle_interval/_128GBDRAM/_2MBLLC_1GBPage_DRAM_Error_1e7.json
make -j
./config.sh ./sim_configs/cycle_interval/_128GBDRAM/_2MBLLC_1GBPage_DRAM_Error_1e8.json
make -j
./config.sh ./sim_configs/cycle_interval/_128GBDRAM/_2MBLLC_1GBPage_DRAM_Error_1e9.json
make -j

