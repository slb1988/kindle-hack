#!/bin/sh
set -eu

action=${1:-status}
case "$action" in
    check) action=install ;;
    weread|doom|neogeo|stock|status|install) : ;;
    *) printf 'Usage: kpm launch ocean [check|weread|doom|neogeo|stock|status]\n' >&2; exit 2 ;;
esac

root=$(CDPATH='' cd "$(dirname "$0")" && pwd)
export OCEAN_EXTENSION_ROOT="$root"
export OCEAN_USB_ROOT=${OCEAN_USB_ROOT:-/mnt/us}
exec "$root/bin/ocean.sh" "$action"
