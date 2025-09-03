#!/bin/bash
cd /home/hamoci/Study/ChampSim/

./config.sh _2MBLLC_2MBPage_DRAM_Error.json
make -j

./config.sh _2MBLLC_2MBPage_DRAM.json
make -j

./config.sh _2MBLLC_4KBPage_DRAM_Error.json
make -j

./config.sh _2MBLLC_4KBPage_DRAM.json
make -j