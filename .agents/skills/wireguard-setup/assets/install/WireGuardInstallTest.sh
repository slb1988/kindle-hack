#!/bin/sh
# Name: WireGuard Install Test
# Author: local setup

printf 'Importing WireGuard config and testing VPN (up to about 90 seconds).\n'
printf 'Keep Wi-Fi on. No DNS change or boot autostart during this test.\n'
/bin/sh /mnt/us/kwg-install/install-and-test.sh
rc=$?
if [ "$rc" -eq 0 ]; then
    printf 'VPN test: DONE. Tunnel stopped; reconnect USB.\n'
else
    printf 'VPN test: CHECK LOG. Reconnect USB for diagnosis.\n'
fi
exit "$rc"
