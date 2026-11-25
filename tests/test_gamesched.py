"""Game scheduling tests: CPU, I/O and GPU boost for the foreground game.

Layout under the ominx root: user-<uid>/service holds the daemon and
user-<uid>/game-<appid> holds a boosted title. The seat moves the daemon in
(enter); the daemon moves games in and out (boost and release).

Two layers. The gamesched driver (src/lib/gamesched-test.c) runs the same library
code against a fake sysroot. The daemon tests then drive a real GAMELAUNCH
through the per-user service. Shipped Valorant and Fortnite must never be
boosted. A vendor-opt-in fixture stands in for a title its publisher enabled.
Every knob is optional: a missing or read-only knob is reported and skipped, and
the launch still succeeds.

A plain filesystem cannot create cgroup control files. The fixtures therefore
populate the directories the kernel would fill on mkdir. mkdir itself and the
kernel's migration rules are only verified on a real cgroup v2 mount."""
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
WIN = os.environ.get('OMINX_WIN_BINARY', str(ROOT / 'build/host/ominx-win'))
OMINX = 'sys/fs/cgroup/ominx'
USER = f'{OMINX}/user-{os.getuid()}'
SERVICE = f'{USER}/service'
GAME = f'{USER}/game-boostdemo'
GPU = 'sys/class/drm/card0/device/power_dpm_force_performance_level'
PUBLISHER_ENABLED = dict(id='boostdemo', name='Boost Demo', appid='boostdemo', dir='Games/boostdemo',
                         exe='Demo/demo.exe', anticheat='eac', anticheat_status='vendor-opt-in')


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
        populate_cgroup(sysroot / OMINX)
        populate_cgroup(sysroot / USER)
        populate_cgroup(sysroot / SERVICE)
        populate_cgroup(sysroot / GAME)
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
        self.assertFalse((sysroot / USER / 'game-valorant').exists())
        self.assertEqual((sysroot / GPU).read_text(), 'auto\n')

    def test_shipped_fortnite_stays_pending_and_is_never_boosted(self):
        sysroot = fake_sysroot(self.root)
        status = self.driver(sysroot, 'fortnite', 'status')
        self.assertIn('Compatibility: pending', status.stdout)
        self.assertIn('anticheat-pending-publisher-support', status.stdout)
        boost = self.driver(sysroot, 'fortnite', 'boost', '4243')
        self.assertIn('boosted-knobs: 0', boost.stdout)
        self.assertFalse((sysroot / USER / 'game-fortnite').exists())

    def test_status_reports_ready_only_when_the_user_group_is_delegated(self):
        ready = self.driver(fake_sysroot(self.root), 'boostdemo', 'status').stdout
        self.assertIn('Compatibility: vendor-opt-in, launch allowed', ready)
        self.assertIn('scheduling: game boost ready', ready)
        bare = self.driver(fake_sysroot(self.root / 'undelegated', delegated=False),
                           'boostdemo', 'status').stdout
        self.assertIn('group not delegated', bare)

    def test_status_says_when_scheduling_is_off_for_a_title(self):
        (self.games / 'pending.game').write_text(profile(
            id='pending', name='Pending', appid='pending', exe='Demo/p.exe',
            anticheat='eac', anticheat_status='pending'))
        out = self.driver(fake_sysroot(self.root), 'pending', 'status').stdout
        self.assertIn('Compatibility: pending, launch refused', out)
        self.assertIn('default priorities', out)


class BoostTests(SchedCase):
    def test_boost_writes_cpu_io_and_gpu_then_release_returns_to_service(self):
        sysroot = fake_sysroot(self.root)
        boost = self.driver(sysroot, 'boostdemo', 'boost', '4242')
        self.assertEqual(boost.returncode, 0, boost.stderr)
        group = sysroot / GAME
        self.assertEqual((group / 'cpu.weight').read_text(), '1000\n')
        self.assertEqual((group / 'io.weight').read_text(), '800\n')
        self.assertEqual((group / 'cgroup.procs').read_text(), '4242\n')
        self.assertEqual((sysroot / GPU).read_text(), 'high\n')
        self.assertIn('boosted-knobs: 3', boost.stdout)

        release = self.driver(sysroot, 'boostdemo', 'release', '4242')
        self.assertEqual(release.returncode, 0, release.stderr)
        self.assertEqual((sysroot / GPU).read_text(), 'auto\n')
        # The game goes back to the daemon's own leaf, not the root cgroup.
        self.assertEqual((sysroot / SERVICE / 'cgroup.procs').read_text(), '4242\n')
        self.assertEqual((sysroot / OMINX / 'cgroup.procs').read_text(), '')

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

    def test_plain_title_with_no_anticheat_is_boosted_too(self):
        (self.games / 'plain.game').write_text(profile(id='plain', name='Plain', appid='plain',
                                                       dir='Games/plain', exe='Demo/plain.exe'))
        sysroot = fake_sysroot(self.root)
        populate_cgroup(sysroot / USER / 'game-plain')
        boost = self.driver(sysroot, 'plain', 'boost', '77')
        self.assertEqual(boost.returncode, 0, boost.stderr)
        self.assertIn('boosted-knobs: 3', boost.stdout)
        self.assertEqual((sysroot / USER / 'game-plain' / 'cpu.weight').read_text(), '1000\n')

    def test_bad_app_id_cannot_escape_the_group_root(self):
        (self.games / 'evil.game').write_text(profile(
            id='evil', name='Evil', appid='../../etc', exe='Demo/evil.exe',
            anticheat='eac', anticheat_status='vendor-opt-in'))
        sysroot = fake_sysroot(self.root)
        boost = self.driver(sysroot, 'evil', 'boost', '9')
        self.assertIn('profile-error: bad-appid', boost.stdout)
        self.assertFalse((sysroot / 'sys/fs/cgroup/etc').exists())


class RootSetupTests(SchedCase):
    def test_prepare_enables_cpu_and_io_on_the_ominx_root(self):
        sysroot = self.root / 'sysroot'
        (sysroot / 'sys/fs/cgroup').mkdir(parents=True)
        (sysroot / 'sys/fs/cgroup/cgroup.subtree_control').write_text('')
        # A real cgroup mount fills the root on mkdir; the fake populates it here.
        populate_cgroup(sysroot / OMINX)
        prepare = self.driver(sysroot, 'boostdemo', 'prepare')
        self.assertEqual(prepare.returncode, 0, prepare.stdout + prepare.stderr)
        self.assertEqual((sysroot / 'sys/fs/cgroup/cgroup.subtree_control').read_text(), '+cpu +io\n')
        self.assertEqual((sysroot / OMINX / 'cgroup.subtree_control').read_text(), '+cpu +io\n')
        self.assertIn('scheduling root ready', prepare.stdout)

    def test_prepare_selects_bfq_only_on_disks_that_offer_it(self):
        sysroot = self.root / 'sysroot'
        (sysroot / 'sys/fs/cgroup').mkdir(parents=True)
        (sysroot / 'sys/fs/cgroup/cgroup.subtree_control').write_text('')
        populate_cgroup(sysroot / OMINX)
        for disk, scheduler in [('sda', '[mq-deadline] kyber bfq none\n'), ('loop0', 'none\n')]:
            (sysroot / f'sys/block/{disk}/queue').mkdir(parents=True)
            (sysroot / f'sys/block/{disk}/queue/scheduler').write_text(scheduler)
        prepare = self.driver(sysroot, 'boostdemo', 'prepare')
        self.assertEqual(prepare.returncode, 0, prepare.stdout + prepare.stderr)
        self.assertEqual((sysroot / 'sys/block/sda/queue/scheduler').read_text(), 'bfq\n')
        self.assertEqual((sysroot / 'sys/block/loop0/queue/scheduler').read_text(), 'none\n')
        self.assertIn('io: bfq selected', prepare.stdout)

    def test_prepare_says_when_no_disk_can_weight_io(self):
        sysroot = self.root / 'sysroot'
        (sysroot / 'sys/fs/cgroup').mkdir(parents=True)
        (sysroot / 'sys/fs/cgroup/cgroup.subtree_control').write_text('')
        populate_cgroup(sysroot / OMINX)
        (sysroot / 'sys/block/vda/queue').mkdir(parents=True)
        (sysroot / 'sys/block/vda/queue/scheduler').write_text('none\n')
        prepare = self.driver(sysroot, 'boostdemo', 'prepare')
        self.assertEqual(prepare.returncode, 0, prepare.stdout + prepare.stderr)
        self.assertIn('io.weight inactive', prepare.stdout)

    def test_prepare_without_a_cgroup_mount_fails_softly(self):
        sysroot = self.root / 'bare'
        sysroot.mkdir()
        prepare = self.driver(sysroot, 'boostdemo', 'prepare')
        self.assertEqual(prepare.returncode, 1)
        self.assertIn('prepare: parent: cannot enable cpu/io', prepare.stdout)

    def test_enter_creates_the_user_group_and_moves_the_daemon_into_service(self):
        sysroot = self.root / 'sysroot'
        (sysroot / 'sys/fs/cgroup').mkdir(parents=True)
        (sysroot / 'sys/fs/cgroup/cgroup.subtree_control').write_text('')
        populate_cgroup(sysroot / OMINX)
        # Kernel fills on mkdir; the fake populates the user subtree and its service leaf.
        populate_cgroup(sysroot / USER)
        populate_cgroup(sysroot / SERVICE)
        enter = subprocess.run([GAMESCHED, str(sysroot), str(self.games), 'boostdemo', 'enter',
                                str(os.getuid()), '4300'], capture_output=True, text=True)
        self.assertEqual(enter.returncode, 0, enter.stdout + enter.stderr)
        self.assertIn('enter: session group ready', enter.stdout)
        self.assertEqual((sysroot / SERVICE / 'cgroup.procs').read_text(), '4300\n')
        self.assertEqual((sysroot / USER / 'cgroup.subtree_control').read_text(), '+cpu +io\n')

    def test_enter_reports_a_kernel_without_the_controllers(self):
        sysroot = self.root / 'sysroot'
        (sysroot / 'sys/fs/cgroup').mkdir(parents=True)
        (sysroot / 'sys/fs/cgroup/cgroup.subtree_control').write_text('')
        populate_cgroup(sysroot / OMINX)
        populate_cgroup(sysroot / USER)
        # No cgroup.subtree_control in the user group: cpu/io cannot be delegated.
        (sysroot / USER / 'cgroup.subtree_control').unlink()
        enter = subprocess.run([GAMESCHED, str(sysroot), str(self.games), 'boostdemo', 'enter',
                                str(os.getuid()), '4300'], capture_output=True, text=True)
        self.assertEqual(enter.returncode, 1)
        self.assertIn('enter: user group: cannot enable cpu/io (knob missing)', enter.stdout)
        self.assertFalse((sysroot / SERVICE / 'cgroup.procs').exists())


class DaemonSchedulingTests(ServiceCase):
    """GAMELAUNCH through the real per-user daemon: the boost happens on launch."""

    def setUp(self):
        super().setUp()
        self.games = self.root / 'games'
        shutil.copytree(SHIPPED_PROFILES, self.games, ignore=shutil.ignore_patterns('README.md'))
        (self.games / 'boostdemo.game').write_text(profile(**PUBLISHER_ENABLED))
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
        group = self.sysroot / GAME
        self.assertEqual((group / 'cpu.weight').read_text(), '1000\n')
        self.assertEqual((group / 'io.weight').read_text(), '800\n')

    def test_daemon_never_boosts_a_shipped_anticheat_title(self):
        runtime = make_runtime(self.root, self.log)
        self.start(runtime)
        self.wait_status('state=ready')
        self.assertEqual(self.request('GAMELAUNCH\tvalorant\n'), 'ERR refused-anticheat-denied\n')
        self.assertEqual(self.request('GAMELAUNCH\tfortnite\n'),
                         'ERR refused-anticheat-pending-publisher-support\n')
        self.assertFalse((self.sysroot / USER / 'game-valorant').exists())
        self.assertFalse((self.sysroot / USER / 'game-fortnite').exists())


class StructuredOutputTests(SchedCase):
    """`ominx-win game list|info --json`: the stable schema the GUI reads."""

    def win(self, *args, sysroot):
        env = dict(os.environ, OMINX_GAMES_DIR=str(self.games), OMINX_SYSROOT=str(sysroot),
                   XDG_RUNTIME_DIR=str(self.root), HOME=str(self.root / 'home'))
        return subprocess.run([WIN, 'game', *args], env=env, capture_output=True, text=True)

    def test_list_json_is_schema_1_and_covers_every_profile(self):
        import json
        result = self.win('list', '--json', sysroot=fake_sysroot(self.root))
        self.assertEqual(result.returncode, 0, result.stderr)
        data = json.loads(result.stdout)
        self.assertEqual(data['schema'], 1)
        ids = {game['id'] for game in data['games']}
        self.assertTrue({'valorant', 'fortnite', 'boostdemo'} <= ids, ids)

    def test_json_states_match_policy(self):
        import json
        data = json.loads(self.win('list', '--json', sysroot=fake_sysroot(self.root)).stdout)
        by_id = {game['id']: game for game in data['games']}
        self.assertFalse(by_id['valorant']['launchable'])
        self.assertEqual(by_id['valorant']['refusal'], 'anticheat-denied')
        self.assertEqual(by_id['valorant']['scheduling']['state'], 'not-eligible')
        self.assertEqual(by_id['fortnite']['refusal'], 'anticheat-pending-publisher-support')
        self.assertEqual(by_id['fortnite']['scheduling']['state'], 'not-eligible')
        self.assertTrue(by_id['boostdemo']['launchable'])
        self.assertEqual(by_id['boostdemo']['scheduling']['state'], 'ready')

    def test_undelegated_host_reports_not_delegated(self):
        import json
        sysroot = fake_sysroot(self.root / 'bare', delegated=False)
        data = json.loads(self.win('info', 'boostdemo', '--json', sysroot=sysroot).stdout)
        self.assertEqual(data['game']['scheduling']['state'], 'not-delegated')

    def test_unknown_game_is_a_json_error(self):
        import json
        result = self.win('info', 'missing', '--json', sysroot=fake_sysroot(self.root))
        self.assertEqual(result.returncode, 1)
        self.assertFalse(json.loads(result.stdout)['valid'])


if __name__ == '__main__':
    unittest.main()
