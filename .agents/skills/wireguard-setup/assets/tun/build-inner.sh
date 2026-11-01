#!/bin/sh
# Build a loadable module only, in an isolated Docker filesystem; never build/flash a kernel image.
set -eu
export LC_ALL=C
cd /work
mkdir -p kernel-build artifacts
python3 - <<'PY'
from pathlib import Path
import shutil
original=Path('device-snapshot/runtime-kernel.config').read_text()
assert 'CONFIG_MODULES=y\n' in original
assert '# CONFIG_MODVERSIONS is not set\n' in original
assert original.count('# CONFIG_TUN is not set')==1
Path('kernel-build/.config').write_text(original.replace('# CONFIG_TUN is not set','CONFIG_TUN=m'))
shutil.copyfile('source/drivers/net/tun.c','module/tun.c')
PY
kmake() {
    make -C /work/source O=/work/kernel-build ARCH=arm CROSS_COMPILE=arm-linux-gnueabihf- \
        'KCFLAGS=-march=armv7-a -mtune=cortex-a9 -mfloat-abi=soft -marm -fno-pie -fno-delete-null-pointer-checks -fno-asynchronous-unwind-tables -fno-unwind-tables -save-temps=obj' \
        'HOSTCFLAGS=-Wall -O2 -fcommon' \
        KBUILD_BUILD_USER=local KBUILD_BUILD_HOST=kindle-tun \
        'KBUILD_BUILD_TIMESTAMP=2026-11-01 00:00:00 UTC' KBUILD_BUILD_VERSION=1 "$@"
}
arm-linux-gnueabihf-gcc --version
kmake oldnoconfig
python3 - <<'PY'
from pathlib import Path
import json,re

def config(path):
 out={}
 for line in Path(path).read_text().splitlines():
  if line.startswith('CONFIG_'):
   k,v=line.split('=',1);out[k]=v
  else:
   m=re.match(r'# (CONFIG_\w+) is not set$',line)
   if m:out[m[1]]='n'
 return out
old=config('device-snapshot/runtime-kernel.config');new=config('kernel-build/.config')
diff={k:[old.get(k),new.get(k)] for k in old.keys()|new.keys() if old.get(k)!=new.get(k)}
Path('artifacts/config-diff.json').write_text(json.dumps(diff,indent=2)+'\n')
print('Configuration differences:',json.dumps(diff))
assert diff=={'CONFIG_TUN':['n','m']}, 'Unexpected config/ABI changes: stop before compiling'
PY
kmake -j2 modules_prepare
python3 - <<'PY'
from pathlib import Path
exports={}
for line in Path('device-snapshot/runtime-kallsyms.txt').read_text().splitlines():
 fields=line.split()
 if len(fields)>=3 and fields[2].startswith('__ksymtab_'):
  name=fields[2][len('__ksymtab_'):]
  owner=fields[3].strip('[]') if len(fields)>3 else 'vmlinux'
  exports[name]=owner
assert len(exports)>1000
# Running kernel has CONFIG_MODVERSIONS=n: no CRCs are consumed. This table
# restricts modpost to symbols actually exported by this exact device snapshot.
Path('kernel-build/Module.symvers').write_text(''.join(f'0x00000000\t{name}\t{owner}\tEXPORT_SYMBOL\n' for name,owner in sorted(exports.items())))
print('Verified runtime export entries:',len(exports))
PY
kmake M=/work/module -j2 modules
arm-linux-gnueabihf-strip --strip-debug module/tun.ko
cp module/tun.ko artifacts/tun.ko
arm-linux-gnueabihf-readelf -p .modinfo artifacts/tun.ko > artifacts/module-metadata.txt
arm-linux-gnueabihf-readelf -h -A artifacts/tun.ko > artifacts/elf-metadata.txt
arm-linux-gnueabihf-nm -u artifacts/tun.ko > artifacts/undefined-symbols.txt
python3 - <<'PY'
from pathlib import Path
import hashlib,json
root=Path('.')
exports={}
for line in Path('device-snapshot/runtime-kallsyms.txt').read_text().splitlines():
 f=line.split()
 if len(f)>=3 and f[2].startswith('__ksymtab_'):
  exports[f[2][len('__ksymtab_'):]]=f[3].strip('[]') if len(f)>3 else 'vmlinux'
imports=[line.split()[-1] for line in Path('artifacts/undefined-symbols.txt').read_text().splitlines() if line.strip()]
missing=sorted(set(imports)-exports.keys())
external={name:exports[name] for name in imports if name in exports and exports[name]!='vmlinux'}
expected='3.0.35-lab126 preempt mod_unload ARMv7 p2v8 '
data=Path('artifacts/tun.ko').read_bytes()
vermagic=[s.decode() for s in data.split(b'\x00') if s.startswith(b'vermagic=')]
assert vermagic==['vermagic='+expected],vermagic
assert not missing,missing
assert not external,external
assert b'license=GPL\x00' in data
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
report={'firmware':'5.13.6 (373199 038)','kernelRelease':'3.0.35-lab126','sourceUrl':'https://kindledownloads.s3.amazonaws.com/Kindle_src_5.13.6_3731990038.tar.gz','sourceArchiveSha256':'4a01245d1bf8724da428dd044bd0e2f6cae0687446b3a2c909dc21a7acc2222f','runtimeConfigSha256':sha('device-snapshot/runtime-kernel.config'),'runtimeSymbolsSha256':sha('device-snapshot/runtime-kallsyms.txt'),'moduleSha256':sha('artifacts/tun.ko'),'tunSourceSha256':sha('module/tun.c'),'vermagic':expected,'symbolVersioning':False,'imports':sorted(imports),'missingRuntimeExports':missing,'externalModuleDependencies':external,'sourceChanges':'GCC attribute/register-variable compatibility headers and restoration of the GPL-omitted stock REAGL Kconfig declaration; TUN driver unmodified','configChanges':{'CONFIG_TUN':['n','m']},'moduleLoadedOnDevice':False,'tunInterfaceTested':False,'vpnTested':False,'autostartInstalled':False}
Path('artifacts/build-manifest.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report,indent=2))
PY
