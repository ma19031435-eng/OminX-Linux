import gzip
import importlib.util
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('bus_archive', ROOT / 'scripts/make-initramfs.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


def entries(packed):
    raw, pos, result = gzip.decompress(packed), 0, {}
    while True:
        fields = [int(raw[pos+6+i*8:pos+14+i*8], 16) for i in range(13)]
        start = pos + 110
        name = raw[start:start + fields[11] - 1].decode()
        data_start = (start + fields[11] + 3) & ~3
        result[name] = (fields, raw[data_start:data_start + fields[6]])
        pos = (data_start + fields[6] + 3) & ~3
        if name == 'TRAILER!!!':
            return result


class DesktopBusTests(unittest.TestCase):
    def test_fixed_packaging_and_account(self):
        binary = Path(os.environ['OMINX_TEST_BINARY']).read_bytes()
        bus = {name: binary for name in ('dbus-daemon', 'ominx-desktop-bus', 'ominx-bus-probe')}
        bus.update({name: b'upstream license' for name in m.BUS_LICENSES})
        plain = entries(m.archive(binary))
        data = entries(m.archive(binary, bus=bus))
        self.assertNotIn('sbin/dbus-daemon', plain)
        self.assertNotIn(b'messagebus:', plain['etc/passwd'][1])
        self.assertIn(b'messagebus:x:81:81:', data['etc/passwd'][1])
        self.assertIn(b'messagebus:!:', data['etc/shadow'][1])
        self.assertEqual(data['var/lib/dbus/machine-id'][1], b'/etc/machine-id')
        self.assertNotIn('etc/machine-id', data)  # never clone a fixed machine identity
        self.assertEqual(data['sbin/ominx-desktop-bus'][0][1], 0o100755)
        self.assertEqual(data['etc/dbus-1/ominx-system.conf'][0][1], 0o100644)
        self.assertNotIn('usr/libexec/dbus-daemon-launch-helper', data)
        self.assertEqual(m.archive(binary, bus=bus), m.archive(binary, bus=bus))

    def test_local_external_only_no_activation(self):
        for kind in ('system', 'session'):
            root = ET.parse(ROOT / 'desktop/bus' / (kind + '.conf')).getroot()
            self.assertEqual([node.text for node in root.findall('auth')], ['EXTERNAL'])
            self.assertTrue(all(node.text.startswith('unix:path=/run/') for node in root.findall('listen')))
            for tag in ('servicedir', 'servicehelper', 'standard_session_servicedirs', 'standard_system_servicedirs', 'allow_anonymous'):
                self.assertIsNone(root.find(tag))
        root = ET.parse(ROOT / 'desktop/bus/system.conf').getroot()
        defaults = root.find("policy[@context='default']")
        self.assertIsNotNone(defaults.find("deny[@own='*']"))
        self.assertIsNotNone(defaults.find("deny[@send_destination='*']"))

    def test_supervisor_refuses_host_and_arguments(self):
        with tempfile.TemporaryDirectory() as directory:
            binary = Path(directory) / 'supervisor'
            subprocess.run(['cc', '-O2', '-Wall', '-Wextra', '-Werror', str(ROOT / 'src/bus/supervisor.c'), '-o', str(binary)], check=True)
            for args in ([], ['arbitrary-command']):
                result = subprocess.run([str(binary), *args], capture_output=True, text=True, timeout=3)
                self.assertEqual(result.returncode, 2)
                self.assertIn('requires root source boot context', result.stderr)
