#!/bin/sh
# Preflight only: no VPN, keys, network changes, module loading, or autostart.
set -u
umask 077
ulimit -c 0 2>/dev/null || :
BASE=/mnt/us/kwg-preflight
STATE="$BASE/state"
BIN="$BASE/kwg"
mkdir -p "$STATE" || exit 1
exec > "$STATE/check.log" 2>&1
printf 'WireGuard v0.2.0 preflight (no installation or tunnel activation)\n'
printf 'kernel: '; uname -r
printf 'architecture: '; uname -m
printf 'uid: '; id -u
printf 'timestamp: '; date -u

kernel=$(uname -r)
major=${kernel%%.*}
rest=${kernel#*.}
minor=${rest%%.*}
kernel_supported=false
case "$major:$minor" in
    *[!0-9:]*|'':*) ;;
    *)
        if [ "$major" -gt 3 ] || { [ "$major" -eq 3 ] && [ "$minor" -ge 2 ]; }; then
            kernel_supported=true
        fi
        ;;
esac
arch_supported=false
[ "$(uname -m)" = armv7l ] && arch_supported=true

printf '\n=== TUN configuration (read-only) ===\n'
if [ -r /proc/config.gz ]; then
    gzip -dc /proc/config.gz 2>/dev/null | grep -E '^(CONFIG_TUN=|# CONFIG_TUN is not set)' || :
else
    printf '/proc/config.gz unavailable\n'
fi
if [ -d /lib/modules ]; then
    find /lib/modules -name 'tun.ko*' -print 2>/dev/null || :
fi
tun_registered=false
tun_node=false
tun_open=false
if grep -Eq '(^|[[:space:]])tun$' /proc/misc; then
    tun_registered=true
fi
if [ -c /dev/net/tun ]; then
    tun_node=true
    ls -l /dev/net/tun
fi
# Only open an already registered driver; never load a module or create an interface.
if [ "$tun_registered" = true ] && [ "$tun_node" = true ]; then
    if (exec 3<> /dev/net/tun); then tun_open=true; fi
fi
printf 'driver_registered: %s\ncharacter_device: %s\ndevice_open: %s\n' "$tun_registered" "$tun_node" "$tun_open"

printf '\n=== Official binary startup test (--help only) ===\n'
hash_ok=true
if command -v sha256sum >/dev/null 2>&1; then
    sum=$(sha256sum "$BIN")
    case "$sum" in
        9167c55f126cd6b74dbe3184b22a59fe1dc90c829754d0d5d0cf6eb731a6dee3\ *) ;;
        *) hash_ok=false ;;
    esac
fi
runtime_ok=false
runtime_rc=125
timed_out=false
if [ "$hash_ok" = true ] && [ "$arch_supported" = true ]; then
    "$BIN" --help > "$STATE/runtime.log" 2>&1 &
    child=$!
    trap 'kill -TERM "$child" 2>/dev/null || :; exit 1' HUP INT TERM
    elapsed=0
    while kill -0 "$child" 2>/dev/null; do
        if [ "$elapsed" -ge 10 ]; then
            timed_out=true
            kill -TERM "$child" 2>/dev/null || :
            sleep 1
            kill -KILL "$child" 2>/dev/null || :
            break
        fi
        sleep 1
        elapsed=$((elapsed + 1))
    done
    wait "$child"
    runtime_rc=$?
    trap - HUP INT TERM
    if [ "$runtime_rc" -eq 0 ] && [ "$timed_out" = false ] && grep -q '^usage:' "$STATE/runtime.log"; then
        runtime_ok=true
    fi
fi
printf 'runtime_exit: %s\nruntime_started: %s\n' "$runtime_rc" "$runtime_ok"

result=preflight_passed_vpn_untested
if [ "$hash_ok" != true ]; then result=binary_hash_mismatch
elif [ "$arch_supported" != true ]; then result=unsupported_architecture
elif [ "$runtime_ok" != true ]; then result=runtime_failed
elif [ "$tun_open" != true ]; then result=tun_unavailable
elif [ "$kernel_supported" != true ]; then result=outside_upstream_kernel_support
fi
printf '{"release":"v0.2.0","phase":"preflight_only","result":"%s","kernelSupportedByGo":%s,"architectureSupported":%s,"tunDriverRegistered":%s,"tunCharacterDevice":%s,"tunDeviceOpens":%s,"binaryStarts":%s,"binaryExitCode":%s,"binaryTimedOut":%s,"tunInterfaceCreation":"not_tested","vpn":"not_started","autostart":"not_installed","clientConfig":"not_copied"}\n' \
    "$result" "$kernel_supported" "$arch_supported" "$tun_registered" "$tun_node" "$tun_open" "$runtime_ok" "$runtime_rc" "$timed_out" > "$STATE/status.json.tmp"
mv "$STATE/status.json.tmp" "$STATE/status.json"
printf '\nresult: %s\nDone. Reconnect USB so the computer can read kwg-preflight/state/.\n' "$result"
sync
