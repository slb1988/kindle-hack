#!/bin/sh
# Single Upstart-supervised WireGuard watchdog. Uses the plugin's existing job.
# No Wi-Fi forcing, sleep inhibition, kernel flashing, or unguarded module load.
set -u
umask 077
DIR=$(CDPATH= cd "$(dirname "$0")" && pwd) || exit 1
BIN="$DIR/kwg"
CONF=${1:-/var/local/kwg/wg.conf}
LOG=${2:-/var/local/kwg/kwg.log}
STATE=/var/local/kwg
GUARD="$STATE/tun-load-pending"
LOCK=/tmp/kwg-watchdog.lock
INTERVAL=${KWG_WATCH_INTERVAL:-10}
case "$INTERVAL" in 1|2|5|10|15|30) ;; *) INTERVAL=10 ;; esac
CHILD=
CHILD_STAMP=
HELPER=
HELPER_STAMP=
SLEEP_PID=
LAST_PHASE=
mkdir -p "$STATE" || exit 1
chmod 700 "$STATE" || exit 1

stamp() { awk '{print $22}' "/proc/$1/stat" 2>/dev/null; }
alive() {
    [ -n "$1" ] && [ -n "$2" ] || return 1
    kill -0 "$1" 2>/dev/null || return 1
    [ "$(stamp "$1")" = "$2" ]
}
log() {
    if [ -f "$LOG" ] && [ "$(wc -c < "$LOG")" -gt 200000 ]; then
        tail -n 200 "$LOG" > "$LOG.trim" && mv "$LOG.trim" "$LOG"
    fi
    printf '%s %s\n' "$(date -u '+%Y-%m-%dT%H:%M:%SZ')" "$1" >> "$LOG"
}
phase() {
    if [ "$LAST_PHASE" != "$1" ]; then
        printf '%s\n' "$1" > "$STATE/service-phase.tmp"
        mv "$STATE/service-phase.tmp" "$STATE/service-phase"
        LAST_PHASE="$1"
        log "state: $1"
    fi
}
nap() {
    sleep "$1" &
    SLEEP_PID=$!
    wait "$SLEEP_PID" 2>/dev/null || :
    SLEEP_PID=
}
stop_owned() {
    p="$1"; identity="$2"
    [ -n "$p" ] || return 0
    if alive "$p" "$identity"; then
        kill -TERM "$p" 2>/dev/null || :
        n=0
        while alive "$p" "$identity" && [ "$n" -lt 2 ]; do sleep 1; n=$((n + 1)); done
        if alive "$p" "$identity"; then kill -KILL "$p" 2>/dev/null || :; fi
    fi
    if ! alive "$p" "$identity"; then wait "$p" 2>/dev/null || :; fi
}
shutdown() {
    trap - HUP INT TERM
    [ -z "$SLEEP_PID" ] || kill -TERM "$SLEEP_PID" 2>/dev/null || :
    stop_owned "$CHILD" "$CHILD_STAMP"
    stop_owned "$HELPER" "$HELPER_STAMP"
    phase stopped
    rm -f "$LOCK/pid" "$LOCK/stamp"
    rmdir "$LOCK" 2>/dev/null || :
    log 'watchdog stopped; boot setting unchanged'
    exit 0
}

if ! mkdir "$LOCK" 2>/dev/null; then
    previous_pid=; previous_stamp=
    [ ! -r "$LOCK/pid" ] || IFS= read -r previous_pid < "$LOCK/pid" || :
    [ ! -r "$LOCK/stamp" ] || IFS= read -r previous_stamp < "$LOCK/stamp" || :
    case "$previous_pid:$previous_stamp" in
        *[!0-9:]*|:*|*:) log 'watchdog lock is incomplete; refusing duplicate'; exit 1 ;;
    esac
    if alive "$previous_pid" "$previous_stamp"; then log 'watchdog already running'; exit 1; fi
    rm -f "$LOCK/pid" "$LOCK/stamp"
    rmdir "$LOCK" 2>/dev/null && mkdir "$LOCK" || exit 1
fi
printf '%s\n' "$$" > "$LOCK/pid"
printf '%s\n' "$(stamp "$$")" > "$LOCK/stamp"
trap 'shutdown' HUP INT TERM
boot_id=$(tr -cd 'a-f0-9-' < /proc/sys/kernel/random/boot_id)
origin=manual
case " ${UPSTART_EVENTS:-} " in *' framework_ready '*) origin=framework_ready ;; esac
printf '%s\n' "$boot_id" > "$STATE/service-boot-id"
printf '%s\n' "$origin" > "$STATE/service-origin"
printf '{"bootId":"%s","origin":"%s","pid":%s,"startedAt":"%s","uptimeSeconds":%s}\n' \
    "$boot_id" "$origin" "$$" "$(date -u '+%Y-%m-%dT%H:%M:%SZ')" "$(awk '{printf "%d",$1}' /proc/uptime)" > "$STATE/service-start.json.tmp"
mv "$STATE/service-start.json.tmp" "$STATE/service-start.json"
log "watchdog started ($origin)"

network_route() { ip route 2>/dev/null | awk '/^default / {print; exit}'; }
tun_ready() { [ -c /dev/net/tun ] && grep -Eq '(^|[[:space:]])tun$' /proc/misc; }
ensure_tun() {
    if tun_ready; then
        [ -e "$GUARD" ] || return 0
        # A manual test may have recovered the driver. Reuse the guarded,
        # hash-verifying loader to confirm it before clearing the marker.
        phase tun_rechecking
    else
        if [ -e "$GUARD" ]; then
            phase tun_guard_paused
            return 1
        fi
        phase tun_setup
        (set -C; printf '%s\n' "$boot_id" > "$GUARD") || return 1
    fi
    sync
    /bin/sh /mnt/us/kwg-tun/load-test.sh >> "$LOG" 2>&1 &
    HELPER=$!
    HELPER_STAMP=$(stamp "$HELPER")
    wait "$HELPER"
    rc=$?
    HELPER=; HELPER_STAMP=
    case "$rc" in
        0) rm -f "$GUARD"; return 0 ;;
        *) phase tun_guard_paused; return 1 ;;
    esac
}

while :; do
    route=$(network_route)
    if [ -z "$route" ]; then phase waiting_network; nap "$INTERVAL"; continue; fi
    binary_sum=$(sha256sum "$DIR/kwg.bin" 2>/dev/null) || binary_sum=
    if [ "${binary_sum%% *}" != 9167c55f126cd6b74dbe3184b22a59fe1dc90c829754d0d5d0cf6eb731a6dee3 ]; then
        phase payload_error; nap 30; continue
    fi
    if ! "$DIR/kwg.bin" check "$CONF" >> "$LOG" 2>&1; then phase config_error; nap 30; continue; fi
    if [ -d /sys/class/net/wg0 ]; then phase unmanaged_tunnel; nap "$INTERVAL"; continue; fi
    if ! ensure_tun; then nap 30; continue; fi
    phase tunnel_starting
    "$BIN" up "$CONF" >> "$LOG" 2>&1 &
    CHILD=$!
    CHILD_STAMP=$(stamp "$CHILD")
    while alive "$CHILD" "$CHILD_STAMP"; do
        [ ! -d /sys/class/net/wg0 ] || phase tunnel_up
        nap "$INTERVAL"
        if [ "$(network_route)" != "$route" ]; then phase network_changed; break; fi
    done
    stop_owned "$CHILD" "$CHILD_STAMP"
    CHILD=; CHILD_STAMP=
    phase reconnect_wait
    nap 5
done
