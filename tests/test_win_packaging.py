"""Windows services packaging: image contents, modes and determinism."""
import gzip
import importlib.util
import stat
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
INIT = Path(os.environ.get('OMINX_TEST_BINARY', ROOT / 'build/host/ominx'))
spec = importlib.util.spec_from_file_location('packaging', ROOT / 'scripts/make-initramfs.py')
packaging = importlib.util.module_from_spec(spec)
spec.loader.exec_module(packaging)


def entries(blob):
    data = gzip.decompress(blob)
    at, found = 0, {}
    while at + 110 <= len(data):
        assert data[at:at + 6] == b'070701'
        values = [int(data[at + 6 + i * 8:at + 14 + i * 8], 16) for i in range(13)]
        name_size, mode, size, uid, gid = values[11], values[1], values[6], values[2], values[3]
        name = data[at + 110:at + 110 + name_size - 1].decode()
        start = at + 110 + name_size
        start += -start % 4
        found[name] = (mode, data[start:start + size], uid, gid)
        at = start + size
        at += -at % 4
        if name == 'TRAILER!!!':
            break
    return found


class WinPackagingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.binary = INIT.read_bytes()
        cls.win = {name: cls.binary for name in packaging.WIN_BINARIES}

    def test_default_image_has_no_windows_services(self):
        image = entries(packaging.archive(self.binary))
        for path in ('bin/ominx-win', 'bin/ominx-wined', 'sbin/ominx-winsetup',
                     'etc/ominx/windows-compat'):
            self.assertNotIn(path, image)

    def test_win_image_contents_and_modes(self):
        image = entries(packaging.archive(self.binary, win=self.win))
        for path in ('bin/ominx-win', 'bin/ominx-wined', 'sbin/ominx-winsetup'):
            self.assertEqual(image[path][0], stat.S_IFREG | 0o755, path)
        self.assertEqual(image['bin/ominx-win-binfmt'][1], b'ominx-win')
        self.assertEqual(image['bin/ominx-win-binfmt'][0], stat.S_IFLNK | 0o777)
        self.assertEqual(image['etc/ominx/windows-compat'][1], b'1\n')
        desktop = image['usr/share/applications/ominx-windows.desktop'][1].decode()
        self.assertIn('Exec=/bin/ominx-win run %f', desktop)
        self.assertIn('application/x-msi', desktop)
        self.assertIn(b'*.exe', image['usr/share/mime/packages/ominx-windows.xml'][1])
        self.assertIn('var/lib/ominx/wine', image)
        # No profiles in the stage: the games directory is still present but empty.
        self.assertNotIn('usr/share/ominx/games/valorant.game', image)
        self.assertEqual(image['usr/share/ominx/games'][0], stat.S_IFDIR | 0o755)

    def test_game_profiles_ship_read_only(self):
        profiles = {'valorant.game': b'id = valorant\n', 'fortnite.game': b'id = fortnite\n'}
        image = entries(packaging.archive(self.binary, win=self.win, win_games=profiles))
        for name, data in profiles.items():
            path = 'usr/share/ominx/games/' + name
            self.assertEqual(image[path][0], stat.S_IFREG | 0o644, path)
            self.assertEqual(image[path][1], data)
        # Deterministic like every other bundle.
        self.assertEqual(packaging.archive(self.binary, win=self.win),
                         packaging.archive(self.binary, win=self.win))

    def test_wine_runtime_requires_services(self):
        with self.assertRaisesRegex(ValueError, 'requires the Windows services'):
            packaging.archive(self.binary, wine_runtime=self.root_dir())

    def root_dir(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        return Path(temp.name)

    def test_cli_requires_static_services(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            stage = root / 'win'
            stage.mkdir()
            for name in packaging.WIN_BINARIES:
                (stage / name).write_bytes(self.binary)
            (stage / 'ominx-wined').write_bytes(b'not an elf')
            output = root / 'out.gz'
            result = subprocess.run(
                ['python3', str(ROOT / 'scripts/make-initramfs.py'), str(INIT), str(output),
                 str(INIT), str(INIT), '--win-dir', str(stage)],
                capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('ELF', result.stdout + result.stderr)


if __name__ == '__main__':
    unittest.main()
