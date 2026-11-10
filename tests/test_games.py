"""Game framework tests: profile validation, anti-cheat launch policy, EAC Linux v2
host checks (against a fake sysfs) and the daemon's GAMELAUNCH verb.

The shipped profiles are used as they are. Valorant (Vanguard, denied) and
Fortnite (EAC, pending publisher support) must never launch. The tests never
add an exemption for them. A fixture profile with vendor-opt-in stands in for
a future title that its publisher has enabled."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import time
import unittest
from unittest import mock

from test_wined import ServiceCase, WIN, make_runtime, pe_image

ROOT = Path(__file__).resolve().parents[1]
SHIPPED_PROFILES = ROOT / 'compat/games'

EAC_V2_REQUIREMENTS = ['module-signing', 'tpm2', 'secure-boot', 'measured-boot',
                       'iommu', 'kernel-lockdown', 'kexec-disabled', 'bpf-lsm']


def profile(**fields):
    base = {
        'id': 'demo', 'name': 'Demo Game', 'appid': 'demo', 'runner': 'wine',
        'dir': 'Games/demo', 'exe': 'Demo/demo.exe', 'anticheat': 'none',
        'anticheat_status': 'none',
    }
    base.update(fields)
    return '\n'.join(f'{key} = {value}' for key, value in base.items()) + '\n'


def make_sysroot(root, complete=True):
    """Fake /sys and /proc. complete=True satisfies every EAC Linux v2 check."""
    sysroot = root / 'sysroot'
    def write(path, data):
        target = sysroot / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data if isinstance(data, bytes) else data.encode())
    write('sys/kernel/security/lsm', 'lockdown,capability,landlock,bpf\n' if complete else 'lockdown,capability\n')
    write('sys/kernel/security/lockdown',
          'none [integrity] confidentiality\n' if complete else '[none] integrity confidentiality\n')
    write('proc/sys/kernel/kexec_load_disabled', '1\n' if complete else '0\n')
    write('sys/module/module/parameters/sig_enforce', 'Y\n' if complete else 'N\n')
    write('sys/class/tpm/tpm0/tpm_version_major', '2\n' if complete else '1\n')
    write('sys/kernel/security/tpm0/binary_bios_measurements', b'log')
    (sysroot / 'sys/class/iommu/dmar0').mkdir(parents=True, exist_ok=True)
    if complete:
        write('sys/firmware/efi/efivars/SecureBoot-8be4df61-93ca-11d2-aa0d-00e098032b8c',
              b'\x06\x00\x00\x00\x01')
    else:
        write('sys/firmware/efi/efivars/SecureBoot-8be4df61-93ca-11d2-aa0d-00e098032b8c',
              b'\x06\x00\x00\x00\x00')
    return sysroot


class GameCase(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.root = Path(self.temp.name)
        self.empty_sysroot = self.root / 'empty'
        self.empty_sysroot.mkdir()
        self.games = self.root / 'games'
        shutil.copytree(SHIPPED_PROFILES, self.games, ignore=shutil.ignore_patterns('README.md'))

    def tearDown(self):
        self.temp.cleanup()

    def win(self, *args, sysroot=None, games=None):
        env = dict(os.environ, OMINX_GAMES_DIR=str(games or self.games),
                   OMINX_SYSROOT=str(sysroot or self.empty_sysroot), XDG_RUNTIME_DIR=str(self.root),
                   HOME=str(self.root / 'home'))
        return subprocess.run([WIN, 'game', *args], env=env, capture_output=True, text=True)

    def write_profile(self, name, text):
        self.games.mkdir(exist_ok=True)
        (self.games / f'{name}.game').write_text(text)


class ShippedProfileTests(GameCase):
    def test_list_refuses_both_anticheat_titles(self):
        listing = self.win('list')
        self.assertEqual(listing.returncode, 0, listing.stderr)
        self.assertRegex(listing.stdout, r'fortnite\s+Fortnite\s+anticheat=eac\s+status=pending\s+refused')
        self.assertRegex(listing.stdout, r'valorant\s+VALORANT\s+anticheat=vanguard\s+status=denied\s+refused')

    def test_valorant_is_denied_even_on_a_fully_capable_host(self):
        sysroot = make_sysroot(self.root, complete=True)
        check = self.win('check', 'valorant', sysroot=sysroot)
        self.assertEqual(check.returncode, 1)
        self.assertIn('anti-cheat denied', check.stdout)
        self.assertIn('does not offer workarounds', check.stdout)

    def test_fortnite_stays_refused_until_publisher_enables_linux(self):
        sysroot = make_sysroot(self.root, complete=True)
        check = self.win('check', 'fortnite', sysroot=sysroot)
        self.assertEqual(check.returncode, 1)
        self.assertIn('has not enabled Linux support', check.stdout)

    def test_info_shows_publisher_status_and_requirement(self):
        info = self.win('info', 'fortnite')
        self.assertEqual(info.returncode, 0, info.stderr)
        self.assertIn('requires:      eac-v2', info.stdout)
        self.assertIn('launchable:    no', info.stdout)

    def test_launch_refuses_before_contacting_the_service(self):
        # No daemon is running. A refusal must come from the policy, not the
        # missing socket, so the reason is shown even without a session.
        launch = self.win('launch', 'valorant')
        self.assertEqual(launch.returncode, 1)
        self.assertIn('will not start', launch.stdout)
        self.assertNotIn('Windows service', launch.stderr)


class PolicyTests(GameCase):
    def test_vendor_opt_in_eac_v2_title_needs_every_host_requirement(self):
        self.write_profile('eacdemo', profile(
            id='eacdemo', name='EAC Demo', appid='eacdemo', exe='Demo/eac.exe',
            anticheat='eac', anticheat_status='vendor-opt-in', requires='eac-v2'))
        missing = self.win('check', 'eacdemo')
        self.assertEqual(missing.returncode, 1)
        self.assertIn('missing EAC Linux v2 requirements', missing.stdout)
        for requirement in EAC_V2_REQUIREMENTS:
            self.assertIn(requirement, missing.stdout)

        ready = self.win('check', 'eacdemo', sysroot=make_sysroot(self.root, complete=True))
        self.assertEqual(ready.returncode, 0, ready.stdout)
        self.assertIn('launchable on this host', ready.stdout)

    def test_partial_host_reports_only_the_missing_requirements(self):
        self.write_profile('eacdemo', profile(
            id='eacdemo', name='EAC Demo', appid='eacdemo', exe='Demo/eac.exe',
            anticheat='eac', anticheat_status='vendor-opt-in', requires='eac-v2'))
        sysroot = make_sysroot(self.root, complete=True)
        (sysroot / 'sys/kernel/security/lsm').write_text('lockdown,capability\n')
        (sysroot / 'proc/sys/kernel/kexec_load_disabled').write_text('0\n')
        check = self.win('check', 'eacdemo', sysroot=sysroot)
        self.assertEqual(check.returncode, 1)
        self.assertIn('bpf-lsm', check.stdout)
        self.assertIn('kexec-disabled', check.stdout)
        self.assertNotIn('tpm2', check.stdout)

    def test_non_anticheat_title_launches_without_eac_checks(self):
        self.write_profile('demo', profile())
        check = self.win('check', 'demo')
        self.assertEqual(check.returncode, 0, check.stdout)

    def test_profile_validation_rejects_unsafe_or_inconsistent_files(self):
        cases = {
            'unknown-key': profile() + 'surprise = 1\n',
            'vanguard-must-be-denied': profile(id='vg', anticheat='vanguard', anticheat_status='pending'),
            'bad-dir': profile(id='traverse', dir='../escape'),
            'anticheat-status-mismatch': profile(id='mismatch', anticheat='none', anticheat_status='denied'),
            'eac-v2-requires-eac': profile(id='badreq', anticheat='battleye',
                                           anticheat_status='vendor-opt-in', requires='eac-v2'),
            'missing-required-key': 'id = broken\nname = Broken\n',
        }
        for reason, text in cases.items():
            with self.subTest(reason=reason):
                identifier = {'unknown-key': 'demo', 'vanguard-must-be-denied': 'vg',
                              'bad-dir': 'traverse', 'anticheat-status-mismatch': 'mismatch',
                              'eac-v2-requires-eac': 'badreq', 'missing-required-key': 'broken'}[reason]
                if reason == 'unknown-key':
                    self.write_profile('demo', text)
                else:
                    self.write_profile(identifier, text)
                info = self.win('info', identifier)
                self.assertEqual(info.returncode, 1)
                self.assertIn(reason, info.stderr)

    def test_file_name_must_match_id(self):
        self.write_profile('other', profile(id='demo'))
        info = self.win('info', 'other')
        self.assertEqual(info.returncode, 1)
        self.assertIn('id-does-not-match-file', info.stderr)

    def test_invalid_profiles_are_visible_in_the_list(self):
        self.write_profile('broken', 'id = broken\n')
        listing = self.win('list')
        self.assertEqual(listing.returncode, 0)
        self.assertIn('invalid profile', listing.stdout)

    def test_unknown_and_malformed_ids_are_rejected(self):
        self.assertEqual(self.win('info', 'missing').returncode, 1)
        for bad in ['../valorant', 'Valorant', 'a/b', '']:
            with self.subTest(bad=bad):
                self.assertEqual(self.win('info', bad).returncode, 1)

    def test_unreadable_host_state_counts_as_missing_requirements(self):
        self.write_profile('eacdemo', profile(
            id='eacdemo', name='EAC Demo', appid='eacdemo', exe='Demo/eac.exe',
            anticheat='eac', anticheat_status='vendor-opt-in', requires='eac-v2'))
        bare = self.root / 'bare'
        bare.mkdir()
        check = self.win('check', 'eacdemo', sysroot=bare)
        self.assertEqual(check.returncode, 1)
        for requirement in EAC_V2_REQUIREMENTS:
            self.assertIn(requirement, check.stdout)


class DaemonLaunchTests(ServiceCase):
    """GAMELAUNCH through the real per-user daemon with a stub runtime."""

    def setUp(self):
        super().setUp()
        self.games = self.root / 'games'
        shutil.copytree(SHIPPED_PROFILES, self.games, ignore=shutil.ignore_patterns('README.md'))
        (self.games / 'demo.game').write_text(profile())
        program = self.home / 'Games/demo/Demo'
        program.mkdir(parents=True)
        (program / 'demo.exe').write_bytes(pe_image())
        self.patch = mock.patch.dict(os.environ, {
            'OMINX_GAMES_DIR': str(self.games),
            'OMINX_SYSROOT': str(self.root / 'empty'),
        })
        self.patch.start()
        (self.root / 'empty').mkdir(exist_ok=True)

    def tearDown(self):
        self.patch.stop()
        super().tearDown()

    def test_daemon_launches_only_policy_approved_titles(self):
        runtime = make_runtime(self.root, self.log)
        self.start(runtime)
        self.wait_status('state=ready')

        ok = self.request('GAMELAUNCH\tdemo\n')
        self.assertTrue(ok.startswith('OK pid='), ok)
        self.assertIn('game=demo', ok)
        deadline = time.monotonic() + 10
        while 'demo.exe' not in self.log.read_text() and time.monotonic() < deadline:
            time.sleep(0.05)
        self.assertIn('demo.exe', self.log.read_text())

        self.assertEqual(self.request('GAMELAUNCH\tvalorant\n'), 'ERR refused-anticheat-denied\n')
        self.assertEqual(self.request('GAMELAUNCH\tfortnite\n'),
                         'ERR refused-anticheat-pending-publisher-support\n')
        self.assertEqual(self.request('GAMELAUNCH\t../valorant\n'), 'ERR bad-game-id\n')
        self.assertIn('ERR game-profile-unknown-game', self.request('GAMELAUNCH\tmissing\n'))

    def test_daemon_refuses_a_profile_it_cannot_verify(self):
        runtime = make_runtime(self.root, self.log)
        self.start(runtime)
        self.wait_status('state=ready')
        (self.games / 'eacdemo.game').write_text(profile(
            id='eacdemo', name='EAC Demo', appid='eacdemo', exe='Demo/demo.exe',
            anticheat='eac', anticheat_status='vendor-opt-in', requires='eac-v2'))
        reply = self.request('GAMELAUNCH\teacdemo\n')
        self.assertTrue(reply.startswith('ERR refused-eac-v2-requirements-unmet:'), reply)
        self.assertIn('bpf-lsm', reply)

    def test_daemon_reports_missing_runtime_honestly(self):
        self.start(self.root / 'no-runtime')
        self.assertEqual(self.request('GAMELAUNCH\tdemo\n'), 'ERR runtime-missing\n')


if __name__ == '__main__':
    unittest.main()
