"""Host tests for the original authentication broker and account tool."""
import importlib.util
import os
from pathlib import Path
import socket
import subprocess
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]
BROKER = os.environ.get('OMINX_LOGIN_BINARY', str(ROOT / 'build/host/ominx-login-test'))
spec = importlib.util.spec_from_file_location('hashing', ROOT / 'scripts/ominx-hash.py')
hashing = importlib.util.module_from_spec(spec)
spec.loader.exec_module(hashing)
ACCOUNTS = 'ominx:1000:1000:/home/ominx:/bin/ominx-desktop:0:{hash}\n' \
           'guest:1002:1002:/home/guest:/bin/ominx-desktop:1:!\n'


class LoginBrokerTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.accounts = self.root / 'accounts'
        self.socket = str(self.root / 'login.sock')
        self.password = 'correct horse'
        self.write_accounts(self.password)
        self.process = subprocess.Popen([BROKER, self.socket, str(self.accounts)],
                                        stdout=subprocess.PIPE, text=True)
        for _ in range(200):
            if Path(self.socket).exists():
                break
            time.sleep(0.05)
        else:
            raise AssertionError('broker did not create its socket')

    def tearDown(self):
        self.process.terminate()
        self.process.wait(timeout=10)
        self.temporary.cleanup()

    def write_accounts(self, password):
        self.accounts.write_text(ACCOUNTS.format(hash=hashing.generate(password, 'testsalt')))
        self.accounts.chmod(0o400)

    def request(self, payload):
        with socket.socket(socket.AF_UNIX, socket.SOCK_SEQPACKET) as client:
            client.settimeout(10)
            client.connect(self.socket)
            client.send(payload.encode())
            return client.recv(4096).decode()

    def test_listing_and_accepted_authentication(self):
        listing = self.request('LIST\n')
        self.assertTrue(listing.startswith('OK\n'))
        self.assertIn('ominx\t1000\t0', listing)
        self.assertIn('guest\t1002\t1', listing)
        self.assertEqual(self.request(f'AUTH\tominx\t{self.password}\n'), 'OK\t1000\n')
        self.assertEqual(self.request('SESSION\n'), 'OK\t1000\t/home/ominx\n')
        self.assertEqual(self.request('SESSION\n'), 'NONE\n')

    def test_wrong_password_unknown_and_locked(self):
        self.assertEqual(self.request('AUTH\tominx\tnope\n'), 'DENY\tcredentials\n')
        self.assertEqual(self.request('AUTH\tnobody\twhatever\n'), 'DENY\tcredentials\n')
        self.assertEqual(self.request('AUTH\tguest\tanything\n'), 'DENY\tlocked\n')
        self.assertEqual(self.request('SESSION\n'), 'NONE\n')

    def test_malformed_and_control_characters(self):
        for payload in ('AUTH\tominx', 'AUTH\tominx\n', 'NOPE\n', 'AUTH\ta\tb\n',
                        'AUTH\tominx\tbad\x01password\n', 'AUTH\tROOT\t%s\n' % 'x',
                        'AUTH\tominx\t' + 'y' * 200 + '\n'):
            with self.subTest(payload=repr(payload[:24])):
                reply = self.request(payload)
                self.assertTrue(reply.startswith('DENY'), reply)

    def test_repeated_failures_are_rate_limited(self):
        for attempt in range(3):
            self.assertEqual(self.request('AUTH\tominx\twrong\n'), 'DENY\tcredentials\n',
                             'attempt %d' % attempt)
        self.assertEqual(self.request(f'AUTH\tominx\t{self.password}\n'), 'DENY\trate-limited\n')
        # The limit is per attempted name, so a different name is unaffected.
        self.assertEqual(self.request('AUTH\tguest\tx\n'), 'DENY\tlocked\n')

    def test_power_request_is_recorded_once(self):
        self.assertEqual(self.request('POWER\toff\n'), 'OK\n')
        self.assertEqual(self.request('POWERSTATE\n'), 'OK\toff\n')
        self.assertEqual(self.request('POWERSTATE\n'), 'NONE\n')
        self.assertEqual(self.request('POWER\texplode\n'), 'DENY\tinvalid\n')
        self.assertEqual(self.request('POWER\treboot\n'), 'OK\n')
        self.assertEqual(self.request('POWERSTATE\n'), 'OK\treboot\n')

    def test_stale_session_is_not_handed_out(self):
        # The test build shortens the approval window to 2s; the service uses 60s.
        self.assertEqual(self.request(f'AUTH\tominx\t{self.password}\n'), 'OK\t1000\n')
        time.sleep(3)
        self.assertEqual(self.request('SESSION\n'), 'NONE\n')

    def test_unsafe_account_file_is_refused(self):
        self.accounts.chmod(0o644)
        self.assertEqual(self.request('AUTH\tominx\t%s\n' % self.password), 'DENY\tunavailable\n')
        self.accounts.chmod(0o600)
        self.accounts.write_text('ominx:1000:1000:/home/ominx:/bin/sh:0:!\n')
        self.accounts.chmod(0o400)
        self.assertEqual(self.request('LIST\n'), 'ERR\taccounts-unavailable\n')

    def test_second_instance_refuses_to_replace_socket(self):
        result = subprocess.run([BROKER, self.socket, str(self.accounts)],
                                capture_output=True, text=True, timeout=20)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.request('LIST\n').splitlines()[0], 'OK')

    def test_password_never_appears_in_the_log(self):
        self.request(f'AUTH\tominx\t{self.password}\n')
        self.request('AUTH\tominx\thunter2-secret\n')
        self.process.terminate()
        self.process.wait(timeout=10)
        log = self.process.stdout.read()
        self.assertIn('login: accepted name=ominx uid=1000', log)
        self.assertNotIn(self.password, log)
        self.assertNotIn('hunter2-secret', log)
        self.process.stdout.close()


class AccountParserTests(unittest.TestCase):
    """The packaged tool and service must agree on what an account record is."""

    def test_host_tool_refuses_non_source_context(self):
        tool = os.environ.get('OMINX_PASSWD_BINARY', str(ROOT / 'build/host/ominx-passwd'))
        result = subprocess.run([tool, '--list'], capture_output=True, text=True, timeout=20)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('source boot context', result.stderr)


if __name__ == '__main__':
    unittest.main()
