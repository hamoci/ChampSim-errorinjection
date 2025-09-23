#!/bin/bash
cd /home/hamoci/Study/ChampSim/

./config.sh ./sim_configs/_32GBDRAM/_2MBLLC_2MBPage_DRAM_Error.json
make -j
./config.sh ./sim_configs/_32GBDRAM/_2MBLLC_2MBPage_DRAM.json
make -j
./config.sh ./sim_configs/_32GBDRAM/_2MBLLC_4KBPage_DRAM_Error.json
make -j
./config.sh ./sim_configs/_32GBDRAM/_2MBLLC_4KBPage_DRAM.json
make -j
# ./config.sh ./sim_configs/_32GBDRAM/_2MBLLC_1GBPage_DRAM_Error.json
# make -j
# ./config.sh ./sim_configs/_32GBDRAM/_2MBLLC_1GBPage_DRAM.json
# make -j

# ./config.sh ./sim_configs/_64GBDRAM/_2MBLLC_2MBPage_DRAM_Error.json
# make -j
# ./config.sh ./sim_configs/_64GBDRAM/_2MBLLC_2MBPage_DRAM.json
# make -j
# ./config.sh ./sim_configs/_64GBDRAM/_2MBLLC_4KBPage_DRAM_Error.json
# make -j
# ./config.sh ./sim_configs/_64GBDRAM/_2MBLLC_4KBPage_DRAM.json
# make -j
# ./config.sh ./sim_configs/_64GBDRAM/_2MBLLC_1GBPage_DRAM_Error.json
# make -j
# ./config.sh ./sim_configs/_64GBDRAM/_2MBLLC_1GBPage_DRAM.json
# make -j

# ./config.sh ./sim_configs/_128GBDRAM/_2MBLLC_2MBPage_DRAM_Error.json
# make -j
# ./config.sh ./sim_configs/_128GBDRAM/_2MBLLC_2MBPage_DRAM.json
# make -j
# ./config.sh ./sim_configs/_128GBDRAM/_2MBLLC_4KBPage_DRAM_Error.json
# make -j
# ./config.sh ./sim_configs/_128GBDRAM/_2MBLLC_4KBPage_DRAM.json
# make -j
# ./config.sh ./sim_configs/_128GBDRAM/_2MBLLC_1GBPage_DRAM_Error.json
# make -j
# ./config.sh ./sim_configs/_128GBDRAM/_2MBLLC_1GBPage_DRAM.json
# make -j