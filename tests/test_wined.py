"""Per-user Windows service: first-login background setup, persistent
wineserver, Proton prefix precreation and refusal of unsuitable files.

The host-test daemon runs against a stub runtime whose fake `wine` logs
every invocation. That proves the service behavior; it never claims that
the stub is Wine. The real source-built runtime is packaged separately
(docs/windows-compatibility.md)."""
import os
from pathlib import Path
import socket
import struct
import subprocess
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]
WINED = os.environ.get('OMINX_WINED_BINARY', str(ROOT / 'build/host/ominx-wined-test'))
WINSETUP = os.environ.get('OMINX_WINSETUP_BINARY', str(ROOT / 'build/host/ominx-winsetup-test'))
WIN = os.environ.get('OMINX_WIN_BINARY', str(ROOT / 'build/host/ominx-win'))


def pe_image(machine=0x8664, bits=64, dll=False):
    data = bytearray(1024)
    data[0:2] = b'MZ'
    struct.pack_into('<I', data, 0x3c, 128)
    data[128:132] = b'PE\0\0'
    struct.pack_into('<H', data, 132, machine)
    struct.pack_into('<H', data, 134, 1)
    struct.pack_into('<H', data, 148, 240 if bits == 64 else 224)
    struct.pack_into('<H', data, 150, 0x2000 if dll else 0x0022)
    struct.pack_into('<H', data, 152, 0x20b if bits == 64 else 0x10b)
    struct.pack_into('<H', data, 152 + 68, 2)
    struct.pack_into('<I', data, 152 + (108 if bits == 64 else 92), 16)
    return bytes(data)


def make_runtime(root, log, fail_wineboot=False):
    runtime = root / 'runtime'
    (runtime / 'bin').mkdir(parents=True)
    (runtime / 'share/dxvk/x64').mkdir(parents=True)
    (runtime / 'share/dxvk/x64/d3d11.dll').write_bytes(b'FAKE-D3D11')
    (runtime / 'VERSION').write_text('wine-10.0-ominx-test\n')
    wine = runtime / 'bin/wine'
    wine.write_text(f'''#!/bin/sh
printf 'CWD=%s PREFIX=%s STEAM=%s ARGS=%s\\n' "$PWD" "$WINEPREFIX" "$SteamAppId" "$*" >> "{log}"
case "$1" in
  wineboot)
    {'exit 7' if fail_wineboot else 'mkdir -p "$WINEPREFIX/drive_c/windows/system32" "$WINEPREFIX/drive_c/windows/syswow64"'}
    ;;
  wineserver) if [ "$2" = "-f" ]; then exec sleep 60; fi ;;
esac
exit 0
''')
    wine.chmod(0o755)
    return runtime


class ServiceCase(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.home = self.root / 'home'
        self.home.mkdir()
        self.socket = str(self.root / 'wined.sock')
        self.log = self.root / 'wine.log'
        self.log.touch()
        self.process = None

    def tearDown(self):
        if self.process:
            try:
                self.request('QUIT\n')
                self.process.wait(timeout=5)
            except Exception:
                self.process.kill()
                self.process.wait(timeout=5)
        self.temp.cleanup()

    def start(self, runtime):
        env = dict(os.environ, HOME=str(self.home), OMINX_WINE_RUNTIME_DIR=str(runtime),
                   OMINX_WINEPREFIX=str(self.home / 'pfx'), OMINX_PROTON_DIR=str(self.home / 'proton'),
                   OMINX_WINED_SOCKET=self.socket, XDG_RUNTIME_DIR=str(self.root))
        self.process = subprocess.Popen([WINED, self.socket], env=env,
                                        stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            if self.process.poll() is not None:
                self.fail('daemon exited: ' + self.process.stderr.read())
            try:
                return self.request('STATUS\n')
            except OSError:
                time.sleep(0.05)
        self.fail('daemon did not start')

    def request(self, payload, timeout=10):
        with socket.socket(socket.AF_UNIX, socket.SOCK_SEQPACKET) as client:
            client.settimeout(timeout)
            client.connect(self.socket)
            client.send(payload.encode())
            return client.recv(16384).decode()

    def wait_status(self, fragment, timeout=20):
        deadline = time.monotonic() + timeout
        status = ''
        while time.monotonic() < deadline:
            status = self.request('STATUS\n')
            if fragment in status:
                return status
            time.sleep(0.1)
        self.fail(f'{fragment!r} not in status: {status}')


class WinedTests(ServiceCase):
    def test_first_login_setup_and_launches(self):
        runtime = make_runtime(self.root, self.log)
        first = self.start(runtime)
        self.assertIn('runtime=present', first)
        exe = self.root / 'Game Setup.exe'
        exe.write_bytes(pe_image())
        msi = self.root / 'app.msi'
        msi.write_bytes(bytes.fromhex('d0cf11e0a1b11ae1') + b'\0' * 600)
        dll = self.root / 'engine.dll'
        dll.write_bytes(pe_image(dll=True))
        arm = self.root / 'arm.exe'
        arm.write_bytes(pe_image(machine=0xaa64))

        # Background first-login setup completes and precreates Proton.
        status = self.wait_status('proton-default=ready')
        self.assertIn('state=ready', status)
        self.assertIn('percent=100', status)
        self.assertIn('wineserver=running', status)
        self.assertIn('dxvk=1', status)
        prefix = self.home / 'pfx'
        self.assertEqual((prefix / 'drive_c/windows/system32/d3d11.dll').read_bytes(), b'FAKE-D3D11')
        self.assertIn('wine-10.0-ominx-test', (prefix / '.ominx-setup-v1').read_text())
        link = self.home / '.wine'
        self.assertTrue(link.is_symlink())
        calls = self.log.read_text()
        self.assertIn('ARGS=wineboot --init', calls)
        self.assertIn('DllOverrides /v d3d11 /d native', calls)
        self.assertIn('PREFIX=' + str(self.home / 'proton/default/pfx'), calls)

        self.assertTrue(self.request(f'RUN\t{exe}\t--fullscreen\n').startswith('OK pid='))
        self.assertTrue(self.request(f'MSI\t{msi}\n').startswith('OK pid='))
        self.assertTrue(self.request(f'PROTON\tdefault\t{exe}\n').startswith('OK pid='))
        self.assertEqual(self.request(f'RUN\t{msi}\n'), 'ERR use-msi-for-installers\n')
        self.assertEqual(self.request(f'MSI\t{exe}\n'), 'ERR not-an-msi\n')
        self.assertEqual(self.request(f'RUN\t{dll}\n'), 'ERR dlls-are-not-programs\n')
        self.assertEqual(self.request(f'RUN\t{arm}\n'), 'ERR unsupported-architecture\n')
        self.assertEqual(self.request('RUN\trelative.exe\n'), 'ERR bad-path\n')
        self.assertEqual(self.request(f'RUN\t{exe}\tbad\x01arg\n'), 'ERR bad-argument\n')
        self.assertEqual(self.request('EXPLODE\n'), 'ERR invalid-request\n')
        self.assertEqual(self.request('RUN\n'), 'ERR invalid-request\n')

        demo = prefix / 'drive_c/Program Files/Demo'
        demo.mkdir(parents=True)
        (demo / 'demo.exe').write_bytes(pe_image())
        apps = self.request('APPS\n')
        self.assertIn('APP\tdemo.exe\t', apps)
        self.assertIn('END count=1', apps)

        probe = self.request(f'PROBE\t{exe}\n')
        self.assertIn('kind=exe\n', probe)
        self.assertIn('subsystem=gui\n', probe)

        # Waits until the stub programs are reaped, then checks their log.
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline and 'running=0' not in self.request('STATUS\n'):
            time.sleep(0.1)
        calls = self.log.read_text()
        self.assertIn(f'ARGS={exe} --fullscreen', calls)
        self.assertIn(f'ARGS=msiexec /i {msi}', calls)
        self.assertIn('STEAM=default', calls)

    def test_second_login_is_immediately_ready(self):
        runtime = make_runtime(self.root, self.log)
        self.start(runtime)
        self.wait_status('state=ready')
        self.request('QUIT\n')
        self.process.wait(timeout=5)
        self.process = None
        self.socket = str(self.root / 'wined2.sock')
        status = self.start(runtime)
        self.assertIn('state=ready', status)

    def test_setup_failure_is_reported_not_silent(self):
        runtime = make_runtime(self.root, self.log, fail_wineboot=True)
        self.start(runtime)
        status = self.wait_status('state=failed')
        self.assertIn('error=setup-step-11', status)
        self.assertEqual(self.request(f'RUN\t{self.root}/x.exe\n'),
                         'ERR prefix-not-ready\n')

    def test_missing_runtime_is_honest(self):
        empty = self.root / 'nothing'
        empty.mkdir()
        status = self.start(empty)
        self.assertIn('runtime=missing', status)
        self.assertIn('state=runtime-missing', status)
        self.assertEqual(self.request('SETUP\n'), 'ERR runtime-missing\n')

    def test_single_instance(self):
        runtime = make_runtime(self.root, self.log)
        self.start(runtime)
        env = dict(os.environ, HOME=str(self.home), OMINX_WINE_RUNTIME_DIR=str(runtime),
                   OMINX_WINEPREFIX=str(self.home / 'pfx'), OMINX_PROTON_DIR=str(self.home / 'proton'),
                   OMINX_WINED_SOCKET=self.socket, XDG_RUNTIME_DIR=str(self.root))
        second = subprocess.run([WINED, self.socket], env=env, capture_output=True, text=True)
        self.assertEqual(second.returncode, 1)
        self.assertIn('already running', second.stderr)


class WinSetupTests(ServiceCase):
    def start_setup(self, runtime):
        state = self.root / 'state'
        state.mkdir(exist_ok=True)
        env = dict(os.environ, OMINX_WINE_RUNTIME_DIR=str(runtime))
        self.process = subprocess.Popen([WINSETUP, self.socket, str(state)], env=env,
                                        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            try:
                return self.request('STATUS\n')
            except OSError:
                time.sleep(0.05)
        self.fail('setup service did not start')

    def test_root_service_with_runtime(self):
        runtime = make_runtime(self.root, self.log)
        status = self.start_setup(runtime)
        self.assertIn('state=ready', status)
        self.assertIn('binfmt=1', status)
        self.assertIn('marker=1', status)
        self.assertIn('wine-10.0-ominx-test',
                      (self.root / 'state/system-setup-v1').read_text())
        self.assertEqual(self.request('RECHECK\n'), status)
        self.assertEqual(self.request('RUN\t/app.exe\n'), 'ERR invalid-request\n')

    def test_root_service_without_runtime(self):
        empty = self.root / 'nothing'
        empty.mkdir()
        status = self.start_setup(empty)
        self.assertIn('state=runtime-missing', status)
        self.assertIn('binfmt=0', status)


class WinClientTests(ServiceCase):
    def test_probe_and_refusals_without_daemon(self):
        exe = self.root / 'tool.exe'
        exe.write_bytes(pe_image())
        env = dict(os.environ, HOME=str(self.home), XDG_RUNTIME_DIR=str(self.root))
        run = lambda *args: subprocess.run([WIN, *args], env=env, capture_output=True, text=True)
        probe = run('probe', '--json', str(exe))
        self.assertEqual(probe.returncode, 0, probe.stderr)
        self.assertIn('"kind":"exe"', probe.stdout)
        self.assertIn('"arch":"x86-64"', probe.stdout)
        note = self.root / 'readme.txt'
        note.write_text('not a program')
        other = run('probe', str(note))
        self.assertEqual(other.returncode, 0)
        self.assertIn('kind=unknown', other.stdout)
        broken = self.root / 'broken.exe'
        broken.write_bytes(b'MZ')
        self.assertEqual(run('probe', str(broken)).returncode, 1)
        help_out = run('help')
        self.assertEqual(help_out.returncode, 0)
        self.assertIn('win proton', help_out.stdout)


if __name__ == '__main__':
    unittest.main()
