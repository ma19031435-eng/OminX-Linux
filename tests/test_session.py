import ctypes
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class SessionPolicyTests(unittest.TestCase):
    def test_exact_recovery_flag(self):
        # Only the pure parser runs on the host, never privilege/device operations.
        with tempfile.TemporaryDirectory() as directory:
            library = Path(directory) / 'session.so'
            subprocess.run(['cc', '-shared', '-fPIC', '-O2', '-Wall', '-Wextra', '-Werror',
                            str(ROOT / 'src/lib/session.c'), '-o', str(library)], check=True)
            parser = ctypes.CDLL(str(library)).ominx_recovery_requested
            parser.argtypes = [ctypes.c_char_p]
            parser.restype = ctypes.c_int
            for text in (b'ominx.recovery=1', b'console=tty0 ominx.recovery=1 panic=-1', b'\tominx.recovery=1\n'):
                self.assertEqual(parser(text), 1)
            for text in (b'', b'ominx.recovery=0', b'xominx.recovery=1', b'ominx.recovery=10',
                         b'foo=ominx.recovery=1', b'ominx.recovery', b'   '):
                self.assertEqual(parser(text), 0)

    def test_host_shell_does_not_change_identity(self):
        result = subprocess.run([os.environ['OMINX_TEST_BINARY'], '--shell'], input='id\nexit\n',
                                text=True, capture_output=True, check=True)
        self.assertIn(f'uid={os.getuid()} euid={os.geteuid()}', result.stdout)
