#!/usr/bin/env python3
# input: public runtime, games and KPM launcher; output: USB-ready ZIP, KPM package and source bundle; pos: release packaging.
from pathlib import Path
import argparse
import hashlib
import json
import shutil
import subprocess
import tarfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]
BUILD = ROOT / 'build'
PACKAGE_ID = 'ocean'
PACKAGE_PLATFORM = 'kindlepw2'


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def copy(source, target):
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)


def numeric_version(version):
    base = version.lstrip('v').split('-', 1)[0]
    parts = [int(part) for part in base.split('.')]
    if len(parts) != 3:
        raise ValueError(f'版本需为 vMAJOR.MINOR.PATCH-*：{version}')
    return parts


def write(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding='utf-8', newline='\n')


def make_kpkg(source, target):
    target.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(target, 'w:gz', compresslevel=6) as tar:
        for path in sorted(source.rglob('*')):
            tar.add(path, path.relative_to(source))


def install_scriptlet(package_name, digest):
    return f'''#!/bin/sh
# Name: Ocean KPM Install
# Author: kindle-hack

LOG=/mnt/us/ocean-kpm-install.log
TMP=/tmp/ocean-kpm-install.out
PKG=/mnt/us/ocean-kpm/{package_name}
KPM=/var/local/kmc/bin/kpm
EXPECTED_SHA256={digest}

say() {{
    printf '%s\n' "$*"
    printf '%s\n' "$*" >> "$LOG"
}}

run() {{
    say ""
    say ">>> $*"
    "$@" > "$TMP" 2>&1
    rc=$?
    cat "$TMP" >> "$LOG"
    cat "$TMP"
    say "<<< exit=$rc"
    return "$rc"
}}

finish() {{
    msg="$1"
    say "$msg"
    if [ -x /mnt/us/libkh/bin/fbink ]; then
        /mnt/us/libkh/bin/fbink -q -y -5 "$msg" >/dev/null 2>&1 || true
    fi
    sync
}}

: > "$LOG"
say "Ocean KPM Install"
say "================="
say "Started: $(date 2>/dev/null || echo unknown)"

if [ ! -x "$KPM" ]; then
    finish "ERROR: KPM was not found at $KPM"
    exit 20
fi
if [ ! -f "$PKG" ]; then
    finish "ERROR: package not found: $PKG"
    exit 21
fi
if command -v sha256sum >/dev/null 2>&1; then
    ACTUAL_SHA256=$(sha256sum "$PKG" | awk '{{print $1}}')
    say "Package SHA-256: $ACTUAL_SHA256"
    if [ "$ACTUAL_SHA256" != "$EXPECTED_SHA256" ]; then
        finish "ERROR: package checksum mismatch"
        exit 22
    fi
else
    say "sha256sum unavailable; archive integrity will be checked by KPM/libarchive."
fi

if ! run "$KPM" -y uninstall ocean; then
    say "No existing Ocean package was removed; continuing."
fi
if ! run "$KPM" -y install "file://$PKG"; then
    finish "ERROR: KPM could not install Ocean"
    exit 23
fi
if [ ! -f /mnt/us/kmc/kpm/packages/ocean/manifest.json ]; then
    finish "ERROR: KPM install ended without Ocean package files"
    exit 24
fi
if ! run "$KPM" launch ocean check; then
    finish "ERROR: Ocean installed, but device check failed"
    exit 25
fi
if [ -d /mnt/us/extensions/ocean ]; then
    rm -rf /mnt/us/extensions/ocean
    say "Removed duplicate legacy USB extension copy."
fi

finish "OK: Ocean installed with KPM and device check completed."
exit 0
'''


def uninstall_scriptlet():
    return '''#!/bin/sh
# Name: Ocean KPM Uninstall
# Author: kindle-hack

LOG=/mnt/us/ocean-kpm-uninstall.log
TMP=/tmp/ocean-kpm-uninstall.out
KPM=/var/local/kmc/bin/kpm

say() {
    printf '%s\n' "$*"
    printf '%s\n' "$*" >> "$LOG"
}

: > "$LOG"
say "Ocean KPM Uninstall"
say "==================="
"$KPM" -y uninstall ocean > "$TMP" 2>&1
rc=$?
cat "$TMP" >> "$LOG"
cat "$TMP"
if [ "$rc" = 0 ]; then
    mkdir -p /mnt/us/ocean/state
    printf '{"phase":"uninstalled","dataPreserved":true}\n' > /mnt/us/ocean/state/status.json
    say "OK: Ocean removed; account data and saved games preserved."
else
    say "ERROR: KPM uninstall failed."
fi
sync
exit "$rc"
'''


def package(version):
    out = BUILD / 'release'
    stage = out / 'kindle-hack-ai-kit'
    package_stage = out / 'kpm-package'
    for path in (stage, package_stage):
        if path.exists():
            shutil.rmtree(path)
        path.mkdir(parents=True)

    package_version = numeric_version(version)
    package_name = f'{PACKAGE_ID}_{".".join(map(str, package_version))}_{PACKAGE_PLATFORM}.kpkg'
    manifest = {
        'manifest_version': 2,
        'id': PACKAGE_ID,
        'name': 'Ocean',
        'author': 'OceanJy333',
        'description': 'WeChat Read and game payload packaged for WinterBreak2/KPM.',
        'version': package_version,
        'dependencies': [],
        'supported_platforms': [PACKAGE_PLATFORM],
    }
    write(package_stage / 'manifest.json', json.dumps(manifest, ensure_ascii=False, indent=2) + '\n')
    for name in ('install.sh', 'launch.sh', 'uninstall.sh'):
        copy(ROOT / 'installer/kpm' / name, package_stage / name)
    shutil.copytree(ROOT / 'installer/kpm/scriptlets', package_stage / 'scriptlets')
    shutil.copytree(ROOT / 'installer/device/bin', package_stage / 'bin')
    copy(BUILD / 'installer/device-probe', package_stage / 'bin/device-probe')
    shutil.copytree(BUILD / 'weread/native-runtime/public-runtime', package_stage / 'payload/runtime')
    for folder, names in [('doom', ['doom-voyage', 'overlay.gray']),
                          ('arcade', ['arcade-voyage', 'overlay.gray', 'missing.gray'])]:
        for name in names:
            copy(BUILD / folder / name, package_stage / 'payload/games' / folder / name)
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    write(package_stage / 'RELEASE', f'source_commit={revision}\nversion={version}\n')

    kpkg = out / package_name
    make_kpkg(package_stage, kpkg)
    digest = sha(kpkg)
    copy(kpkg, stage / 'kpm' / package_name)
    write(stage / 'scriptlets/OceanKPMInstall.sh', install_scriptlet(package_name, digest))
    write(stage / 'scriptlets/OceanKPMUninstall.sh', uninstall_scriptlet())
    copy(ROOT / 'installer/install.py', stage / 'install.py')

    guide = (ROOT / 'docs/给AI的安装任务.md').read_text()
    write(stage / '给AI的安装任务.md', guide.replace('(../README.md', '(README.md'))
    copy(ROOT / 'README.md', stage / 'README.md')
    for name in ['AGENTS.md', 'BUILD.md', 'docs/setup.md', 'docs/给AI的安装任务.md', 'docs/release-validation.md',
                 '.agents/skills/kindle-setup/SKILL.md', 'weread/BUILD.md', 'system/BUILD.md']:
        copy(ROOT / name, stage / name)
    copy(ROOT / 'LICENSE', stage / 'LICENSE')
    copy(ROOT / 'THIRD_PARTY_NOTICES.md', stage / 'THIRD_PARTY_NOTICES.md')
    shutil.copytree(ROOT / 'LICENSES', stage / 'LICENSES')
    write(stage / '源码与许可.txt',
          '对应源码附件：kindle-hack-sources.tar.gz。\n'
          'Qt/系统库的固定来源与获取方法见源码内 weread/BUILD.md 和 runtime/licenses。\n'
          'KPM 包包含动态运行库。账号、书籍、WAD、ROM 和 BIOS 不包含在发布包中。\n')
    entries = {str(p.relative_to(stage)): sha(p) for p in sorted(stage.rglob('*')) if p.is_file()}
    release_manifest = {'version': version, 'sourceRevision': revision,
                        'packageManager': 'KPM', 'package': {'file': f'kpm/{package_name}', 'sha256': digest},
                        'privateAssetsIncluded': False, 'logicalCanvas': [1072, 1448],
                        'profiles': {'pw1': {'reader': False, 'games': 'device-probe-required'},
                                     'pw2': {'reader': 'device-probe-required', 'games': 'device-probe-required'},
                                     'pw3': {'reader': 'device-probe-required', 'games': 'device-probe-required'},
                                     'voyage': {'reader': 'device-probe-required', 'games': 'device-probe-required'}},
                        'hardwareValidation': 'pending', 'files': entries}
    write(stage / 'manifest.json', json.dumps(release_manifest, ensure_ascii=False, indent=2) + '\n')
    archive = out / 'kindle-hack-ai-kit.zip'
    with zipfile.ZipFile(archive, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for path in sorted(stage.rglob('*')):
            if path.is_file():
                z.write(path, path.relative_to(stage))
    sources = out / 'kindle-hack-sources.tar.gz'
    tracked = subprocess.check_output(['git', 'ls-files', '-z'], cwd=ROOT).decode().split('\0')
    with tarfile.open(sources, 'w:gz', compresslevel=6) as tar:
        for name in tracked:
            if name and (ROOT / name).is_file():
                tar.add(ROOT / name, 'kindle-hack/' + name)
        for name in ['doom/doomgeneric.tar.gz', 'arcade/fba-source.tar.gz',
                     'native-deps/zlib.tar.gz', 'weread/native-runtime/glibc-2.39.tar.xz',
                     'weread/native-runtime/packages.sha256']:
            tar.add(BUILD / name, 'kindle-hack/build/' + name)
        tar.add(BUILD / 'weread/runtime-sources', 'kindle-hack/build/weread/runtime-sources')
    checksum = out / 'SHA256SUMS'
    checksum.write_text(''.join(f'{sha(p)}  {p.name}\n' for p in [archive, sources, kpkg]))
    print(json.dumps({'archive': str(archive), 'bytes': archive.stat().st_size,
                      'sha256': sha(archive), 'kpkg': str(kpkg), 'kpkgSha256': digest,
                      'sources': str(sources)}, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--version', default='v0.2.1-ai-kit')
    package(parser.parse_args().version)
