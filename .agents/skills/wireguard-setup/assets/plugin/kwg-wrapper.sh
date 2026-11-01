#!/bin/sh
# Keep the upstream kwg binary intact; supply this device's TUN module only
# when starting a tunnel. Read-only/key/config commands never load a module.
DIR=$(CDPATH= cd "$(dirname "$0")" && pwd) || exit 1
needs_tun=false
case "${1:-}" in
    up) needs_tun=true ;;
    status|check|genkey|pubkey|-h|--help|help|'') ;;
    *) if [ "$#" -eq 1 ] && [ -f "$1" ]; then needs_tun=true; fi ;;
esac
if [ "$needs_tun" = true ]; then
    if ! { [ -c /dev/net/tun ] && grep -Eq '(^|[[:space:]])tun$' /proc/misc; }; then
        if ! /bin/sh /mnt/us/kwg-tun/load-test.sh; then
            printf 'kwg: TUN setup failed; see /mnt/us/kwg-tun/state/test.log\n' >&2
            exit 1
        fi
    fi
fi
exec "$DIR/kwg.bin" "$@"
