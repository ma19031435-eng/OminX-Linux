"""OPKGX v1: validation, install, upgrade, remove, list, and run.

Builds real .opkgx archives with tarfile (ustar) and drives
build/host/ominx-opkgx (or OMINX_OPKGX_BINARY) with a throwaway HOME.
The rules come from docs/opkgx-format.md."""
import io
import os
import stat
import struct
import zlib
import subprocess
import tarfile
import tempfile
import time
import unittest
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_wined import pe_image  # noqa: E402

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
        env.update(getattr(self, 'extra_env', {}))
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
        self.assertIn('Exec=ominx-opkgx run --notify org.example.puzzle\n', desk)
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

    def test_wine_app_without_service_reports_unavailable(self):
        text = MANIFEST.replace('runner=native', 'runner=wine').replace('app/puzzle', 'app/Puzzle.exe')
        entries = default_entries(text)
        entries[3] = lambda t: add_file(t, 'app/Puzzle.exe', b'MZ' + b'\x00' * 62)
        self.run_cli('install', str(self.write(build(entries))))
        r = self.run_cli('run', 'org.example.puzzle')
        self.assertEqual(r.returncode, 1)
        self.assertIn('wined-unavailable', r.stderr)

    def test_msi_app_is_setup_pending(self):
        text = MANIFEST.replace('runner=native', 'runner=wine').replace('app/puzzle', 'app/setup.msi')
        entries = default_entries(text)
        entries[3] = lambda t: add_file(t, 'app/setup.msi', b'\xd0\xcf\x11\xe0' + b'\x00' * 60)
        r = self.run_cli('install', str(self.write(build(entries))))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual((self.apps / 'registry').read_text(),
                         'org.example.puzzle 1.2.0 wine setup-pending\n')



OLE_MSI = b'\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1' + b'\x00' * 504


def make_wine_runtime(root, msi_exit=0, fail_wineboot=False):
    """A stub runtime that logs every call. msiexec exits with the code in root/msi-exit."""
    runtime = root / 'runtime'
    (runtime / 'bin').mkdir(parents=True)
    (runtime / 'VERSION').write_text('wine-stub-opkgx\n')
    (root / 'msi-exit').write_text(str(msi_exit))
    log = root / 'wine.log'
    wine = runtime / 'bin/wine'
    wine.write_text(f"""#!/bin/sh
printf 'PREFIX=%s ARGS=%s\\n' "$WINEPREFIX" "$*" >> "{log}"
case "$1" in
  wineboot)
    {'exit 7' if fail_wineboot else 'mkdir -p "$WINEPREFIX/drive_c/windows/system32" "$WINEPREFIX/drive_c/windows/syswow64"'}
    ;;
  wineserver) if [ "$2" = "-f" ]; then exec sleep 60; fi ;;
  msiexec) exit "$(cat "{root}/msi-exit")" ;;
esac
exit 0
""")
    wine.chmod(0o755)
    return runtime, log


class WineService(OpkgxCase):
    """Runs the real host-test daemon against the stub runtime."""

    def setUp(self):
        super().setUp()
        self.socket = str(self.root / 'wined.sock')
        self.process = None

    def tearDown(self):
        if self.process:
            try:
                self.service_request('QUIT\n')
                self.process.wait(timeout=5)
            except Exception:
                self.process.kill()
                self.process.wait(timeout=5)
            self.log_handle.close()
        super().tearDown()

    def start_service(self, runtime, fail_wineboot=False):
        import socket as sock
        env = dict(os.environ, HOME=str(self.home), OMINX_WINE_RUNTIME_DIR=str(runtime),
                   OMINX_WINEPREFIX=str(self.root / 'default-pfx'), OMINX_PROTON_DIR=str(self.root / 'proton'),
                   OMINX_WINED_SOCKET=self.socket, XDG_RUNTIME_DIR=str(self.root))
        self.daemon_log = self.root / 'daemon.log'
        self.log_handle = open(self.daemon_log, 'w')
        self.extra_env = {'OMINX_WINED_SOCKET': self.socket, 'XDG_RUNTIME_DIR': str(self.root),
                          'OMINX_WINE_RUNTIME_DIR': str(runtime)}
        self.process = subprocess.Popen([WINED_BIN, self.socket], env=env,
                                        stdout=subprocess.DEVNULL, stderr=self.log_handle, text=True)
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            if self.process.poll() is not None:
                self.fail('daemon exited: ' + self.daemon_log.read_text())
            try:
                self.service_request('STATUS\n')
                return
            except OSError:
                time.sleep(0.05)
        self.fail('daemon did not start')

    def service_request(self, payload):
        import socket as sock
        with sock.socket(sock.AF_UNIX, sock.SOCK_SEQPACKET) as client:
            client.settimeout(10)
            client.connect(self.socket)
            client.send(payload.encode())
            return client.recv(16384).decode()

    def cli(self, *args):
        return self.run_cli(*args)

    def app_prefix(self, app_id):
        return self.apps / app_id / 'prefix'

    def wait_for(self, predicate, timeout=20):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if predicate():
                return True
            time.sleep(0.05)
        return False

    def install_wine(self, exec_name, body, name='pkg.opkgx'):
        text = MANIFEST.replace('runner=native', 'runner=wine').replace('app/puzzle', exec_name)
        entries = default_entries(text)
        entries[3] = lambda t: add_file(t, exec_name, body, 0o644)
        r = self.run_cli('install', str(self.write(build(entries), name)))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_install_builds_the_app_prefix(self):
        runtime, _ = make_wine_runtime(self.root)
        self.start_service(runtime)
        self.install_wine('app/Puzzle.exe', pe_image())
        ready = self.app_prefix('org.example.puzzle') / '.ominx-setup-v1'
        self.assertTrue(self.wait_for(ready.exists), 'app prefix was not built at install time\n' +
                        self.daemon_log.read_text() + '\n' + str(sorted(p.name for p in ready.parent.iterdir())
                                                              if ready.parent.exists() else 'no prefix dir'))
        self.assertFalse((self.home / '.wine').exists() and os.path.islink(self.home / '.wine') and
                         os.readlink(self.home / '.wine') == str(self.app_prefix('org.example.puzzle')),
                         'an app prefix must not take over ~/.wine')

    def test_exe_runs_inside_its_own_prefix(self):
        runtime, log = make_wine_runtime(self.root)
        self.start_service(runtime)
        self.install_wine('app/Puzzle.exe', pe_image())
        self.assertTrue(self.wait_for(lambda: (self.app_prefix('org.example.puzzle') / '.ominx-setup-v1').exists()))
        r = self.cli('run', 'org.example.puzzle')
        self.assertEqual(r.returncode, 0, r.stderr)
        prefix = str(self.app_prefix('org.example.puzzle'))
        self.assertTrue(self.wait_for(lambda: log.exists() and f'PREFIX={prefix} ARGS=' in log.read_text()
                                      and 'Puzzle.exe' in log.read_text()), log.read_text() if log.exists() else '')
        self.assertNotIn('msiexec', log.read_text())

    def test_failed_prefix_setup_reports_not_ready(self):
        runtime, _ = make_wine_runtime(self.root, fail_wineboot=True)
        self.start_service(runtime)
        self.install_wine('app/Puzzle.exe', pe_image())
        time.sleep(0.5)
        r = self.cli('run', 'org.example.puzzle')
        self.assertEqual(r.returncode, 1)
        self.assertIn('prefix-not-ready', r.stderr)

    def test_msi_completes_and_becomes_ready(self):
        runtime, log = make_wine_runtime(self.root, msi_exit=0)
        self.start_service(runtime)
        self.install_wine('app/setup.msi', OLE_MSI)
        self.assertEqual((self.apps / 'registry').read_text(), 'org.example.puzzle 1.2.0 wine setup-pending\n')
        self.assertTrue(self.wait_for(lambda: (self.app_prefix('org.example.puzzle') / '.ominx-setup-v1').exists()))
        r = self.cli('run', 'org.example.puzzle')
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue(self.wait_for(lambda: (self.apps / 'org.example.puzzle' / '.last-run').exists()))
        self.assertEqual((self.apps / 'org.example.puzzle' / '.last-run').read_text(), 'exit=0\n')
        self.assertEqual(self.cli('list').stdout, 'org.example.puzzle 1.2.0 wine ready\n')
        self.assertIn('msiexec', log.read_text())

    def test_failed_msi_stays_pending(self):
        runtime, _ = make_wine_runtime(self.root, msi_exit=3)
        self.start_service(runtime)
        self.install_wine('app/setup.msi', OLE_MSI)
        self.assertTrue(self.wait_for(lambda: (self.app_prefix('org.example.puzzle') / '.ominx-setup-v1').exists()))
        self.assertEqual(self.cli('run', 'org.example.puzzle').returncode, 0)
        self.assertTrue(self.wait_for(lambda: (self.apps / 'org.example.puzzle' / '.last-run').exists()))
        self.assertEqual((self.apps / 'org.example.puzzle' / '.last-run').read_text(), 'exit=3\n')
        self.assertEqual(self.cli('list').stdout, 'org.example.puzzle 1.2.0 wine setup-pending\n')

    def test_msi_pending_until_installer_runs(self):
        runtime, _ = make_wine_runtime(self.root, msi_exit=0)
        self.start_service(runtime)
        self.install_wine('app/setup.msi', OLE_MSI)
        self.assertEqual(self.cli('list').stdout, 'org.example.puzzle 1.2.0 wine setup-pending\n')

    def test_daemon_refuses_escaping_requests(self):
        runtime, _ = make_wine_runtime(self.root)
        self.start_service(runtime)
        self.install_wine('app/Puzzle.exe', pe_image())
        self.assertEqual(self.service_request('APPRUN\t../../etc\tapp/Puzzle.exe\n'), 'ERR bad-app-id\n')
        self.assertEqual(self.service_request('APPRUN\torg.example.puzzle\t../secret.exe\n'), 'ERR bad-path\n')
        self.assertEqual(self.service_request('APPRUN\torg.example.puzzle\t/etc/passwd\n'), 'ERR bad-path\n')
        self.assertEqual(self.service_request('APPSETUP\t..\n'), 'ERR bad-app-id\n')
        self.assertEqual(self.service_request('APPRUN\torg.example.none\tapp/Puzzle.exe\n'), 'ERR not-installed\n')
        self.assertFalse((self.apps / 'org.example.none').exists(), 'an unknown id must not create a prefix')

    def test_native_apps_do_not_need_the_service(self):
        runtime, _ = make_wine_runtime(self.root)
        self.start_service(runtime)
        self.run_cli('install', str(self.write(build())))
        r = self.cli('list')
        self.assertIn('org.example.puzzle 1.2.0 native ready', r.stdout)



def pe_with_icon(icon_image, width=2, height=2, bits=32, with_resources=True):
    """A PE32+ executable whose .rsrc holds one group icon and one image."""
    group = struct.pack('<HHH', 0, 1, 1) + struct.pack(
        '<BBBBHHIH', width, height, 0, 0, 1, bits, len(icon_image), 1)
    buf = bytearray()

    def alloc(n):
        off = len(buf)
        buf.extend(b'\0' * n)
        return off

    root = alloc(16 + 16)
    # Each of the four directories has one 8-byte entry after its 16-byte header.
    g_names = alloc(16 + 8)
    g_langs = alloc(16 + 8)
    i_names = alloc(16 + 8)
    i_langs = alloc(16 + 8)
    g_data = alloc(16)
    i_data = alloc(16)
    g_blob = alloc(len(group))
    i_blob = alloc(len(icon_image))
    buf[g_blob:g_blob + len(group)] = group
    buf[i_blob:i_blob + len(icon_image)] = icon_image
    # Fill in the directories and data entries now that offsets are known.
    struct.pack_into('<HH', buf, g_names + 12, 0, 1)
    struct.pack_into('<II', buf, g_names + 16, 1, g_langs | 0x80000000)
    struct.pack_into('<HH', buf, g_langs + 12, 0, 1)
    struct.pack_into('<II', buf, g_langs + 16, 0x409, g_data)
    struct.pack_into('<HH', buf, i_names + 12, 0, 1)
    struct.pack_into('<II', buf, i_names + 16, 1, i_langs | 0x80000000)
    struct.pack_into('<HH', buf, i_langs + 12, 0, 1)
    struct.pack_into('<II', buf, i_langs + 16, 0x409, i_data)
    struct.pack_into('<IIII', buf, g_data, 0x1000 + g_blob, len(group), 0, 0)
    struct.pack_into('<IIII', buf, i_data, 0x1000 + i_blob, len(icon_image), 0, 0)
    # Root: type 14 (group icon) and type 3 (icon). Each points at its name directory.
    struct.pack_into('<HH', buf, root + 12, 0, 2)
    struct.pack_into('<II', buf, root + 16, 14, g_names | 0x80000000)
    struct.pack_into('<II', buf, root + 24, 3, i_names | 0x80000000)
    rsrc = bytes(buf)
    rsrc_padded = rsrc + b'\0' * (-len(rsrc) % 0x200)

    headers = bytearray(0x400)
    headers[0:2] = b'MZ'
    struct.pack_into('<I', headers, 0x3c, 0x80)
    headers[0x80:0x84] = b'PE\0\0'
    struct.pack_into('<HHIIIHH', headers, 0x84, 0x8664, 1, 0, 0, 0, 240, 0x0022)
    opt = 0x98
    struct.pack_into('<H', headers, opt, 0x20b)
    struct.pack_into('<I', headers, opt + 108, 16)
    if with_resources:
        struct.pack_into('<II', headers, opt + 112 + 2 * 8, 0x1000, len(rsrc))
    sec = opt + 240
    headers[sec:sec + 8] = b'.rsrc\0\0\0'
    struct.pack_into('<IIIIIIHHI', headers, sec + 8, len(rsrc), 0x1000, len(rsrc_padded), 0x400, 0, 0, 0, 0, 0x40000040)
    return bytes(headers) + rsrc_padded


def dib_icon(width, height, bpp, pixels_top_down, mask_rows=None):
    """BITMAPINFOHEADER plus bottom-up pixel rows and an AND mask. pixels are (r,g,b,a) rows top-down."""
    header = struct.pack('<IiiHHIIiiII', 40, width, height * 2, 1, bpp, 0, 0, 0, 0, 0, 0)
    stride = ((width * bpp + 31) // 32) * 4
    body = bytearray()
    for row in reversed(pixels_top_down):
        line = bytearray()
        for (r, g, b, a) in row:
            line += bytes([b, g, r] + ([a] if bpp == 32 else []))
        line += b'\0' * (stride - len(line))
        body += line
    mask_stride = ((width + 31) // 32) * 4
    mask = bytearray()
    for row in reversed(mask_rows or [[0] * width] * height):
        bits = bytearray(mask_stride)
        for x, bit in enumerate(row):
            if bit:
                bits[x // 8] |= 0x80 >> (x % 8)
        mask += bits
    return header + bytes(body) + bytes(mask)


def decode_png(data):
    """Minimal reader for the PNG this tool writes: IHDR, IDAT (zlib, filter 0), IEND."""
    assert data[:8] == b'\x89PNG\r\n\x1a\n', 'not a PNG'
    pos = 8
    idat = b''
    width = height = None
    while pos < len(data):
        length = struct.unpack('>I', data[pos:pos + 4])[0]
        kind = data[pos + 4:pos + 8]
        body = data[pos + 8:pos + 8 + length]
        crc = struct.unpack('>I', data[pos + 8 + length:pos + 12 + length])[0]
        assert crc == zlib.crc32(kind + body) & 0xffffffff, 'bad chunk CRC'
        if kind == b'IHDR':
            width, height, depth, colour = struct.unpack('>IIBB', body[:10])
            assert (depth, colour) == (8, 6), 'expected 8-bit RGBA'
        elif kind == b'IDAT':
            idat += body
        pos += 12 + length
    raw = zlib.decompress(idat)
    rows = []
    stride = width * 4 + 1
    for y in range(height):
        line = raw[y * stride:(y + 1) * stride]
        assert line[0] == 0, 'expected filter 0'
        rows.append([tuple(line[1 + x * 4:1 + x * 4 + 4]) for x in range(width)])
    return width, height, rows


class IconExtraction(OpkgxCase):
    def wine_package(self, exe_bytes, shipped_icon=None):
        text = MANIFEST.replace('runner=native', 'runner=wine').replace('app/puzzle', 'app/Puzzle.exe')
        if shipped_icon is None:
            text = text.replace('icon=icon.png\n', '')
        entries = [lambda t: add_file(t, 'opkgx.manifest', text.encode())]
        if shipped_icon is not None:
            entries.append(lambda t: add_file(t, 'icon.png', shipped_icon))
        entries.append(lambda t: add_dir(t, 'app'))
        entries.append(lambda t: add_file(t, 'app/Puzzle.exe', exe_bytes, 0o644))
        return build(entries)

    def install(self, data):
        r = self.run_cli('install', str(self.write(data)))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def app_dir(self):
        return self.apps / 'org.example.puzzle'

    def desktop_text(self):
        return (self.desktop / 'ominx-org.example.puzzle.desktop').read_text()

    def test_png_icon_is_copied_unchanged(self):
        png = PNG + b'\x00' * 64
        self.install(self.wine_package(pe_with_icon(png, width=32, height=32, bits=32)))
        self.assertEqual((self.app_dir() / 'icon.png').read_bytes(), png)
        self.assertIn(f'Icon={self.app_dir()}/icon.png\n', self.desktop_text())

    def test_bitmap_icon_becomes_png_with_correct_orientation(self):
        top_down = [[(255, 0, 0, 255), (255, 255, 255, 255)],   # top row: red, white
                    [(0, 0, 255, 255), (0, 255, 0, 255)]]        # bottom row: blue, green
        self.install(self.wine_package(pe_with_icon(dib_icon(2, 2, 32, top_down), width=2, height=2, bits=32)))
        width, height, rows = decode_png((self.app_dir() / 'icon.png').read_bytes())
        self.assertEqual((width, height), (2, 2))
        self.assertEqual(rows[0], [(255, 0, 0, 255), (255, 255, 255, 255)])
        self.assertEqual(rows[1], [(0, 0, 255, 255), (0, 255, 0, 255)])

    def test_24bit_icon_uses_the_and_mask_for_transparency(self):
        top_down = [[(10, 20, 30, 255), (40, 50, 60, 255)],
                    [(70, 80, 90, 255), (100, 110, 120, 255)]]
        icon = dib_icon(2, 2, 24, top_down, mask_rows=[[1, 0], [0, 0]])
        self.install(self.wine_package(pe_with_icon(icon, width=2, height=2, bits=24)))
        _, _, rows = decode_png((self.app_dir() / 'icon.png').read_bytes())
        self.assertEqual(rows[0][0], (10, 20, 30, 0))
        self.assertEqual(rows[0][1], (40, 50, 60, 255))

    def test_32bit_icon_with_zero_alpha_uses_the_mask(self):
        top_down = [[(255, 0, 0, 0), (0, 255, 0, 0)], [(0, 0, 255, 0), (9, 9, 9, 0)]]
        icon = dib_icon(2, 2, 32, top_down, mask_rows=[[0, 1], [0, 0]])
        self.install(self.wine_package(pe_with_icon(icon, width=2, height=2, bits=32)))
        _, _, rows = decode_png((self.app_dir() / 'icon.png').read_bytes())
        self.assertEqual(rows[0][0][3], 255)
        self.assertEqual(rows[0][1][3], 0)

    def test_program_without_icon_installs_with_generic_icon(self):
        self.install(self.wine_package(pe_with_icon(b'', with_resources=False)))
        self.assertFalse((self.app_dir() / 'icon.png').exists())
        self.assertNotIn('Icon=', self.desktop_text())

    def test_unsupported_bit_depth_is_skipped_not_fatal(self):
        icon = dib_icon(2, 2, 32, [[(1, 2, 3, 255)] * 2] * 2)
        icon8 = icon[:14] + struct.pack('<H', 8) + icon[16:]
        self.install(self.wine_package(pe_with_icon(icon8, width=2, height=2, bits=8)))
        self.assertFalse((self.app_dir() / 'icon.png').exists())

    def test_shipped_icon_wins_over_the_program_icon(self):
        shipped = PNG + b'\x01' * 8
        icon = dib_icon(2, 2, 32, [[(255, 0, 0, 255)] * 2] * 2)
        self.install(self.wine_package(pe_with_icon(icon, width=2, height=2, bits=32), shipped_icon=shipped))
        self.assertEqual((self.app_dir() / 'icon.png').read_bytes(), shipped)

    def test_truncated_resources_do_not_break_install(self):
        icon = dib_icon(2, 2, 32, [[(1, 2, 3, 255)] * 2] * 2)
        pe = pe_with_icon(icon, width=2, height=2, bits=32)
        self.install(self.wine_package(pe[:0x440]))  # cut inside the resource section
        self.assertFalse((self.app_dir() / 'icon.png').exists())

    def test_native_apps_never_get_an_extracted_icon(self):
        text = MANIFEST.replace('icon=icon.png\n', '')
        entries = [e for i, e in enumerate(default_entries(text)) if i != 1]  # no icon.png shipped
        self.install(build(entries))
        self.assertFalse((self.app_dir() / 'icon.png').exists())
        self.assertNotIn('Icon=', self.desktop_text())


class DesktopIntegration(OpkgxCase):
    """The file association and the notifications that make double-click install work."""

    @classmethod
    def setUpClass(cls):
        import importlib.util
        spec = importlib.util.spec_from_file_location('make_initramfs', ROOT / 'scripts/make-initramfs.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        cls.entry_text = module.OPKGX_DESKTOP_ENTRY.decode()
        cls.mime_text = module.OPKGX_MIME_XML.decode()

    def test_mime_xml_is_well_formed_and_maps_the_extension(self):
        import xml.etree.ElementTree as ET
        root = ET.fromstring(self.mime_text)
        ns = '{http://www.freedesktop.org/standards/shared-mime-info}'
        types = root.findall(ns + 'mime-type')
        self.assertEqual([t.get('type') for t in types], ['application/x-opkgx'])
        self.assertEqual([g.get('pattern') for g in types[0].findall(ns + 'glob')], ['*.opkgx'])

    def test_desktop_entry_handles_the_mime_type_and_installs_the_file(self):
        self.assertIn('MimeType=application/x-opkgx;', self.entry_text)
        self.assertIn('Exec=ominx-opkgx install --notify %f', self.entry_text)
        self.assertIn('[Desktop Entry]', self.entry_text)
        self.assertIn('Type=Application', self.entry_text)

    def test_notification_on_success_and_failure(self):
        fake = self.root / 'bin'
        fake.mkdir()
        log = self.root / 'notify.log'
        (fake / 'notify-send').write_text(f'#!/bin/sh\necho "$@" >> "{log}"\n')
        (fake / 'notify-send').chmod(0o755)
        self.extra_env = {'PATH': f"{fake}:{os.environ['PATH']}"}
        self.assertEqual(self.run_cli('install', '--notify', str(self.write(build()))).returncode, 0)
        self.assertIn('Application installed', log.read_text())
        bad = self.run_cli('install', '--notify', str(self.write(b'not a package', 'bad.opkgx')))
        self.assertEqual(bad.returncode, 1)
        self.assertIn('critical', log.read_text())
        self.assertIn('install failed', log.read_text())

    def test_missing_notify_send_is_not_an_error(self):
        self.extra_env = {'PATH': '/nonexistent'}
        r = self.run_cli('install', '--notify', str(self.write(build())))
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_flag_position_does_not_change_the_command(self):
        self.assertEqual(self.run_cli('--notify', 'validate', str(self.write(build()))).returncode, 0)
        self.assertEqual(self.run_cli('validate', '--notify', str(self.write(build()))).returncode, 0)


WINED_BIN = os.environ.get('OMINX_WINED_BINARY', str(ROOT / 'build/host/ominx-wined-test'))


class PackTests(OpkgxCase):
    def make_source(self, manifest=MANIFEST, extra=()):
        src = self.root / 'src'
        (src / 'app/data').mkdir(parents=True)
        (src / 'opkgx.manifest').write_text(manifest)
        (src / 'icon.png').write_bytes(PNG)
        (src / 'app/puzzle').write_bytes(SCRIPT)
        os.chmod(src / 'app/puzzle', 0o755)
        (src / 'app/data/level1.txt').write_text('level data')
        for rel, data in extra:
            (src / rel).parent.mkdir(parents=True, exist_ok=True)
            (src / rel).write_bytes(data)
        return src

    def pack(self, src, out='out.opkgx'):
        return self.run_cli('pack', str(src), str(self.root / out))

    def test_pack_then_install_round_trip(self):
        src = self.make_source()
        r = self.pack(src)
        self.assertEqual(r.returncode, 0, r.stderr)
        r = self.run_cli('install', str(self.root / 'out.opkgx'))
        self.assertEqual(r.returncode, 0, r.stderr)
        app = self.apps / 'org.example.puzzle'
        self.assertEqual((app / 'app/data/level1.txt').read_text(), 'level data')
        self.assertTrue(os.access(app / 'app/puzzle', os.X_OK))
        self.assertEqual((app / 'icon.png').read_bytes(), PNG)

    def test_pack_is_deterministic(self):
        src = self.make_source()
        self.pack(src, 'a.opkgx')
        self.pack(src, 'b.opkgx')
        self.assertEqual((self.root / 'a.opkgx').read_bytes(), (self.root / 'b.opkgx').read_bytes())

    def test_pack_puts_manifest_first(self):
        src = self.make_source()
        self.pack(src)
        import tarfile
        with tarfile.open(self.root / 'out.opkgx') as t:
            self.assertEqual(t.getnames()[0], 'opkgx.manifest')

    def test_pack_refuses_missing_manifest(self):
        src = self.make_source()
        (src / 'opkgx.manifest').unlink()
        r = self.pack(src)
        self.assertEqual(r.returncode, 1)
        self.assertIn('manifest-missing', r.stderr)
        self.assertFalse((self.root / 'out.opkgx').exists())

    def test_pack_refuses_invalid_manifest(self):
        src = self.make_source(MANIFEST.replace('id=org.example.puzzle', 'id=Bad_ID'))
        r = self.pack(src)
        self.assertEqual(r.returncode, 1)
        self.assertIn('bad-id', r.stderr)

    def test_pack_refuses_symlinks(self):
        src = self.make_source()
        os.symlink('/etc/passwd', src / 'app/leak')
        r = self.pack(src)
        self.assertEqual(r.returncode, 1)
        self.assertIn('link-entry', r.stderr)
        self.assertFalse((self.root / 'out.opkgx').exists())
        self.assertFalse((self.root / 'out.opkgx.tmp').exists())

    def test_pack_handles_long_paths(self):
        deep = 'app/' + '/'.join(['d' * 40] * 4) + '/file.dat'
        src = self.make_source(extra=[(deep, b'deep')])
        r = self.pack(src)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.run_cli('validate', str(self.root / 'out.opkgx')).returncode, 0)

    def test_pack_refuses_paths_too_long(self):
        # Each component fits; the whole path is over the 255-byte limit.
        long_name = 'app/' + '/'.join(['x' * 100, 'y' * 100, 'z' * 100])
        src = self.make_source(extra=[(long_name, b'x')])
        r = self.pack(src)
        self.assertEqual(r.returncode, 1)
        self.assertIn('path-too-long', r.stderr)

    def test_pack_missing_source(self):
        r = self.run_cli('pack', str(self.root / 'nope'), str(self.root / 'out.opkgx'))
        self.assertEqual(r.returncode, 1)
        self.assertIn('source-unreadable', r.stderr)


if __name__ == '__main__':
    unittest.main()
