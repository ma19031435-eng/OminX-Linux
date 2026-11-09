"""OPKGX v1: validation, install, upgrade, remove, list, and run.

Builds real .opkgx archives with tarfile (ustar) and drives
build/host/ominx-opkgx (or OMINX_OPKGX_BINARY) with a throwaway HOME.
The rules come from docs/opkgx-format.md."""
import io
import os
import stat
import subprocess
import tarfile
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BIN = os.environ.get('OMINX_OPKGX_BINARY', str(ROOT / 'build/host/ominx-opkgx'))
PNG = b'\x89PNG\r\n\x1a\n' + b'\x00' * 24

MANIFEST = (
    'format=1\n'
    'id=org.example.puzzle\n'
    'name=Puzzle Garden\n'
    'version=1.2.0\n'
    'summary=Calm tile puzzles.\n'
    'arch=x86_64\n'
    'runner=native\n'
    'exec=app/puzzle\n'
    'icon=icon.png\n'
    'categories=Games,Utilities\n'
)
SCRIPT = b'#!/bin/sh\necho ran > "$HOME/ran-marker"\n'


def add_file(tar, name, data, mode=0o644):
    info = tarfile.TarInfo(name)
    info.size = len(data)
    info.mode = mode
    tar.addfile(info, io.BytesIO(data))


def add_dir(tar, name, mode=0o755):
    info = tarfile.TarInfo(name)
    info.type = tarfile.DIRTYPE
    info.mode = mode
    tar.addfile(info)


def build(entries=None, fmt=tarfile.USTAR_FORMAT):
    """entries: list of callables taking the tar. Defaults to a valid native app."""
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode='w', format=fmt) as tar:
        if entries is None:
            entries = default_entries()
        for add in entries:
            add(tar)
    return buf.getvalue()


def default_entries(manifest=MANIFEST):
    return [
        lambda t: add_file(t, 'opkgx.manifest', manifest.encode()),
        lambda t: add_file(t, 'icon.png', PNG),
        lambda t: add_dir(t, 'app'),
        lambda t: add_file(t, 'app/puzzle', SCRIPT, 0o755),
        lambda t: add_file(t, 'app/data/level1.txt', b'level data'),
    ]


class OpkgxCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.home = self.root / 'home'
        self.home.mkdir()
        self.apps = self.home / '.local/share/ominx/apps'
        self.desktop = self.home / '.local/share/applications'

    def tearDown(self):
        self._tmp.cleanup()

    def write(self, data, name='pkg.opkgx'):
        path = self.root / name
        path.write_bytes(data)
        return path

    def run_cli(self, *args, home=None):
        env = dict(os.environ)
        env['HOME'] = str(home or self.home)
        env.pop('XDG_DATA_HOME', None)
        return subprocess.run([BIN, *args], capture_output=True, text=True, timeout=30, env=env)

    def expect_reject(self, data, reason):
        path = self.write(data)
        r = self.run_cli('validate', str(path))
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn(reason, r.stderr)
        r = self.run_cli('install', str(path))
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn(reason, r.stderr)
        self.assertFalse(self.apps.exists() and any(self.apps.iterdir()),
                         'a rejected package must write nothing')
        self.assertFalse(self.desktop.exists(), 'a rejected package must write no desktop entry')


class Validate(OpkgxCase):
    def test_valid_package_reports_manifest(self):
        r = self.run_cli('validate', str(self.write(build())))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout.strip(), 'org.example.puzzle 1.2.0 native')

    def test_validate_writes_nothing(self):
        self.run_cli('validate', str(self.write(build())))
        self.assertFalse(self.home.joinpath('.local').exists())

    def test_crlf_manifest_accepted(self):
        data = build(default_entries(MANIFEST.replace('\n', '\r\n')))
        r = self.run_cli('validate', str(self.write(data)))
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_comments_and_blank_lines_ignored(self):
        text = '# header\n\n' + MANIFEST + '\n# trailing\n'
        r = self.run_cli('validate', str(self.write(build(default_entries(text)))))
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_wine_package_validates(self):
        text = MANIFEST.replace('runner=native', 'runner=wine').replace('app/puzzle', 'app/Puzzle.EXE')
        entries = default_entries(text)
        entries[3] = lambda t: add_file(t, 'app/Puzzle.EXE', b'MZ' + b'\x00' * 62, 0o644)
        r = self.run_cli('validate', str(self.write(build(entries))))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn('wine', r.stdout)

    def test_msi_package_validates(self):
        text = MANIFEST.replace('runner=native', 'runner=wine').replace('app/puzzle', 'app/setup.msi')
        entries = default_entries(text)
        entries[3] = lambda t: add_file(t, 'app/setup.msi', b'\xd0\xcf\x11\xe0' + b'\x00' * 60)
        r = self.run_cli('validate', str(self.write(build(entries))))
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_missing_file_is_not_a_crash(self):
        r = self.run_cli('validate', str(self.root / 'nope.opkgx'))
        self.assertEqual(r.returncode, 1)
        self.assertIn('archive-unreadable', r.stderr)


class ManifestRules(OpkgxCase):
    def replace_manifest(self, old, new):
        return MANIFEST.replace(old, new)

    def test_missing_manifest(self):
        self.expect_reject(build([lambda t: add_file(t, 'app/puzzle', SCRIPT, 0o755)]), 'manifest-not-first')

    def test_manifest_not_first(self):
        entries = default_entries()
        entries.insert(0, lambda t: add_dir(t, 'app'))
        self.expect_reject(build(entries), 'manifest-not-first')

    def test_unknown_key(self):
        self.expect_reject(build(default_entries(MANIFEST + 'colour=blue\n')), 'unknown-key')

    def test_duplicate_key(self):
        self.expect_reject(build(default_entries(MANIFEST + 'name=Again\n')), 'duplicate-key')

    def test_bad_format(self):
        self.expect_reject(build(default_entries(MANIFEST.replace('format=1', 'format=2'))), 'format-unsupported')

    def test_missing_required_key(self):
        self.expect_reject(build(default_entries(MANIFEST.replace('name=Puzzle Garden\n', ''))),
                           'missing-required-key')

    def test_bad_line(self):
        self.expect_reject(build(default_entries(MANIFEST + 'no equals here\n')), 'bad-line')

    def test_bad_ids(self):
        for bad in ['Org.Example', '1org', 'a', 'org..x', 'org/x', 'org x', 'x' * 65]:
            with self.subTest(id=bad):
                self.expect_reject(build(default_entries(self.replace_manifest('id=org.example.puzzle', 'id=' + bad))),
                                   'bad-id')

    def test_bad_versions(self):
        for bad in ['1.2', '1.2.3.4', 'v1.2.3', '1..2', '1.2.x', '123456.0.0']:
            with self.subTest(version=bad):
                self.expect_reject(build(default_entries(self.replace_manifest('version=1.2.0', 'version=' + bad))),
                                   'bad-version')

    def test_name_limits(self):
        self.expect_reject(build(default_entries(self.replace_manifest('name=Puzzle Garden', 'name=' + 'n' * 65))),
                           'bad-name')

    def test_summary_limit(self):
        self.expect_reject(build(default_entries(self.replace_manifest('summary=Calm tile puzzles.', 'summary=' + 'x' * 121))),
                           'bad-summary')

    def test_arch_must_be_x86_64(self):
        self.expect_reject(build(default_entries(self.replace_manifest('arch=x86_64', 'arch=aarch64'))),
                           'arch-unsupported')

    def test_bad_runner(self):
        self.expect_reject(build(default_entries(self.replace_manifest('runner=native', 'runner=flatpak'))),
                           'bad-runner')

    def test_exec_outside_app(self):
        self.expect_reject(build(default_entries(self.replace_manifest('exec=app/puzzle', 'exec=puzzle'))),
                           'exec-outside-app')

    def test_exec_with_dotdot(self):
        self.expect_reject(build(default_entries(self.replace_manifest('exec=app/puzzle', 'exec=app/../puzzle'))),
                           'exec-outside-app')

    def test_wine_exec_must_be_windows(self):
        text = MANIFEST.replace('runner=native', 'runner=wine')
        self.expect_reject(build(default_entries(text)), 'exec-not-windows')

    def test_permissions_reserved(self):
        self.expect_reject(build(default_entries(MANIFEST + 'permissions=network\n')), 'permissions-unsupported')

    def test_permissions_empty_allowed(self):
        r = self.run_cli('validate', str(self.write(build(default_entries(MANIFEST + 'permissions=\n')))))
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_bad_category(self):
        self.expect_reject(build(default_entries(self.replace_manifest('categories=Games,Utilities', 'categories=Games,Music'))),
                           'bad-category')

    def test_icon_key_must_name_icon_png(self):
        self.expect_reject(build(default_entries(self.replace_manifest('icon=icon.png', 'icon=other.png'))),
                           'bad-icon-key')


class ArchiveRules(OpkgxCase):
    def test_symlink_refused(self):
        def link(t):
            info = tarfile.TarInfo('app/link')
            info.type = tarfile.SYMTYPE
            info.linkname = '/etc/passwd'
            t.addfile(info)
        self.expect_reject(build(default_entries() + [link]), 'link-entry')

    def test_hardlink_refused(self):
        def hard(t):
            info = tarfile.TarInfo('app/hard')
            info.type = tarfile.LNKTYPE
            info.linkname = 'app/puzzle'
            t.addfile(info)
        self.expect_reject(build(default_entries() + [hard]), 'link-entry')

    def test_device_refused(self):
        def dev(t):
            info = tarfile.TarInfo('app/null')
            info.type = tarfile.CHRTYPE
            info.devmajor, info.devminor = 1, 3
            t.addfile(info)
        self.expect_reject(build(default_entries() + [dev]), 'device-entry')

    def test_fifo_refused(self):
        def fifo(t):
            info = tarfile.TarInfo('app/pipe')
            info.type = tarfile.FIFOTYPE
            t.addfile(info)
        self.expect_reject(build(default_entries() + [fifo]), 'fifo-entry')

    def test_dotdot_path_refused(self):
        self.expect_reject(build(default_entries() + [lambda t: add_file(t, 'app/../../evil', b'x')]),
                           'path-escape')

    def test_absolute_path_refused(self):
        self.expect_reject(build(default_entries() + [lambda t: add_file(t, '/etc/evil', b'x')]),
                           'path-escape')

    def test_outside_layout_refused(self):
        self.expect_reject(build(default_entries() + [lambda t: add_file(t, 'readme.txt', b'x')]),
                           'unexpected-entry')

    def test_pax_extension_refused(self):
        entries = default_entries() + [lambda t: add_file(t, 'app/' + 'long' * 30 + '.dat', b'x')]
        self.expect_reject(build(entries, fmt=tarfile.PAX_FORMAT), 'extension-entry')

    def test_duplicate_entry_refused(self):
        self.expect_reject(build(default_entries() + [lambda t: add_file(t, 'app/data/level1.txt', b'again')]),
                           'duplicate-entry')

    def test_missing_payload_refused(self):
        entries = [lambda t: add_file(t, 'opkgx.manifest', MANIFEST.encode()),
                   lambda t: add_dir(t, 'app')]
        self.expect_reject(build(entries), 'exec-missing')

    def test_exec_not_executable_refused(self):
        entries = default_entries()
        entries[3] = lambda t: add_file(t, 'app/puzzle', SCRIPT, 0o644)
        self.expect_reject(build(entries), 'exec-not-executable')

    def test_exec_missing_refused(self):
        entries = default_entries()
        entries[3] = lambda t: add_file(t, 'app/other', SCRIPT, 0o755)
        self.expect_reject(build(entries), 'exec-missing')

    def test_directory_with_data_refused(self):
        def bad_dir(t):
            info = tarfile.TarInfo('app/sub')
            info.type = tarfile.DIRTYPE
            info.size = 4
            t.addfile(info, io.BytesIO(b'abcd'))
        self.expect_reject(build(default_entries() + [bad_dir]), 'bad-size')

    def test_icon_not_png(self):
        entries = default_entries()
        entries[1] = lambda t: add_file(t, 'icon.png', b'GIF89a' + b'\x00' * 20)
        self.expect_reject(build(entries), 'icon-not-png')

    def test_icon_undeclared(self):
        self.expect_reject(build(default_entries(MANIFEST.replace('icon=icon.png\n', ''))), 'icon-undeclared')

    def test_icon_missing(self):
        entries = [e for i, e in enumerate(default_entries()) if i != 1]
        self.expect_reject(build(entries), 'icon-missing')

    def test_icon_too_large(self):
        entries = default_entries()
        entries[1] = lambda t: add_file(t, 'icon.png', PNG + b'\x00' * (512 * 1024))
        self.expect_reject(build(entries), 'too-large')

    def test_manifest_too_large(self):
        big = MANIFEST + '# ' + 'x' * 17000 + '\n'
        self.expect_reject(build(default_entries(big)), 'too-large')

    def test_bad_checksum(self):
        data = bytearray(build())
        at = data.index(b'icon.png\x00')  # the name field of the icon header
        data[at] ^= 0x01
        self.expect_reject(bytes(data), 'bad-checksum')

    def test_every_cut_before_the_end_is_refused(self):
        data = build()
        content_end = data.index(b'level data') + len(b'level data')
        for cut in list(range(1, content_end, 37)) + [512, 1024, 2048]:
            with self.subTest(cut=cut):
                self.expect_reject(data[:cut], 'truncated')

    def test_missing_end_marker_refused(self):
        data = build()
        content_end = data.index(b'level data') + len(b'level data')
        self.expect_reject(data[:content_end + (-content_end % 512)], 'truncated')

    def test_not_a_tar(self):
        self.expect_reject(b'this is not a package' * 40, 'bad-checksum')

    def test_empty_archive(self):
        self.expect_reject(b'', 'truncated')



class InstallRemove(OpkgxCase):
    def install(self, data, name='pkg.opkgx'):
        r = self.run_cli('install', str(self.write(data, name)))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        return r

    def test_install_creates_app_and_desktop_entry(self):
        self.install(build())
        app = self.apps / 'org.example.puzzle'
        self.assertTrue((app / 'app/puzzle').is_file())
        self.assertTrue((app / 'app/data/level1.txt').is_file())
        self.assertTrue((app / 'icon.png').is_file())
        self.assertTrue((app / 'opkgx.manifest').is_file())
        desk = (self.desktop / 'ominx-org.example.puzzle.desktop').read_text()
        self.assertIn('Name=Puzzle Garden\n', desk)
        self.assertIn('Exec=ominx-opkgx run org.example.puzzle\n', desk)
        self.assertIn(f'Icon={app}/icon.png\n', desk)
        self.assertIn('Categories=Games;Utilities;\n', desk)
        self.assertIn('X-OminX-Runner=native\n', desk)
        self.assertEqual((self.apps / 'registry').read_text(),
                         'org.example.puzzle 1.2.0 native ready\n')

    def test_install_modes(self):
        self.install(build())
        app = self.apps / 'org.example.puzzle'
        self.assertTrue(os.access(app / 'app/puzzle', os.X_OK))
        self.assertEqual(stat.S_IMODE((app / 'app/data/level1.txt').stat().st_mode), 0o644)
        self.assertEqual(stat.S_IMODE((app / 'app').stat().st_mode), 0o755)

    def test_setuid_bits_are_cleared(self):
        entries = default_entries()
        entries[3] = lambda t: add_file(t, 'app/puzzle', SCRIPT, 0o4755)
        self.install(build(entries))
        mode = (self.apps / 'org.example.puzzle/app/puzzle').stat().st_mode
        self.assertFalse(mode & (stat.S_ISUID | stat.S_ISGID))

    def test_no_staging_left_behind(self):
        self.install(build())
        self.assertEqual([p.name for p in self.apps.iterdir() if p.name.startswith('.')], [])

    def test_list_shows_registry(self):
        self.install(build())
        r = self.run_cli('list')
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout, 'org.example.puzzle 1.2.0 native ready\n')

    def test_list_empty_when_nothing_installed(self):
        r = self.run_cli('list')
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout, '')

    def test_upgrade_replaces_version(self):
        self.install(build())
        newer = build(default_entries(MANIFEST.replace('version=1.2.0', 'version=1.3.0')))
        self.install(newer)
        self.assertEqual((self.apps / 'registry').read_text(),
                         'org.example.puzzle 1.3.0 native ready\n')
        self.assertFalse((self.apps / '.old-org.example.puzzle').exists())
        self.assertFalse(any(p.name.startswith('.staging-') for p in self.apps.iterdir()))

    def test_failed_upgrade_keeps_old_version(self):
        self.install(build())
        bad = build(default_entries(MANIFEST.replace('version=1.2.0', 'version=1.3.0') + 'colour=blue\n'))
        r = self.run_cli('install', str(self.write(bad, 'bad.opkgx')))
        self.assertEqual(r.returncode, 1)
        self.assertEqual((self.apps / 'registry').read_text(),
                         'org.example.puzzle 1.2.0 native ready\n')
        self.assertTrue((self.apps / 'org.example.puzzle/app/puzzle').is_file())

    def test_remove(self):
        self.install(build())
        r = self.run_cli('remove', 'org.example.puzzle')
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertFalse((self.apps / 'org.example.puzzle').exists())
        self.assertFalse((self.desktop / 'ominx-org.example.puzzle.desktop').exists())
        self.assertEqual((self.apps / 'registry').read_text(), '')

    def test_remove_keeps_other_apps(self):
        self.install(build())
        other = build(default_entries(MANIFEST.replace('org.example.puzzle', 'org.example.other')))
        self.install(other)
        self.run_cli('remove', 'org.example.puzzle')
        self.assertEqual((self.apps / 'registry').read_text(), 'org.example.other 1.2.0 native ready\n')
        self.assertTrue((self.apps / 'org.example.other/app/puzzle').is_file())

    def test_remove_not_installed(self):
        r = self.run_cli('remove', 'org.example.none')
        self.assertEqual(r.returncode, 1)
        self.assertIn('not-installed', r.stderr)

    def test_remove_rejects_bad_id(self):
        r = self.run_cli('remove', '../../etc')
        self.assertEqual(r.returncode, 1)
        self.assertIn('bad-id', r.stderr)

    def test_interrupted_swap_is_restored(self):
        self.install(build())
        # Simulate a crash between the two renames: old copy parked, new copy not yet in place.
        (self.apps / 'org.example.puzzle').rename(self.apps / '.old-org.example.puzzle')
        r = self.run_cli('remove', 'org.example.puzzle')
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertFalse((self.apps / '.old-org.example.puzzle').exists())
        self.assertFalse((self.apps / 'org.example.puzzle').exists())

    def test_interrupted_swap_restored_on_install(self):
        self.install(build())
        (self.apps / 'org.example.puzzle').rename(self.apps / '.old-org.example.puzzle')
        newer = build(default_entries(MANIFEST.replace('version=1.2.0', 'version=1.3.0')))
        self.install(newer)
        self.assertEqual((self.apps / 'registry').read_text(),
                         'org.example.puzzle 1.3.0 native ready\n')
        self.assertFalse((self.apps / '.old-org.example.puzzle').exists())


class Run(OpkgxCase):
    def test_native_app_runs(self):
        self.run_cli('install', str(self.write(build())))
        r = self.run_cli('run', 'org.example.puzzle')
        self.assertEqual(r.returncode, 0, r.stderr)
        marker = self.home / 'ran-marker'
        for _ in range(100):
            if marker.exists():
                break
            time.sleep(0.05)
        self.assertTrue(marker.exists(), 'app did not start')
        self.assertEqual(marker.read_text().strip(), 'ran')

    def test_run_not_installed(self):
        r = self.run_cli('run', 'org.example.none')
        self.assertEqual(r.returncode, 1)
        self.assertIn('not-installed', r.stderr)

    def test_run_rejects_bad_id(self):
        r = self.run_cli('run', '../x')
        self.assertEqual(r.returncode, 1)
        self.assertIn('bad-id', r.stderr)

    def test_wine_app_reports_not_wired(self):
        text = MANIFEST.replace('runner=native', 'runner=wine').replace('app/puzzle', 'app/Puzzle.exe')
        entries = default_entries(text)
        entries[3] = lambda t: add_file(t, 'app/Puzzle.exe', b'MZ' + b'\x00' * 62)
        self.run_cli('install', str(self.write(build(entries))))
        r = self.run_cli('run', 'org.example.puzzle')
        self.assertEqual(r.returncode, 1)
        self.assertIn('wine-launch-not-wired', r.stderr)

    def test_msi_app_is_setup_pending(self):
        text = MANIFEST.replace('runner=native', 'runner=wine').replace('app/puzzle', 'app/setup.msi')
        entries = default_entries(text)
        entries[3] = lambda t: add_file(t, 'app/setup.msi', b'\xd0\xcf\x11\xe0' + b'\x00' * 60)
        r = self.run_cli('install', str(self.write(build(entries))))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual((self.apps / 'registry').read_text(),
                         'org.example.puzzle 1.2.0 wine setup-pending\n')


if __name__ == '__main__':
    unittest.main()
