# input: temporary USB root and KPM release; output: host contract tests; pos: installer tests.
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from types import SimpleNamespace

ENTRY = Path(__file__).resolve().parents[1] / 'install.py'
spec = importlib.util.spec_from_file_location('ocean_install', ENTRY)
installer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(installer)


class HostTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.usb = self.root / 'Kindle'
        self.source = self.root / 'source'
        self.usb.mkdir()
        self.package = self.source / 'kpm/ocean_0.2.1_kindlepw2.kpkg'
        self.package.parent.mkdir(parents=True)
        self.package.write_bytes(b'kpm package fixture')
        install = self.source / installer.INSTALL_SCRIPTLET
        uninstall = self.source / installer.UNINSTALL_SCRIPTLET
        install.parent.mkdir(parents=True, exist_ok=True)
        install.write_text('#!/bin/sh\n# install fixture\n')
        uninstall.write_text('#!/bin/sh\n# uninstall fixture\n')

    def install(self):
        return installer.run('install', self.usb, self.source)

    def test_install_and_reinstall_preserve_user_data(self):
        other = self.usb / 'documents/KOReader.sh'
        account = self.usb / 'ocean/state/weread/session.json'
        save = self.usb / 'games/save.dsg'
        for path in (other, account, save):
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text('keep')
        stale = self.usb / 'ocean-kpm/ocean_0.2.0_kindlepw2.kpkg'
        stale.parent.mkdir(parents=True)
        stale.write_text('old')
        result = self.install()
        self.assertEqual(result['phase'], 'copied')
        self.assertFalse(stale.exists())
        self.assertTrue(installer.run('verify', self.usb, self.source)['ok'])
        self.assertEqual(installer.read_status(self.usb)['phase'], 'awaiting_device_check')
        self.install()
        for path in (other, account, save):
            self.assertEqual(path.read_text(), 'keep')

    def test_incomplete_release_does_not_replace_existing_install(self):
        self.install()
        self.package.unlink()
        with self.assertRaisesRegex(ValueError, '发行包不完整'):
            self.install()
        self.assertTrue((self.usb / 'ocean-kpm/ocean_0.2.1_kindlepw2.kpkg').exists())

    def test_verify_reports_missing_and_mismatch(self):
        result = installer.run('verify', self.usb, self.source)
        self.assertFalse(result['ok'])
        self.assertIn('ocean_0.2.1_kindlepw2.kpkg', result['missing'])
        self.install()
        script = self.usb / 'documents/OceanKPMInstall.sh'
        script.write_text('corrupt')
        result = installer.run('verify', self.usb, self.source)
        self.assertFalse(result['ok'])
        self.assertEqual(result['mismatched'], ['installScriptlet'])

    def test_low_space_is_reported_before_mutation(self):
        with patch.object(installer.shutil, 'disk_usage', return_value=SimpleNamespace(free=0)):
            with self.assertRaisesRegex(ValueError, '空间不足'):
                self.install()
        self.assertFalse((self.usb / 'ocean-kpm/ocean_0.2.1_kindlepw2.kpkg').exists())

    def test_uninstall_copies_kpm_scriptlet_and_preserves_data(self):
        self.install()
        package = self.usb / 'ocean-kpm/ocean_0.2.1_kindlepw2.kpkg'
        account = self.usb / 'ocean/state/weread/session.json'
        account.parent.mkdir(parents=True, exist_ok=True)
        account.write_text('keep')
        result = installer.run('uninstall', self.usb, self.source)
        self.assertEqual(result['phase'], 'uninstall_pending')
        self.assertTrue((self.usb / 'documents/OceanKPMUninstall.sh').exists())
        self.assertTrue(package.exists())
        self.assertEqual(account.read_text(), 'keep')
        self.assertEqual(installer.read_status(self.usb)['phase'], 'uninstall_pending')

    def test_explicit_usb_path_and_json_status(self):
        self.assertEqual(installer.find_kindle(str(self.usb)), self.usb.resolve())
        result = installer.run('status', self.usb, self.source)
        self.assertEqual(json.loads(json.dumps(result))['device']['phase'], 'awaiting_device_check')
        self.assertIn('kpmInstalledVersion', result)
        with self.assertRaises(ValueError):
            installer.find_kindle(str(self.root / 'missing'))


if __name__ == '__main__':
    unittest.main()
