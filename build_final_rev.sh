#!/bin/bash
cd /home/hamoci/Study/ChampSim/

#make clean

# Build all configs in ./sim_configs/final_rev/ recursively
for config in $(find ./sim_configs/final_rev/ -name "*.json" | sort); do
    echo "Building config: $config"
    ./config.sh "$config"
    make -j
    if [ $? -ne 0 ]; then
        echo "Build failed for: $config"
        exit 1
    fi
    echo "Successfully built: $config"
    echo "----------------------------------------"
done

echo "All configs built successfully!"
