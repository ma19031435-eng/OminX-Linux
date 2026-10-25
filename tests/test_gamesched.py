"""Game scheduling tests: CPU, I/O and GPU boost for the foreground game.

Two layers. The gamesched driver (src/lib/gamesched-test.c) runs the same library
code the daemon uses against a fake sysroot. The daemon tests then drive a real
GAMELAUNCH through the per-user service. Shipped Valorant and Fortnite must never
be boosted. A vendor-opt-in fixture stands in for a title its publisher enabled.
Every knob is optional: a missing or read-only knob is reported and skipped, and
the launch still succeeds."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest import mock

from test_games import profile, SHIPPED_PROFILES
from test_wined import ServiceCase, make_runtime, pe_image

ROOT = Path(__file__).resolve().parents[1]
GAMESCHED = os.environ.get('OMINX_GAMESCHED_BINARY', str(ROOT / 'build/host/ominx-gamesched-test'))
GROUP_ROOT = 'sys/fs/cgroup/ominx'
GPU = 'sys/class/drm/card0/device/power_dpm_force_performance_level'
PUBLISHER_ENABLED = dict(id='boostdemo', name='Boost Demo', appid='boostdemo', dir='Games/boostdemo',
                         exe='Demo/demo.exe',
                         anticheat='eac', anticheat_status='vendor-opt-in')


def populate_cgroup(path):
    """The kernel fills a new cgroup directory with its control files. The fake does the same."""
    path.mkdir(parents=True, exist_ok=True)
    for name in ('cgroup.procs', 'cgroup.subtree_control', 'cpu.weight', 'io.weight'):
        (path / name).touch()


def fake_sysroot(root, gpu=True, delegated=True):
    sysroot = root / 'sysroot'
    (sysroot / 'sys/fs/cgroup').mkdir(parents=True)
    (sysroot / 'sys/fs/cgroup/cgroup.subtree_control').write_text('')
    if delegated:
        populate_cgroup(sysroot / GROUP_ROOT)
        # The per-title group exists with its knobs, as the kernel would present it, so
        # boost takes the EEXIST path and writes the real control files.
        populate_cgroup(sysroot / GROUP_ROOT / 'game-boostdemo')
    if gpu:
        (sysroot / GPU).parent.mkdir(parents=True)
        (sysroot / GPU).write_text('auto\n')
    return sysroot


class SchedCase(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.root = Path(self.temp.name)
        self.games = self.root / 'games'
        shutil.copytree(SHIPPED_PROFILES, self.games, ignore=shutil.ignore_patterns('README.md'))
        (self.games / 'boostdemo.game').write_text(profile(**PUBLISHER_ENABLED))

    def tearDown(self):
        self.temp.cleanup()

    def driver(self, sysroot, game, *args):
        return subprocess.run([GAMESCHED, str(sysroot), str(self.games), game, *args],
                              capture_output=True, text=True)


class StatusTests(SchedCase):
    def test_shipped_valorant_is_refused_and_never_boosted(self):
        sysroot = fake_sysroot(self.root)
        status = self.driver(sysroot, 'valorant', 'status')
        self.assertEqual(status.returncode, 0, status.stderr)
        self.assertIn('Compatibility: denied', status.stdout)
        self.assertIn('launch refused (anticheat-denied)', status.stdout)
        self.assertIn('scheduling: default priorities', status.stdout)
        boost = self.driver(sysroot, 'valorant', 'boost', '4242')
        self.assertEqual(boost.returncode, 0, boost.stderr)
        self.assertIn('not boosted', boost.stdout)
        self.assertIn('boosted-knobs: 0', boost.stdout)
        self.assertFalse((sysroot / GROUP_ROOT / 'game-valorant').exists())
        self.assertEqual((sysroot / GPU).read_text(), 'auto\n')

    def test_shipped_fortnite_stays_pending_and_is_never_boosted(self):
        sysroot = fake_sysroot(self.root)
        status = self.driver(sysroot, 'fortnite', 'status')
        self.assertIn('Compatibility: pending', status.stdout)
        self.assertIn('anticheat-pending-publisher-support', status.stdout)
        boost = self.driver(sysroot, 'fortnite', 'boost', '4243')
        self.assertIn('boosted-knobs: 0', boost.stdout)
        self.assertFalse((sysroot / GROUP_ROOT / 'game-fortnite').exists())

    def test_status_reports_ready_only_when_the_group_is_delegated(self):
        ready = self.driver(fake_sysroot(self.root), 'boostdemo', 'status').stdout
        self.assertIn('Compatibility: vendor-opt-in, launch allowed', ready)
        self.assertIn('scheduling: game boost ready', ready)
        other = self.root / 'undelegated'
        bare = self.driver(fake_sysroot(other, delegated=False), 'boostdemo', 'status').stdout
        self.assertIn('group not delegated', bare)

    def test_non_publisher_enabled_title_keeps_default_priorities(self):
        (self.games / 'plain.game').write_text(profile(id='plain', name='Plain', appid='plain',
                                                       exe='Demo/plain.exe'))
        sysroot = fake_sysroot(self.root)
        boost = self.driver(sysroot, 'plain', 'boost', '77')
        self.assertIn('not a publisher-enabled title', boost.stdout)
        self.assertIn('boosted-knobs: 0', boost.stdout)


class BoostTests(SchedCase):
    def test_boost_writes_cpu_io_and_gpu_then_release_restores(self):
        sysroot = fake_sysroot(self.root)
        boost = self.driver(sysroot, 'boostdemo', 'boost', '4242')
        self.assertEqual(boost.returncode, 0, boost.stderr)
        group = sysroot / GROUP_ROOT / 'game-boostdemo'
        self.assertEqual((group / 'cpu.weight').read_text(), '1000\n')
        self.assertEqual((group / 'io.weight').read_text(), '800\n')
        self.assertEqual((group / 'cgroup.procs').read_text(), '4242\n')
        self.assertEqual((sysroot / GPU).read_text(), 'high\n')
        self.assertIn('boosted-knobs: 3', boost.stdout)

        release = self.driver(sysroot, 'boostdemo', 'release', '4242')
        self.assertEqual(release.returncode, 0, release.stderr)
        self.assertEqual((sysroot / GPU).read_text(), 'auto\n')
        self.assertEqual((sysroot / GROUP_ROOT / 'cgroup.procs').read_text(), '4242\n')

    def test_missing_gpu_knob_is_skipped_not_fatal(self):
        sysroot = fake_sysroot(self.root, gpu=False)
        boost = self.driver(sysroot, 'boostdemo', 'boost', '4242')
        self.assertEqual(boost.returncode, 0, boost.stderr)
        self.assertIn('gpu: skipped (knob missing)', boost.stdout)
        self.assertIn('cpu: applied', boost.stdout)
        self.assertIn('boosted-knobs: 2', boost.stdout)

    def test_undelegated_group_reports_and_keeps_the_launch_going(self):
        sysroot = fake_sysroot(self.root, delegated=False)
        boost = self.driver(sysroot, 'boostdemo', 'boost', '4242')
        self.assertEqual(boost.returncode, 0, boost.stderr)
        self.assertIn('scheduling: not boosted (group:', boost.stdout)
        self.assertIn('boosted-knobs: 0', boost.stdout)
        self.assertEqual((sysroot / GPU).read_text(), 'auto\n')

    def test_bad_app_id_cannot_escape_the_group_root(self):
        (self.games / 'evil.game').write_text(profile(
            id='evil', name='Evil', appid='../../etc', exe='Demo/evil.exe',
            anticheat='eac', anticheat_status='vendor-opt-in'))
        sysroot = fake_sysroot(self.root)
        boost = self.driver(sysroot, 'evil', 'boost', '9')
        self.assertIn('profile-error: bad-appid', boost.stdout)
        self.assertFalse((sysroot / 'sys/fs/cgroup/etc').exists())


class PrepareTests(SchedCase):
    def test_prepare_creates_group_and_enables_controllers(self):
        sysroot = self.root / 'sysroot'
        (sysroot / 'sys/fs/cgroup').mkdir(parents=True)
        (sysroot / 'sys/fs/cgroup/cgroup.subtree_control').write_text('')
        # A real cgroup mount fills the group on mkdir; a plain fake directory cannot, so the
        # group is populated here. mkdir itself is only verified on a real cgroup v2 mount.
        populate_cgroup(sysroot / GROUP_ROOT)
        prepare = subprocess.run([GAMESCHED, str(sysroot), str(self.games), 'boostdemo', 'prepare',
                                  str(os.getuid())], capture_output=True, text=True)
        self.assertEqual(prepare.returncode, 0, prepare.stdout + prepare.stderr)
        self.assertEqual((sysroot / 'sys/fs/cgroup/cgroup.subtree_control').read_text(), '+cpu +io\n')
        self.assertEqual((sysroot / GROUP_ROOT / 'cgroup.subtree_control').read_text(), '+cpu +io\n')
        self.assertIn('scheduling group ready', prepare.stdout)

    def test_prepare_without_a_cgroup_mount_fails_softly(self):
        sysroot = self.root / 'bare'
        sysroot.mkdir()
        prepare = subprocess.run([GAMESCHED, str(sysroot), str(self.games), 'boostdemo', 'prepare', '1000'],
                                 capture_output=True, text=True)
        self.assertEqual(prepare.returncode, 1)
        self.assertIn('prepare: cannot enable cpu/io on the parent', prepare.stdout)


class DaemonSchedulingTests(ServiceCase):
    """GAMELAUNCH through the real per-user daemon: the boost happens on launch."""

    def setUp(self):
        super().setUp()
        self.games = self.root / 'games'
        shutil.copytree(SHIPPED_PROFILES, self.games, ignore=shutil.ignore_patterns('README.md'))
        (self.games / 'boostdemo.game').write_text(profile(**PUBLISHER_ENABLED))
        (self.games / 'demo.game').write_text(profile())
        program = self.home / 'Games/boostdemo/Demo'
        program.mkdir(parents=True)
        (program / 'demo.exe').write_bytes(pe_image())
        self.sysroot = fake_sysroot(self.root)
        self.patch = mock.patch.dict(os.environ, {
            'OMINX_GAMES_DIR': str(self.games),
            'OMINX_SYSROOT': str(self.sysroot),
        })
        self.patch.start()

    def tearDown(self):
        self.patch.stop()
        super().tearDown()

    def test_daemon_boosts_a_publisher_enabled_launch(self):
        runtime = make_runtime(self.root, self.log)
        self.start(runtime)
        self.wait_status('state=ready')
        reply = self.request('GAMELAUNCH\tboostdemo\n')
        self.assertTrue(reply.startswith('OK pid='), reply)
        group = self.sysroot / GROUP_ROOT / 'game-boostdemo'
        self.assertEqual((group / 'cpu.weight').read_text(), '1000\n')
        self.assertEqual((group / 'io.weight').read_text(), '800\n')

    def test_daemon_never_boosts_a_shipped_anticheat_title(self):
        runtime = make_runtime(self.root, self.log)
        self.start(runtime)
        self.wait_status('state=ready')
        self.assertEqual(self.request('GAMELAUNCH\tvalorant\n'), 'ERR refused-anticheat-denied\n')
        self.assertEqual(self.request('GAMELAUNCH\tfortnite\n'),
                         'ERR refused-anticheat-pending-publisher-support\n')
        self.assertFalse((self.sysroot / GROUP_ROOT / 'game-valorant').exists())
        self.assertFalse((self.sysroot / GROUP_ROOT / 'game-fortnite').exists())


if __name__ == '__main__':
    unittest.main()
