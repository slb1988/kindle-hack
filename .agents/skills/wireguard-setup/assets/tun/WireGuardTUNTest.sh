#!/bin/sh
# Name: WireGuard TUN Test
# Author: local setup

printf 'Testing a temporary TUN driver. No VPN or autostart.\n'
/bin/sh /mnt/us/kwg-tun/load-test.sh
rc=$?
if [ "$rc" -eq 0 ]; then
    printf 'TUN test: PASS. Please reconnect USB.\n'
else
    printf 'TUN test: FAILED. Please reconnect USB.\n'
fi
exit "$rc"
