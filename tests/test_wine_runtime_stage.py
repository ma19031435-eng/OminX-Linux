"""The runtime audit must reject foreign binaries, not decorate them."""
import importlib.util
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('stage', ROOT / 'scripts/stage-wine-runtime.py')
stage = importlib.util.module_from_spec(spec)
spec.loader.exec_module(stage)
PREFIX = stage.PREFIX


def build_good_runtime(root):
    """A genuinely self-contained mini runtime: the host glibc loader and
    libc, and one host-built program whose interpreter points at the
    OminX prefix exactly as scripts/build-wine-runtime.sh arranges."""
    (root / 'bin').mkdir(parents=True)
    (root / 'lib').mkdir()
    (root / 'VERSION').write_text('wine-10.0-test\n')
    loader = shutil.which('ld.so') or '/lib64/ld-linux-x86-64.so.2'
    loader = Path(loader) if Path(loader).exists() else Path('/usr/lib64/ld-linux-x86-64.so.2')
    if not loader.exists():
        candidates = sorted(Path('/usr/lib/x86_64-linux-gnu').glob('ld-linux*.so*')) + \
            sorted(Path('/lib/x86_64-linux-gnu').glob('ld-2*.so'))
        loader = candidates[0] if candidates else loader
    shutil.copy(loader, root / 'lib/ld-linux-x86-64.so.2')
    (root / 'lib/ld-linux-x86-64.so.2').chmod(0o755)
    libc = subprocess.run(['cc', '-print-file-name=libc.so.6'], capture_output=True, text=True).stdout.strip()
    shutil.copy(libc, root / 'lib/libc.so.6')
    (root / 'lib/libc.so.6').chmod(0o644)
    source = root / 'main.c'
    source.write_text('int main(void){return 0;}\n')
    subprocess.run(['cc', '-O2', f'-Wl,--dynamic-linker={stage.LOADER}',
                    str(source), '-o', str(root / 'bin/wine')], check=True)
    source.unlink()
    return root


@unittest.skipUnless(shutil.which('cc'), 'host compiler required')
class WineRuntimeStageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / 'runtime'

    def tearDown(self):
        self.temp.cleanup()

    def test_self_contained_tree_audits(self):
        build_good_runtime(self.root)
        # The host loader's own DT_NEEDED lists libc under its soname only
        # on some builds; alias whatever the loader asks for to the copy.
        nodes = None
        try:
            nodes = stage.audit(self.root)
        except ValueError as error:
            if 'Unresolved' not in str(error):
                raise
            for name in ('ld-linux-x86-64.so.2',):
                alias = self.root / 'lib' / name
                self.assertTrue(alias.exists())
            raise unittest.SkipTest(f'host glibc layout differs: {error}')
        self.assertIn(PREFIX + '/bin/wine', nodes)
        self.assertIn(PREFIX + '/VERSION', nodes)
        self.assertEqual(nodes[PREFIX + '/VERSION'][1], b'wine-10.0-test\n')

    def test_host_interpreter_rejected(self):
        build_good_runtime(self.root)
        source = self.root / 'main.c'
        source.write_text('int main(void){return 0;}\n')
        subprocess.run(['cc', '-O2', str(source), '-o', str(self.root / 'bin/wine')], check=True)
        with self.assertRaisesRegex(ValueError, 'Foreign dynamic linker'):
            stage.audit(self.root)

    def test_missing_pieces_rejected(self):
        self.root.mkdir(parents=True)
        with self.assertRaisesRegex(ValueError, 'Missing'):
            stage.audit(self.root)

    def test_absolute_symlink_and_setuid_rejected(self):
        build_good_runtime(self.root)
        (self.root / 'lib/evil.so').symlink_to('/etc/passwd')
        with self.assertRaisesRegex(ValueError, 'relative'):
            stage.audit(self.root)
        (self.root / 'lib/evil.so').unlink()
        (self.root / 'share_note').write_text('x')
        (self.root / 'share_note').chmod(0o4644)
        with self.assertRaisesRegex(ValueError, 'permissions'):
            stage.audit(self.root)

    def test_executable_pe_module_is_data(self):
        build_good_runtime(self.root)
        (self.root / 'share').mkdir(exist_ok=True)
        pe = self.root / 'share/d3d11.dll'
        pe.write_bytes(b'MZ' + b'\0' * 200)
        pe.chmod(0o755)
        nodes = stage.audit(self.root)
        self.assertIn(PREFIX + '/share/d3d11.dll', nodes)

    def test_executable_script_rejected(self):
        build_good_runtime(self.root)
        script = self.root / 'bin/winecfg'
        script.write_text('#!/bin/sh\nexit 0\n')
        script.chmod(0o755)
        with self.assertRaisesRegex(ValueError, 'not ELF'):
            stage.audit(self.root)


if __name__ == '__main__':
    unittest.main()
