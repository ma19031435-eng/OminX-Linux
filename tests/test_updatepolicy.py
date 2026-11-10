"""User-controlled update policy: the decisions that must never be made for the user.

Drives build/host/ominx-updatepolicy-test (or OMINX_UPDATEPOLICY_BINARY)."""
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BIN = os.environ.get('OMINX_UPDATEPOLICY_BINARY', str(ROOT / 'build/host/ominx-updatepolicy-test'))


def decide(policy, hour, activity, restart='0'):
    """policy is None for defaults, or the text of a policy file."""
    path = '-'
    tmp = None
    if policy is not None:
        tmp = tempfile.NamedTemporaryFile('w', delete=False, suffix='.policy')
        tmp.write(policy)
        tmp.close()
        path = tmp.name
    try:
        out = subprocess.run([BIN, path, str(hour), activity, restart],
                             capture_output=True, text=True, timeout=10)
    finally:
        if tmp:
            os.unlink(tmp.name)
    return out


def parse(out):
    assert out.returncode == 0, out.stderr
    fields = dict(part.split('=', 1) for part in out.stdout.strip().split(' ', 3)[:3])
    return {k: int(v) for k, v in fields.items()}


class UpdatePolicyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not os.path.exists(BIN):
            raise unittest.SkipTest('ominx-updatepolicy-test not built (run make check)')

    def test_defaults_never_install_or_restart_on_their_own(self):
        for hour in range(24):
            for activity in ('idle', 'active', 'gaming'):
                d = parse(decide(None, hour, activity))
                self.assertEqual(d['install'], 0, (hour, activity))
                self.assertEqual(d['restart'], 0, (hour, activity))

    def test_defaults_allow_download_all_day(self):
        for hour in range(24):
            self.assertEqual(parse(decide(None, hour, 'active'))['download'], 1)

    def test_user_restart_request_runs_now_when_not_gaming(self):
        d = parse(decide(None, 14, 'active', restart='1'))
        self.assertEqual(d['restart'], 1)

    def test_user_restart_request_waits_while_gaming(self):
        d = parse(decide(None, 14, 'gaming', restart='1'))
        self.assertEqual(d['restart'], 0)

    def test_automatic_install_only_in_its_window_and_when_idle(self):
        policy = 'auto_install=1\ninstall_window=2-5\n'
        self.assertEqual(parse(decide(policy, 3, 'idle'))['install'], 1)
        self.assertEqual(parse(decide(policy, 3, 'active'))['install'], 0)
        self.assertEqual(parse(decide(policy, 3, 'gaming'))['install'], 0)
        self.assertEqual(parse(decide(policy, 12, 'idle'))['install'], 0)

    def test_window_wraps_past_midnight(self):
        policy = 'auto_install=1\ninstall_window=23-6\n'
        self.assertEqual(parse(decide(policy, 23, 'idle'))['install'], 1)
        self.assertEqual(parse(decide(policy, 1, 'idle'))['install'], 1)
        self.assertEqual(parse(decide(policy, 7, 'idle'))['install'], 0)

    def test_automatic_restart_only_when_idle_and_in_window(self):
        policy = 'auto_restart=1\nrestart_window=2-4\n'
        self.assertEqual(parse(decide(policy, 3, 'idle'))['restart'], 1)
        self.assertEqual(parse(decide(policy, 3, 'active'))['restart'], 0)
        self.assertEqual(parse(decide(policy, 3, 'gaming'))['restart'], 0)
        self.assertEqual(parse(decide(policy, 10, 'idle'))['restart'], 0)

    def test_download_window_is_respected(self):
        policy = 'download_window=8-22\n'
        self.assertEqual(parse(decide(policy, 9, 'active'))['download'], 1)
        self.assertEqual(parse(decide(policy, 3, 'active'))['download'], 0)

    def test_unknown_key_and_bad_values_are_refused(self):
        for policy in ('colour=red\n', 'auto_install=yes\n', 'install_window=2-99\n', 'install_window=2-5x\n'):
            out = decide(policy, 3, 'idle')
            self.assertNotEqual(out.returncode, 0, policy)

    def test_crlf_policy_files_are_accepted(self):
        policy = 'auto_install=1\r\ninstall_window=2-5\r\n'
        self.assertEqual(parse(decide(policy, 3, 'idle'))['install'], 1)
        self.assertEqual(parse(decide(policy, 9, 'idle'))['install'], 0)

    def test_missing_policy_file_is_an_error(self):
        out = subprocess.run([BIN, '/nonexistent/policy', '3', 'idle', '0'],
                             capture_output=True, text=True, timeout=10)
        self.assertNotEqual(out.returncode, 0)

    def test_bad_arguments_are_refused(self):
        for args in (['-', '24', 'idle', '0'], ['-', '3', 'busy', '0'], ['-', '3', 'idle', 'yes']):
            out = subprocess.run([BIN] + args, capture_output=True, text=True, timeout=10)
            self.assertNotEqual(out.returncode, 0, args)


if __name__ == '__main__':
    unittest.main()
