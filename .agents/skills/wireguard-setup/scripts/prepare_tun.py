#!/usr/bin/env python3
"""Prepare the reviewed kernel source/config; never compile or load a module itself."""
from pathlib import Path
import argparse
import json
import os
import shutil
import subprocess
import sys
import tarfile
import urllib.request

from bundle import ASSETS, PROFILE, sha, validate_snapshot


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--snapshot', type=Path, required=True)
    parser.add_argument('--work', type=Path, required=True)
    parser.add_argument('--archive', type=Path, help='An already downloaded official GPL archive')
    parser.add_argument('--allow-kernel-module', action='store_true')
    args = parser.parse_args()
    try:
        if not args.allow_kernel_module:
            raise ValueError('Explicit user authorization for TUN module development is required')
        if sys.version_info < (3, 12):
            raise ValueError('Python 3.12+ is required for safe tar data filtering')
        profile = json.loads(PROFILE.read_text())
        validate_snapshot(args.snapshot, profile)
        work = args.work.resolve()
        if work.exists() and any(work.iterdir()):
            raise ValueError('Work directory must be empty; preserve existing artifacts')
        work.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(work, 0o700)
        if shutil.disk_usage(work).free < 2 * 1024**3:
            raise ValueError('Less than 2 GiB free: stop and clean reproducible intermediates first')
        (work / '.gitignore').write_text('*\n')
        archive = args.archive.resolve() if args.archive else work / 'gpl-source.tar.gz'
        source = profile['source']
        if args.archive is None:
            temporary = archive.with_suffix('.part')
            with urllib.request.urlopen(source['url'], timeout=60) as response, temporary.open('xb') as output:
                copied = 0
                while data := response.read(1024 * 1024):
                    copied += len(data)
                    if copied > source['bytes']:
                        raise ValueError('GPL download exceeded the pinned size')
                    output.write(data)
            if copied != source['bytes'] or sha(temporary) != source['sha256']:
                raise ValueError('GPL download checksum/size mismatch; do not extract')
            temporary.rename(archive)
        if archive.stat().st_size != source['bytes'] or sha(archive) != source['sha256']:
            raise ValueError('GPL archive does not match the reviewed firmware release')
        nested = work / 'kernel-source.tar.gz'
        with tarfile.open(archive, 'r:gz') as outer:
            member = outer.getmember(source['kernelMember'])
            if not member.isfile():
                raise ValueError('Unexpected kernel archive member type')
            with outer.extractfile(member) as stream, nested.open('xb') as output:
                shutil.copyfileobj(stream, output)
        kernel = work / 'source'
        kernel.mkdir()
        with tarfile.open(nested, 'r:gz') as inner:
            inner.extractall(kernel, filter='data')
        subprocess.run(['patch', '--dry-run', '-p1', '-i', str(ASSETS / 'tun/source-compat.patch')],
                       cwd=kernel, check=True)
        subprocess.run(['patch', '-p1', '-i', str(ASSETS / 'tun/source-compat.patch')],
                       cwd=kernel, check=True)
        # Do not let an enclosing Git checkout append '+' to the kernel release.
        (kernel / '.scmversion').write_text('')
        snapshot = work / 'device-snapshot'
        snapshot.mkdir()
        for name in ['runtime-kernel.config', 'runtime-kallsyms.txt', 'kernel-version.txt',
                     'kernel-release.txt', 'architecture.txt', 'stock-module-metadata.txt']:
            shutil.copyfile(args.snapshot / name, snapshot / name)
            (snapshot / name).chmod(0o600)
        (work / 'module').mkdir()
        shutil.copyfile(ASSETS / 'tun/Makefile', work / 'module/Makefile')
        shutil.copyfile(ASSETS / 'tun/build-inner.sh', work / 'build-inner.sh')
        shutil.copyfile(ASSETS / 'tun/tun-probe.c', work / 'tun-probe.c')
        receipt = {'profile': profile['id'], 'sourceUrl': source['url'],
                   'sourceArchiveSha256': sha(archive),
                   'patchSha256': sha(ASSETS / 'tun/source-compat.patch'),
                   'runtimeConfigSha256': sha(snapshot / 'runtime-kernel.config'),
                   'kernelCompiled': False, 'moduleCompiled': False, 'deviceTouched': False}
        (work / 'source-receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')
        print(json.dumps({'work': str(work), 'profile': profile['id'],
                          'next': 'Follow references/tun-build.md: build only the module and static probe'}, indent=2))
    except (ValueError, OSError, KeyError, tarfile.TarError, subprocess.CalledProcessError) as error:
        print('TUN source preparation: ' + str(error), file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
