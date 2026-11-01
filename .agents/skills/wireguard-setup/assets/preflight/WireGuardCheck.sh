#!/bin/sh
# Name: WireGuard Check
# Author: local setup

printf 'WireGuard Check: starting. No VPN changes.\n'
LOG=/mnt/us/kwg-preflight/launcher.log
if ! printf 'WireGuard Check launcher v2 started\n' > "$LOG"; then
    printf 'ERROR: cannot write launcher.log on Kindle storage.\n'
    exit 1
fi
date -u >> "$LOG" 2>&1
printf 'Collecting kernel/module information for TUN...\n'
if ! /bin/sh /mnt/us/kwg-preflight/tun-snapshot.sh >> "$LOG" 2>&1; then
    printf 'TUN info capture failed. Please reconnect USB.\n'
    sync
    exit 1
fi
/bin/sh /mnt/us/kwg-preflight/check.sh >> "$LOG" 2>&1
rc=$?
printf 'check_exit: %s\n' "$rc" >> "$LOG"
if [ "$rc" -eq 0 ] && [ -s /mnt/us/kwg-preflight/state/status.json ]; then
    printf 'WireGuard Check: DONE. Please reconnect USB.\n'
else
    printf 'WireGuard Check: ERROR (exit %s). Please reconnect USB.\n' "$rc"
    tail -n 5 "$LOG"
fi
sync
exit "$rc"
