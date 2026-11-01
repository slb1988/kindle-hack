#!/bin/sh
set -eu

USB=${OCEAN_USB_ROOT:-/mnt/us}
for script in OceanCheck.sh OceanWeRead.sh OceanDoom.sh OceanNeoGeo.sh OceanStock.sh; do
    cp "scriptlets/$script" "$USB/documents/$script"
done

printf '%s\n' 'Ocean launch scriptlets installed.'
