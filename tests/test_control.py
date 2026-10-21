import os
from pathlib import Path
import socket
import subprocess
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]


class ControlTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.binary = Path(cls.temp.name) / 'test-control'
        subprocess.run(['cc', '-O2', '-Wall', '-Wextra', '-Werror', '-DOMINX_CONTROL_TEST',
                        str(ROOT / 'src/control/main.c'), '-o', str(cls.binary)], check=True)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.path = Path(self.directory.name) / 'control.sock'
        self.process = None
        self.start()

    def start(self):
        self.process = subprocess.Popen([str(self.binary), str(self.path)], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            if self.process.poll() is not None:
                self.fail(self.process.communicate())
            try:
                if self.request(b'status\n').startswith(b'OK '):
                    return
            except OSError:
                time.sleep(0.02)
        self.fail('service did not start')

    def request(self, data):
        with socket.socket(socket.AF_UNIX, socket.SOCK_SEQPACKET) as connection:
            connection.settimeout(2)
            connection.connect(str(self.path))
            connection.sendall(data)
            return connection.recv(256)

    def tearDown(self):
        if self.process:
            self.process.terminate()
            self.process.communicate(timeout=3)
        self.directory.cleanup()

    def test_protocol_and_injection_rejection(self):
        self.assertIn(b'protocol=1', self.request(b'status\n'))
        for data in (b'reboot; id\n', b'poweroff\nstatus\n', b'status\0\n', b'x' * 4096,
                     b'attach /dev/vda\n', b'reboot', b'STATUS\n'):
            self.assertEqual(self.request(data), b'ERR invalid-request\n')
        self.assertIn(b'OK ', self.request(b'status\n'))

    def test_test_binary_never_powers_host(self):
        for operation in (b'reboot\n', b'poweroff\n'):
            self.assertEqual(self.request(operation), b'OK test-only-no-power-action\n')

    def test_idle_client_timeout(self):
        with socket.socket(socket.AF_UNIX, socket.SOCK_SEQPACKET) as client:
            client.settimeout(2)
            client.connect(str(self.path))
            self.assertEqual(client.recv(256), b'ERR invalid-request\n')
        self.assertIn(b'OK ', self.request(b'status\n'))

    def test_restart_and_single_instance(self):
        second = subprocess.run([str(self.binary), str(self.path)], capture_output=True, timeout=3)
        self.assertNotEqual(second.returncode, 0)
        self.assertIn(b'OK ', self.request(b'status\n'))
        self.process.terminate()
        self.process.communicate(timeout=3)
        self.start()
        self.assertEqual(self.path.stat().st_mode & 0o777, 0o660)

    def test_refuses_regular_file(self):
        other = Path(self.directory.name) / 'keep'
        other.write_text('keep me')
        result = subprocess.run([str(self.binary), str(other)], capture_output=True, timeout=3)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(other.read_text(), 'keep me')
