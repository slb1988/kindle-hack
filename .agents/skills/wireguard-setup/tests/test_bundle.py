from __future__ import annotations

import argparse
import base64
import copy
import hashlib
import json
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import bundle as b


class BundleTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='wireguard-skill-test-')
        self.root = Path(self.tmp.name)
        self.profile = json.loads(b.PROFILE.read_text())
        self.snapshot = self.root / 'snapshot'
        self.snapshot.mkdir()
        inputs = {
            'kernel-release.txt': self.profile['kernelRelease'] + '\n',
            'architecture.txt': 'armv7l\n',
            'kernel-version.txt': 'synthetic kernel build for host-only tests\n',
            'runtime-kernel.config': 'CONFIG_MODULES=y\n# CONFIG_MODVERSIONS is not set\n# CONFIG_TUN is not set\n',
            'runtime-kallsyms.txt': '00000000 r __ksymtab_test_export\n',
        }
        for name, text in inputs.items():
            (self.snapshot / name).write_text(text)
        self.profile['kernelVersionSha256'] = b.sha(self.snapshot / 'kernel-version.txt')
        self.profile['kernelConfigSha256'] = b.sha(self.snapshot / 'runtime-kernel.config')
        self.archive = self.root / 'release.zip'
        self.binary = b'synthetic release binary, never executed'
        with zipfile.ZipFile(self.archive, 'w') as z:
            for name, value in [('kwg', self.binary), ('main.lua', b'-- fixture'),
                                ('_meta.lua', b'-- fixture'), ('kwg-loop.sh', b'#!/bin/sh\n')]:
                z.writestr('kwg.koplugin/' + name, value)
            z.writestr('../not-extracted.txt', 'not extracted')
        self.profile['release']['zipSha256'] = b.sha(self.archive)
        self.profile['release']['binarySha256'] = hashlib.sha256(self.binary).hexdigest()
        self.config = self.root / 'client.conf'
        self.private = base64.b64encode(bytes([1]) * 32).decode()
        self.public = base64.b64encode(bytes([2]) * 32).decode()
        self.config.write_text(
            '[Interface]\nPrivateKey = ' + self.private + '\nAddress = 10.42.0.8/24\nDNS = 192.0.2.53\n'
            '[Peer]\nPublicKey = ' + self.public + '\nEndpoint = vpn.example.invalid:51820\n'
            'AllowedIPs = 10.42.0.0/24\nPersistentKeepalive = 25\n')

    def tearDown(self):
        self.tmp.cleanup()

    def args(self, mode, **extra):
        values = dict(mode=mode, out=self.root / (mode + '-bundle'), snapshot=self.snapshot,
                      release_zip=self.archive, artifacts=None, config=self.config,
                      peer_test_ip='10.42.0.5', include_private_config=False,
                      allow_kernel_module=False, installed_root=None)
        values.update(extra)
        return argparse.Namespace(**values)

    def test_valid_config_parameters_are_redacted(self):
        result = b.parse_client(self.config, '10.42.0.5')
        self.assertEqual(result['VPN_ADDRESS'], '10.42.0.8')
        self.assertEqual(result['VPN_SUBNET_REGEX'], '10[.]42[.]0[.]0/24')
        self.assertNotIn(self.private, json.dumps(result))
        self.assertNotIn(self.public, json.dumps(result))

    def test_invalid_key_is_not_echoed(self):
        secret = 'DO_NOT_ECHO_THIS_INVALID_PRIVATE_KEY'
        self.config.write_text(self.config.read_text().replace(self.private, secret))
        with self.assertRaises(ValueError) as caught:
            b.parse_client(self.config, None)
        self.assertNotIn(secret, str(caught.exception))

    def test_full_tunnel_hooks_multiple_peers_and_ipv6_are_rejected(self):
        original = self.config.read_text()
        mutations = [original.replace('10.42.0.0/24', '0.0.0.0/0'),
                     original + 'PostUp = do-not-execute\n',
                     original + '[Peer]\nPublicKey = duplicate\n',
                     original.replace('10.42.0.8/24', 'fd00::8/128')]
        for content in mutations:
            with self.subTest(content=content[:11]):
                self.config.write_text(content)
                with self.assertRaises(ValueError):
                    b.parse_client(self.config, None)

    def test_test_peer_must_be_an_owned_target_in_vpn_subnet(self):
        for peer in ['198.51.100.1', '10.42.0.8', 'not-an-ip']:
            with self.subTest(peer=peer), self.assertRaises(ValueError):
                b.parse_client(self.config, peer)
        self.assertEqual(b.parse_client(self.config, None)['TEST_PEER_IP'], '')

    def test_template_unknown_and_shell_injection_rejected(self):
        with self.assertRaises(ValueError):
            b.substitute('@@MISSING@@', {})
        with self.assertRaises(ValueError):
            b.substitute('@@VALUE@@', {'VALUE': "'; touch /tmp/not-allowed; '"})
        self.assertEqual(b.substitute('@@VALUE@@', {'VALUE': '10[.]42[.]0[.]0/24'}), '10[.]42[.]0[.]0/24')

    def test_snapshot_mismatch_rejected_before_output(self):
        (self.snapshot / 'runtime-kernel.config').write_text('different configuration\n')
        args = self.args('app')
        with self.assertRaises(ValueError):
            b.render(args, self.profile)
        self.assertFalse(args.out.exists())

    def test_release_integrity_and_no_archive_path_extraction(self):
        args = self.args('preflight')
        manifest = b.render(args, self.profile)
        self.assertEqual(len(manifest['files']), 4)
        self.assertFalse((self.root / 'not-extracted.txt').exists())
        broken = copy.deepcopy(self.profile)
        broken['release']['zipSha256'] = '0' * 64
        with self.assertRaises(ValueError):
            b.release_files(self.archive, broken)

    def test_app_template_contains_no_private_key_without_opt_in(self):
        args = self.args('app', peer_test_ip=None)
        manifest = b.render(args, self.profile)
        self.assertFalse(any(r['secret'] for r in manifest['files']))
        self.assertFalse((args.out / 'usb/kwg-install/client.conf').exists())
        source = (args.out / 'usb/kwg-install/install-and-test.sh').read_text()
        self.assertNotIn('@@', source)
        self.assertNotIn(self.private, source)
        self.assertIn('ping_result=not_requested', source)
        self.assertIn('10[.]42[.]0[.]0/24', source)
        subprocess.run(['/bin/sh', '-n', str(args.out / 'usb/kwg-install/install-and-test.sh')], check=True)

    def test_private_config_opt_in_is_exact_and_restricted(self):
        args = self.args('app', include_private_config=True)
        manifest = b.render(args, self.profile)
        copied = args.out / 'usb/kwg-install/client.conf'
        self.assertEqual(copied.read_bytes(), self.config.read_bytes())
        self.assertEqual(copied.stat().st_mode & 0o777, 0o600)
        self.assertEqual(args.out.stat().st_mode & 0o777, 0o700)
        self.assertEqual([r['path'] for r in manifest['files'] if r['secret']], ['kwg-install/client.conf'])

    def test_kernel_module_needs_explicit_authorization(self):
        with self.assertRaisesRegex(ValueError, 'authorization'):
            b.render(self.args('tun'), self.profile)

    @staticmethod
    def elf(kind=2, interpreter=False):
        data = bytearray(84 if kind == 2 else 52)
        data[:6] = b'\x7fELF\x01\x01'
        struct.pack_into('<HH', data, 16, kind, 40)
        if kind == 2:
            struct.pack_into('<I', data, 28, 52)
            struct.pack_into('<HH', data, 42, 32, 1)
            struct.pack_into('<I', data, 52, 3 if interpreter else 1)
        return bytes(data)

    def test_dynamic_helper_is_rejected(self):
        helper = self.root / 'helper'
        helper.write_bytes(self.elf(interpreter=True))
        with self.assertRaisesRegex(ValueError, 'static'):
            b.verify_arm_elf(helper, False)
        helper.write_bytes(self.elf())
        b.verify_arm_elf(helper, False)

    def test_tun_artifact_provenance_and_runtime_exports(self):
        artifacts = self.root / 'artifacts'
        artifacts.mkdir()
        module = artifacts / 'tun.ko'
        module.write_bytes(self.elf(1) + ('vermagic=' + self.profile['vermagic']).encode() + b'\0license=GPL\0')
        (artifacts / 'tun-probe').write_bytes(self.elf())
        manifest = {'kernelRelease': self.profile['kernelRelease'],
                    'runtimeConfigSha256': self.profile['kernelConfigSha256'],
                    'sourceArchiveSha256': self.profile['source']['sha256'],
                    'vermagic': self.profile['vermagic'], 'missingRuntimeExports': [],
                    'externalModuleDependencies': {}, 'imports': ['test_export'],
                    'moduleSha256': b.sha(module)}
        (artifacts / 'build-manifest.json').write_text(json.dumps(manifest))
        args = self.args('tun', artifacts=artifacts, allow_kernel_module=True)
        b.render(args, self.profile)
        script = (args.out / 'usb/kwg-tun/load-test.sh').read_text()
        self.assertNotIn('@@', script)
        self.assertIn(b.sha(module), script)
        subprocess.run(['/bin/sh', '-n', str(args.out / 'usb/kwg-tun/load-test.sh')], check=True)
        manifest['imports'].append('missing_export')
        (artifacts / 'build-manifest.json').write_text(json.dumps(manifest))
        with self.assertRaisesRegex(ValueError, 'exported'):
            b.render(self.args('tun', out=self.root/'tun-bad', artifacts=artifacts, allow_kernel_module=True), self.profile)

    def test_stage_mount_gate_idempotency_and_conflict_preflight(self):
        args = self.args('preflight')
        b.render(args, self.profile)
        kindle = self.root / 'Kindle'
        (kindle / 'documents').mkdir(parents=True)
        with self.assertRaisesRegex(ValueError, 'mounted'):
            b.stage(args.out, kindle)
        with patch.object(b.os.path, 'ismount', return_value=True):
            first = b.stage(args.out, kindle)
            second = b.stage(args.out, kindle)
            self.assertEqual(first['copiedFiles'], 4)
            self.assertEqual(second['copiedFiles'], 0)
            entry = kindle / 'documents/WireGuardCheck.sh'
            entry.write_text('user changed this file\n')
            (kindle / 'kwg-preflight/kwg').unlink()
            with self.assertRaisesRegex(ValueError, 'differs'):
                b.stage(args.out, kindle)
            self.assertEqual(entry.read_text(), 'user changed this file\n')
            self.assertFalse((kindle / 'kwg-preflight/kwg').exists())

    def test_stage_rejects_escape_and_symlinked_destination(self):
        args = self.args('preflight')
        b.render(args, self.profile)
        kindle = self.root / 'Kindle'
        (kindle / 'documents').mkdir(parents=True)
        with patch.object(b.os.path, 'ismount', return_value=True):
            external = self.root / 'external'
            external.mkdir()
            (kindle / 'kwg-preflight').symlink_to(external, target_is_directory=True)
            with self.assertRaisesRegex(ValueError, 'Symlinked'):
                b.stage(args.out, kindle)
            self.assertEqual(list(external.iterdir()), [])
            (kindle / 'kwg-preflight').unlink()
            manifest = json.loads((args.out / 'bundle.json').read_text())
            manifest['files'][0]['path'] = '../escape'
            (args.out / 'bundle.json').write_text(json.dumps(manifest))
            with self.assertRaisesRegex(ValueError, 'Unsafe'):
                b.stage(args.out, kindle)


if __name__ == '__main__':
    unittest.main()
