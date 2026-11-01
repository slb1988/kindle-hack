#!/usr/bin/env python3
"""Render reviewed USB overlays; never execute device code or change a kernel.

The bundled automatic path is restricted to the measured PW3/5.13.6 profile.
Use an ignored build/ work directory. Configuration content is never logged.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import ipaddress
import json
import os
from pathlib import Path, PurePosixPath
import re
import struct
import sys
import zipfile

SKILL = Path(__file__).resolve().parents[1]
PROFILE = SKILL / 'profiles/pw3-5.13.6.json'
ASSETS = SKILL / 'assets'


def sha(path: Path) -> str:
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def safe_relative(value: str) -> str:
    path = PurePosixPath(value)
    if not value or path.is_absolute() or '..' in path.parts or '\\' in value:
        raise ValueError('Unsafe relative payload path')
    return str(path)


def substitute(text: str, values: dict[str, str]) -> str:
    def replace(match):
        key = match.group(1)
        if key not in values:
            raise ValueError('Missing template parameter: ' + key)
        value = values[key]
        # All substitutions are hashes, IPv4/CIDR strings, or bracket-dot regexes.
        if not re.fullmatch(r'[a-zA-Z0-9_./\[\]-]*', value):
            raise ValueError('Unsafe template parameter: ' + key)
        return value
    return re.sub(r'@@([A-Z_0-9]+)@@', replace, text)


def validate_snapshot(snapshot: Path, profile: dict) -> dict[str, str]:
    expected = {
        'kernel-release.txt': profile['kernelRelease'],
        'architecture.txt': profile['architecture'],
    }
    for name, value in expected.items():
        if (snapshot / name).read_text().strip() != value:
            raise ValueError('Unsupported device snapshot: ' + name)
    for name, field in [('kernel-version.txt', 'kernelVersionSha256'),
                        ('runtime-kernel.config', 'kernelConfigSha256')]:
        if sha(snapshot / name) != profile[field]:
            raise ValueError('Snapshot does not match the reviewed profile: ' + name)
    return {
        'KERNEL_VERSION_SHA256': profile['kernelVersionSha256'],
        'KERNEL_CONFIG_SHA256': profile['kernelConfigSha256'],
    }


def parse_client(path: Path, peer: str | None) -> dict[str, str]:
    raw = path.read_bytes()
    sections: dict[str, dict[str, str]] = {}
    section = None
    for original in raw.decode('utf-8-sig').splitlines():
        line = original.split('#', 1)[0].strip()
        if not line:
            continue
        if line.startswith('[') and line.endswith(']'):
            section = line[1:-1].lower()
            if section not in ('interface', 'peer') or section in sections:
                raise ValueError('Only one Interface and one Peer are supported')
            sections[section] = {}
            continue
        if section is None or '=' not in line:
            raise ValueError('Malformed WireGuard configuration')
        key, value = (part.strip() for part in line.split('=', 1))
        key = key.lower()
        if key in ('preup', 'postup', 'predown', 'postdown'):
            raise ValueError('Configuration hooks require a separate review')
        if key in sections[section]:
            raise ValueError('Duplicate configuration field: ' + key)
        sections[section][key] = value
    if set(sections) != {'interface', 'peer'}:
        raise ValueError('Interface and Peer are required')
    interface, server = sections['interface'], sections['peer']
    for fields, name in [(interface, 'privatekey'), (server, 'publickey')]:
        try:
            valid = len(base64.b64decode(fields[name], validate=True)) == 32
        except (KeyError, ValueError):
            valid = False
        if not valid:
            raise ValueError('Invalid key field: ' + name)  # Never include its value.
    if server.get('presharedkey'):
        try:
            valid = len(base64.b64decode(server['presharedkey'], validate=True)) == 32
        except ValueError:
            valid = False
        if not valid:
            raise ValueError('Invalid preshared key')
    endpoint = server.get('endpoint', '')
    host, separator, port = endpoint.rpartition(':')
    if not separator or not host or not port.isdigit() or not 1 <= int(port) <= 65535:
        raise ValueError('Peer Endpoint must be host:port')
    try:
        address = ipaddress.IPv4Interface(interface['address'])
        subnet = ipaddress.IPv4Network(server['allowedips'], strict=False)
    except (KeyError, ValueError):
        raise ValueError('This verified test supports one IPv4 address and one IPv4 subnet') from None
    if not subnet.is_private or subnet.prefixlen < 8:
        raise ValueError('Full/internet-wide tunnels are outside the reviewed split-tunnel workflow')
    test_peer = ''
    if peer:
        try:
            candidate = ipaddress.IPv4Address(peer)
        except ValueError:
            raise ValueError('Test peer must be an IPv4 address') from None
        if candidate not in subnet or candidate == address.ip:
            raise ValueError('Test peer must be a different, known host inside AllowedIPs')
        test_peer = str(candidate)
    return {
        'CONFIG_SHA256': hashlib.sha256(raw).hexdigest(),
        'VPN_ADDRESS': str(address.ip),
        'VPN_SUBNET': str(subnet),
        'VPN_SUBNET_REGEX': str(subnet).replace('.', '[.]'),
        'TEST_PEER_IP': test_peer,
    }


def release_files(archive: Path, profile: dict) -> dict[str, bytes]:
    if sha(archive) != profile['release']['zipSha256']:
        raise ValueError('Release ZIP SHA-256 mismatch; do not execute or extract it')
    names = ['kwg', 'main.lua', '_meta.lua', 'kwg-loop.sh']
    with zipfile.ZipFile(archive) as z:
        # Read only known members rather than extracting arbitrary archive paths.
        result = {name: z.read('kwg.koplugin/' + name) for name in names}
    if hashlib.sha256(result['kwg']).hexdigest() != profile['release']['binarySha256']:
        raise ValueError('Release binary SHA-256 mismatch')
    return result


def verify_arm_elf(path: Path, relocatable: bool) -> None:
    data = path.read_bytes()
    if len(data) < 52 or data[:6] != b'\x7fELF\x01\x01':
        raise ValueError('Expected a little-endian 32-bit ELF: ' + path.name)
    kind, machine = struct.unpack_from('<HH', data, 16)
    if machine != 40 or kind != (1 if relocatable else 2):
        raise ValueError('Unexpected ARM ELF type: ' + path.name)
    if not relocatable:
        offset = struct.unpack_from('<I', data, 28)[0]
        size, count = struct.unpack_from('<HH', data, 42)
        if not count or size < 32 or offset + size * count > len(data):
            raise ValueError('Malformed helper program headers')
        if any(struct.unpack_from('<I', data, offset + i * size)[0] == 3 for i in range(count)):
            raise ValueError('TUN helper must be static, not dynamically linked')


class Bundle:
    def __init__(self, out: Path, mode: str):
        self.out = out.resolve()
        if self.out.exists() and any(self.out.iterdir()):
            raise ValueError('Output directory is not empty; preserve it or choose a new build/ directory')
        self.out.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(self.out, 0o700)
        (self.out / '.gitignore').write_text('*\n')
        self.usb = self.out / 'usb'
        self.usb.mkdir()
        self.mode = mode
        self.files: list[dict] = []
        self.prerequisites: list[dict] = []

    def add(self, name: str, data: bytes | str, secret=False):
        name = safe_relative(name)
        data = data.encode() if isinstance(data, str) else data
        path = self.usb / name
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open('xb') as f:
            f.write(data)
        if secret:
            path.chmod(0o600)
        self.files.append({'path': name, 'sha256': hashlib.sha256(data).hexdigest(),
                           'bytes': len(data), 'secret': secret})

    def asset(self, source: str, target: str, values=None):
        data = (ASSETS / source).read_bytes()
        if values is not None:
            data = substitute(data.decode(), values)
        self.add(target, data)

    def prerequisite(self, root: Path, name: str):
        name = safe_relative(name)
        path = root / name
        if not path.is_file() or path.is_symlink():
            raise ValueError('Missing or symlinked prerequisite: ' + name)
        self.prerequisites.append({'path': name, 'sha256': sha(path)})

    def sums(self, target: str, records=None):
        records = self.files + self.prerequisites if records is None else records
        self.add(target, ''.join(r['sha256'] + '  ' + r['path'] + '\n'
                                 for r in records if not r.get('secret')))

    def finish(self):
        manifest = {'schema': 1, 'profile': 'pw3-5.13.6', 'mode': self.mode,
                    'files': self.files, 'prerequisites': self.prerequisites,
                    'deviceExecution': 'not_performed'}
        (self.out / 'bundle.json').write_text(json.dumps(manifest, indent=2) + '\n')
        return manifest


def render(args, profile: dict):
    values = validate_snapshot(args.snapshot, profile) if args.mode != 'preflight' else {}
    client = parse_client(args.config, args.peer_test_ip) if args.mode == 'app' else None
    released = release_files(args.release_zip, profile) if args.mode in ('preflight', 'app') else None
    if args.mode == 'tun' and not args.allow_kernel_module:
        raise ValueError('TUN build/load requires explicit user authorization and --allow-kernel-module')
    b = Bundle(args.out, args.mode)
    if args.mode == 'preflight':
        b.add('kwg-preflight/kwg', released['kwg'])
        for name in ['check.sh', 'tun-snapshot.sh']:
            b.asset('preflight/' + name, 'kwg-preflight/' + name)
        b.asset('preflight/WireGuardCheck.sh', 'documents/WireGuardCheck.sh')
    elif args.mode == 'tun':
        artifacts = args.artifacts
        manifest = json.loads((artifacts / 'build-manifest.json').read_text())
        if (manifest['kernelRelease'] != profile['kernelRelease'] or
                manifest['runtimeConfigSha256'] != values['KERNEL_CONFIG_SHA256'] or
                manifest['sourceArchiveSha256'] != profile['source']['sha256'] or
                manifest['vermagic'] != profile['vermagic'] or
                manifest['missingRuntimeExports'] or manifest['externalModuleDependencies']):
            raise ValueError('Module provenance/ABI verification failed')
        exported = set()
        for line in (args.snapshot / 'runtime-kallsyms.txt').read_text().splitlines():
            fields = line.split()
            if len(fields) == 3 and fields[2].startswith('__ksymtab_'):
                exported.add(fields[2][len('__ksymtab_'):])
        if not manifest['imports'] or not set(manifest['imports']) <= exported:
            raise ValueError('Module imports are not all exported by this running kernel')
        module, probe = artifacts / 'tun.ko', artifacts / 'tun-probe'
        verify_arm_elf(module, True)
        verify_arm_elf(probe, False)
        if sha(module) != manifest['moduleSha256']:
            raise ValueError('Module checksum mismatch')
        if ('vermagic=' + profile['vermagic']).encode() + b'\0' not in module.read_bytes():
            raise ValueError('Module vermagic mismatch')
        values.update(TUN_MODULE_SHA256=sha(module), TUN_PROBE_SHA256=sha(probe))
        b.add('kwg-tun/tun.ko', module.read_bytes())
        b.add('kwg-tun/tun-probe', probe.read_bytes())
        b.asset('tun/load-test.sh.in', 'kwg-tun/load-test.sh', values)
        b.add('kwg-tun/deployment-manifest.json', json.dumps(manifest, indent=2) + '\n')
        b.asset('tun/WireGuardTUNTest.sh', 'documents/WireGuardTUNTest.sh')
    elif args.mode == 'app':
        values.update(client)
        prefix = 'koreader/plugins/kwg.koplugin/'
        for name in ['main.lua', '_meta.lua']:
            b.add(prefix + name, released[name])
        b.add(prefix + 'kwg.bin', released['kwg'])
        b.asset('plugin/kwg-wrapper.sh', prefix + 'kwg')
        b.asset('service/kwg-loop.sh', prefix + 'kwg-loop.sh')
        b.asset('install/install-and-test.sh.in', 'kwg-install/install-and-test.sh', values)
        b.asset('install/WireGuardInstallTest.sh', 'documents/WireGuardInstallTest.sh')
        b.sums('kwg-install/payload.sha256', [r for r in b.files if r['path'].startswith(prefix)])
        if args.include_private_config:
            b.add('kwg-install/client.conf', args.config.read_bytes(), secret=True)
    elif args.mode == 'service':
        root = args.installed_root.resolve()
        prefix = 'koreader/plugins/kwg.koplugin/'
        if sha(root / (prefix + 'kwg.bin')) != profile['release']['binarySha256']:
            raise ValueError('Installed WireGuard binary is not the reviewed release')
        b.asset('service/control.sh.in', 'kwg-service/control.sh', values)
        b.asset('service/kwg.upstart', 'kwg-service/kwg.upstart')
        b.asset('service/kwg-loop.sh', prefix + 'kwg-loop.sh')
        for file in sorted((ASSETS / 'service/scriptlets').glob('*.sh')):
            b.add('documents/' + file.name, file.read_bytes())
        for name in [prefix + n for n in ['kwg', 'kwg.bin', 'main.lua', '_meta.lua']] + [
                'kwg-tun/tun.ko', 'kwg-tun/tun-probe', 'kwg-tun/load-test.sh']:
            b.prerequisite(root, name)
        b.sums('kwg-service/payload.sha256')
        # Flat, public-only inputs for the isolated service test harness.
        for source, dest in [('kwg-service/control.sh', 'control.sh'),
                             ('kwg-service/kwg.upstart', 'kwg.upstart'),
                             (prefix + 'kwg-loop.sh', 'kwg-loop.sh')]:
            (b.out / dest).write_bytes((b.usb / source).read_bytes())
    return b.finish()


def discover_kindle() -> Path:
    candidates = []
    for parent, pattern in [('/Volumes', '*'), ('/media', '*/*'), ('/run/media', '*/*')]:
        for p in Path(parent).glob(pattern):
            version = p / 'system/version.txt'
            if os.path.ismount(p) and (p / 'documents').is_dir() and version.is_file():
                if version.read_bytes()[:64].startswith(b'Kindle'):
                    candidates.append(p.resolve())
    candidates = sorted(set(candidates))
    if len(candidates) != 1:
        raise ValueError('Connect one Kindle in USB file-transfer mode; found ' + str(len(candidates)))
    return candidates[0]


def stage(bundle: Path, kindle: Path):
    root = kindle.resolve()
    if not os.path.ismount(root) or not (root / 'documents').is_dir():
        raise ValueError('Target is not a mounted Kindle userstore')
    manifest = json.loads((bundle / 'bundle.json').read_text())
    allowed = ('kwg-preflight/', 'kwg-tun/', 'kwg-install/', 'kwg-service/',
               'koreader/plugins/kwg.koplugin/', 'documents/WireGuard')
    plan = []
    for record in manifest['prerequisites'] + manifest['files']:
        relative = safe_relative(record['path'])
        if not relative.startswith(allowed):
            raise ValueError('Payload path is outside the WireGuard allowlist')
        target = root / relative
        current = target
        while current != root:
            if current.is_symlink():
                raise ValueError('Symlinked destination is not allowed')
            current = current.parent
        if record in manifest['prerequisites']:
            if not target.is_file() or sha(target) != record['sha256']:
                raise ValueError('Device prerequisite changed: ' + relative)
            continue
        source = bundle / 'usb' / relative
        if (not source.is_file() or source.is_symlink() or
                not source.resolve().is_relative_to((bundle / 'usb').resolve()) or
                sha(source) != record['sha256']):
            raise ValueError('Bundle checksum mismatch: ' + relative)
        if relative.startswith('koreader/') and not (root / 'koreader/plugins').is_dir():
            raise ValueError('Install KOReader before its plugin')
        if target.exists() and (not target.is_file() or sha(target) != record['sha256']):
            raise ValueError('Existing file differs; preserve/inspect before upgrading: ' + relative)
        plan.append((source, target, record))
    copied = 0
    for source, target, record in plan:
        if not target.exists():
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open('xb') as f:
                f.write(source.read_bytes()); f.flush(); os.fsync(f.fileno())
            copied += 1
        if sha(target) != record['sha256']:
            raise ValueError('USB copy verification failed: ' + record['path'])
    receipt = {'kindle': str(root), 'mode': manifest['mode'], 'copiedFiles': copied,
               'verifiedFiles': len(plan), 'deviceExecution': 'awaiting user Scriptlet click'}
    (bundle / 'stage-receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')
    return receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    make = commands.add_parser('render')
    make.add_argument('mode', choices=['preflight', 'tun', 'app', 'service'])
    make.add_argument('--out', type=Path, required=True)
    make.add_argument('--snapshot', type=Path)
    make.add_argument('--release-zip', type=Path)
    make.add_argument('--artifacts', type=Path)
    make.add_argument('--config', type=Path)
    make.add_argument('--peer-test-ip')
    make.add_argument('--include-private-config', action='store_true')
    make.add_argument('--allow-kernel-module', action='store_true')
    make.add_argument('--installed-root', type=Path)
    copy = commands.add_parser('stage')
    copy.add_argument('bundle', type=Path)
    copy.add_argument('--kindle', type=Path)
    args = parser.parse_args()
    try:
        if args.command == 'stage':
            report = stage(args.bundle.resolve(), args.kindle or discover_kindle())
        else:
            required = ['release_zip'] if args.mode == 'preflight' else ['snapshot']
            required += {'tun': ['artifacts'], 'app': ['release_zip', 'config'],
                         'service': ['installed_root']}.get(args.mode, [])
            for field in required:
                if getattr(args, field) is None:
                    raise ValueError('Missing --' + field.replace('_', '-'))
            profile = json.loads(PROFILE.read_text())
            manifest = render(args, profile)
            report = {'out': str(args.out.resolve()), 'mode': args.mode,
                      'files': len(manifest['files']), 'deviceExecution': 'not_performed',
                      'privateConfigIncluded': any(f['secret'] for f in manifest['files'])}
        print(json.dumps(report, indent=2))
    except (ValueError, OSError, KeyError, zipfile.BadZipFile) as error:
        # Do not print raw config, decoder internals, or a traceback containing keys.
        print('WireGuard setup: ' + str(error), file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
