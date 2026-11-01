#!/bin/sh
# Read-only kernel/module capability capture for a separately built TUN module.
# No insmod/modprobe, firmware writes, network changes, keys, or autostart.
set -eu
umask 077
BASE=/mnt/us/kwg-preflight
SNAP="$BASE/tun-snapshot"
mkdir -p "$SNAP"
exec > "$SNAP/capture.log" 2>&1
printf 'TUN build snapshot v1 (no module loaded)\n'
date -u
uname -r > "$SNAP/kernel-release.txt"
uname -m > "$SNAP/architecture.txt"
cp /proc/version "$SNAP/kernel-version.txt"
if [ -r /etc/prettyversion.txt ]; then
    cp /etc/prettyversion.txt "$SNAP/firmware-version.txt"
fi
if [ ! -r /proc/config.gz ]; then
    printf 'ERROR: running kernel configuration is unavailable\n'
    exit 1
fi
gzip -dc /proc/config.gz > "$SNAP/runtime-kernel.config.tmp"
test -s "$SNAP/runtime-kernel.config.tmp"
mv "$SNAP/runtime-kernel.config.tmp" "$SNAP/runtime-kernel.config"
cp /proc/kallsyms "$SNAP/runtime-kallsyms.txt"
cp /proc/modules "$SNAP/loaded-modules.txt"
grep -E '^(Processor|model name|Features|CPU implementer|CPU architecture|CPU variant|CPU part|CPU revision|Hardware|Revision)[[:space:]]*:' /proc/cpuinfo > "$SNAP/cpu-capabilities.txt" || :
grep -E '^(CONFIG_(LOCALVERSION|MODULES|MODULE_UNLOAD|MODVERSIONS|MODULE_SIG|MODULE_SIG_FORCE|SMP|PREEMPT|AEABI|THUMB2_KERNEL|CPU_V7|ARM_PATCH_PHYS_VIRT|KALLSYMS|KALLSYMS_ALL|NET|INET|IPV6|NET_NS|TUN|SECURITY|SECURITY_SELINUX|SECURITY_APPARMOR)=|# CONFIG_(MODULES|MODVERSIONS|MODULE_SIG|MODULE_SIG_FORCE|SMP|PREEMPT|TUN) is not set)' "$SNAP/runtime-kernel.config" > "$SNAP/capabilities.txt" || :
modules_disabled=unknown
if [ -r /proc/sys/kernel/modules_disabled ]; then
    IFS= read -r modules_disabled < /proc/sys/kernel/modules_disabled || :
fi
printf 'modules_disabled: %s\n' "$modules_disabled" >> "$SNAP/capabilities.txt"
printf 'Available tools:\n' > "$SNAP/tools.txt"
for tool in insmod rmmod modprobe modinfo strings sha256sum gzip busybox; do
    command -v "$tool" >> "$SNAP/tools.txt" 2>/dev/null || :
done
: > "$SNAP/module-paths.txt"
if [ -d /lib/modules ]; then
    find /lib/modules -type f -name '*.ko' -print > "$SNAP/module-paths.txt"
fi
: > "$SNAP/stock-module-metadata.txt"
count=0
while IFS= read -r module; do
    [ -n "$module" ] || continue
    printf '\nmodule: %s\n' "$module" >> "$SNAP/stock-module-metadata.txt"
    if command -v modinfo >/dev/null 2>&1; then
        modinfo "$module" 2>/dev/null | grep -E '^(filename|name|vermagic|depends|srcversion):' >> "$SNAP/stock-module-metadata.txt" || :
    elif command -v strings >/dev/null 2>&1; then
        strings "$module" | grep -E '^(vermagic|depends|srcversion)=' >> "$SNAP/stock-module-metadata.txt" || :
    else
        printf 'No metadata inspection tool available\n' >> "$SNAP/stock-module-metadata.txt"
    fi
    count=$((count + 1))
    [ "$count" -lt 4 ] || break
done < "$SNAP/module-paths.txt"
loadable=false
versioned=false
[ "$(id -u)" -eq 0 ] || { printf 'ERROR: root is required for kernel-symbol capture\n'; exit 1; }
if grep -q '^CONFIG_MODULES=y$' "$SNAP/runtime-kernel.config"; then loadable=true; fi
if grep -q '^CONFIG_MODVERSIONS=y$' "$SNAP/runtime-kernel.config"; then versioned=true; fi
exports=$(grep -c '[[:space:]]__ksymtab_' "$SNAP/runtime-kallsyms.txt" || :)
case "$modules_disabled" in 0|1) ;; *) modules_disabled=unknown ;; esac
printf '{"phase":"kernel_capability_snapshot","loadableModules":%s,"moduleSymbolVersioning":%s,"modulesDisabled":"%s","exportTableEntries":%s,"moduleLoadAttempted":false,"kernelFlashed":false,"vpnStarted":false}\n' "$loadable" "$versioned" "$modules_disabled" "$exports" > "$SNAP/status.json.tmp"
mv "$SNAP/status.json.tmp" "$SNAP/status.json"
printf 'Snapshot complete. No module or VPN was started.\n'
sync
