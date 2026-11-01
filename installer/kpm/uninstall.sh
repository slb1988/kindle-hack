#!/bin/sh
set -eu

USB=${OCEAN_USB_ROOT:-/mnt/us}
for script in OceanCheck.sh OceanWeRead.sh OceanDoom.sh OceanNeoGeo.sh OceanStock.sh; do
    if [ -f "$USB/documents/$script" ] && cmp -s "scriptlets/$script" "$USB/documents/$script"; then
        rm -f "$USB/documents/$script"
    fi
done

printf '%s\n' 'Ocean launch scriptlets removed; account data and saved games preserved.'
