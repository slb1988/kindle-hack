#!/usr/bin/env python3
# input: KPM package release and mounted Kindle; output: USB package/scriptlet install and status; pos: host entry.
"""Copy the KPM package and one-tap installer; no SSH, compiler or device configuration needed."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import sqlite3
import sys

PACKAGE_DIR = 'kpm'
INSTALL_SCRIPTLET = 'scriptlets/OceanKPMInstall.sh'
UNINSTALL_SCRIPTLET = 'scriptlets/OceanKPMUninstall.sh'
NEXT = '安全弹出 Kindle → 拔下 USB → 打开图书库中的 Ocean KPM Install → 完成后重新连接 USB'
UNINSTALL_NEXT = '安全弹出 Kindle → 拔下 USB → 打开图书库中的 Ocean KPM Uninstall'


def sha256(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def release_source(explicit=None):
    if explicit:
        return Path(explicit).expanduser().resolve()
    here = Path(__file__).resolve().parent
    for candidate in (here, here.parent):
        if (candidate / PACKAGE_DIR).is_dir():
            return candidate
    return here.parent


def find_kindle(explicit=None):
    if explicit:
        target = Path(explicit).expanduser().resolve()
        if not target.is_dir():
            raise ValueError(f'Kindle 目录不存在：{target}')
        return target
    candidates = [Path('/Volumes/Kindle')]
    for base in (Path('/media'), Path('/run/media'), Path('/mnt')):
        if base.is_dir():
            candidates.extend(base.glob('*/Kindle'))
            candidates.append(base / 'Kindle')
    found = sorted({p.resolve() for p in candidates if p.is_dir()})
    if len(found) != 1:
        raise ValueError('请指定 Kindle USB 根目录：python3 installer/install.py --kindle /Volumes/Kindle')
    return found[0]


def find_package(source):
    packages = sorted((source / PACKAGE_DIR).glob('*.kpkg'))
    if len(packages) != 1:
        raise ValueError(f'发行包应恰好包含一个 {PACKAGE_DIR}/*.kpkg，当前找到 {len(packages)} 个')
    return packages[0]


def missing_files(source):
    missing = []
    try:
        find_package(source)
    except ValueError:
        missing.append(f'{PACKAGE_DIR}/*.kpkg')
    for name in (INSTALL_SCRIPTLET, UNINSTALL_SCRIPTLET):
        if not (source / name).is_file():
            missing.append(name)
    return missing


def read_status(kindle):
    path = kindle / 'ocean/state/status.json'
    if path.is_file():
        return json.loads(path.read_text())
    return {'phase': 'awaiting_device_check'}


def installed_version(kindle):
    database = kindle / 'kmc/kpm/kpm.db'
    if not database.is_file():
        return None
    try:
        connection = sqlite3.connect(f'file:{database}?mode=ro', uri=True)
        try:
            row = connection.execute(
                "select version_major, version_minor, version_patch from installed_packages where id='ocean'"
            ).fetchone()
            return '.'.join(str(part) for part in row) if row else None
        finally:
            connection.close()
    except sqlite3.Error:
        return 'unknown'


def copy_verified(source, target):
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)
    if sha256(source) != sha256(target):
        target.unlink(missing_ok=True)
        raise ValueError(f'复制后校验失败：{target.name}')


def run(command, kindle, source, progress=False):
    source = source.resolve()
    if command in ('install', 'verify'):
        missing = missing_files(source)
        if missing:
            raise ValueError('发行包不完整：' + ', '.join(missing))
    if command == 'uninstall' and not (source / UNINSTALL_SCRIPTLET).is_file():
        raise ValueError('发行包不完整：' + UNINSTALL_SCRIPTLET)
    package = find_package(source) if (source / PACKAGE_DIR).is_dir() else None
    package_target = kindle / 'ocean-kpm' / package.name if package else None
    install_script = source / INSTALL_SCRIPTLET
    uninstall_script = source / UNINSTALL_SCRIPTLET

    if command == 'install':
        size = package.stat().st_size + install_script.stat().st_size
        if size > shutil.disk_usage(kindle).free:
            raise ValueError(f'Kindle 空间不足：需要 {size // 1048576 + 1} MiB')
        package_target.parent.mkdir(parents=True, exist_ok=True)
        for old in package_target.parent.glob('ocean_*.kpkg'):
            if old != package_target:
                old.unlink()
        if progress:
            print(f'正在复制 {size // 1048576 + 1} MiB 到 {kindle}', file=sys.stderr, flush=True)
        copy_verified(package, package_target)
        copy_verified(install_script, kindle / 'documents/OceanKPMInstall.sh')
        state = kindle / 'ocean/state'
        state.mkdir(parents=True, exist_ok=True)
        (state / 'status.json').write_text('{"phase":"awaiting_device_check"}\n')
        return {'phase': 'copied', 'kindle': str(kindle), 'package': package.name,
                'sha256': sha256(package_target), 'kpmInstalledVersion': installed_version(kindle),
                'next': NEXT}

    if command == 'uninstall':
        copy_verified(uninstall_script, kindle / 'documents/OceanKPMUninstall.sh')
        state = kindle / 'ocean/state'
        state.mkdir(parents=True, exist_ok=True)
        (state / 'status.json').write_text('{"phase":"uninstall_pending"}\n')
        return {'phase': 'uninstall_pending', 'next': UNINSTALL_NEXT,
                'preserved': ['ocean', 'games', 'weread-offline']}

    result = {'kindle': str(kindle), 'device': read_status(kindle),
              'kpmInstalledVersion': installed_version(kindle)}
    if command == 'verify':
        expected = {'package': sha256(package), 'installScriptlet': sha256(install_script)}
        actual = {}
        missing = []
        if not package_target.is_file():
            missing.append(package.name)
        else:
            actual['package'] = sha256(package_target)
        target_script = kindle / 'documents/OceanKPMInstall.sh'
        if not target_script.is_file():
            missing.append('documents/OceanKPMInstall.sh')
        else:
            actual['installScriptlet'] = sha256(target_script)
        mismatched = [name for name, digest in expected.items()
                      if name in actual and actual[name] != digest]
        result.update({'package': package.name, 'expected': expected, 'actual': actual,
                       'missing': missing, 'mismatched': mismatched,
                       'ok': not missing and not mismatched, 'next': NEXT})
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', nargs='?', default='install',
                        choices=['install', 'status', 'verify', 'uninstall'])
    parser.add_argument('--kindle')
    parser.add_argument('--source', help=argparse.SUPPRESS)
    parser.add_argument('--json', action='store_true')
    args = parser.parse_args()
    try:
        result = run(args.command, find_kindle(args.kindle), release_source(args.source), progress=True)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        if not args.json and 'next' in result:
            print(result['next'])
        return 1 if result.get('ok') is False else 0
    except (ValueError, OSError, json.JSONDecodeError) as error:
        print(json.dumps({'error': str(error)}, ensure_ascii=False), file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
