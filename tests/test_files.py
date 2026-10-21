import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

BINARY = Path(os.environ.get('OMINX_FILES_BINARY', 'build/ominx-files')).resolve()


class FileManagerTests(unittest.TestCase):
    def run_files(self, *args, ok=True):
        result = subprocess.run([str(BINARY), *map(str, args)], capture_output=True, timeout=5)
        if ok:
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        else:
            self.assertNotEqual(result.returncode, 0)
        return result

    def test_listing_unicode_controls_and_invalid_bytes(self):
        with tempfile.TemporaryDirectory() as root:
            directory = Path(root)
            (directory / 'résumé notes.txt').write_text('hello')
            (directory / 'escape\x1b[2J\n".txt').write_text('data')
            raw = os.fsencode(root) + b'/invalid\xff'
            fd = os.open(raw, os.O_CREAT | os.O_WRONLY, 0o600)
            os.close(fd)
            result = self.run_files('list', root)
            self.assertNotIn(b'\x1b', result.stdout)
            parsed = json.loads(result.stdout)
            self.assertTrue(parsed['complete'])
            entries = parsed['entries']
            self.assertIn('résumé notes.txt', [entry['name'] for entry in entries])
            self.assertIn(b'invalid\xff'.hex(), [entry['name_hex'] for entry in entries])

    def test_copy_and_explicit_remove(self):
        with tempfile.TemporaryDirectory() as root:
            source, target = Path(root) / 'a', Path(root) / 'b'
            source.write_bytes(bytes(range(256)) * 1024)
            source.chmod(0o755)
            self.run_files('copy', source, target)
            self.assertEqual(source.read_bytes(), target.read_bytes())
            self.assertEqual(target.stat().st_mode & 0o111, 0)
            self.run_files('remove', target, ok=False)
            self.assertTrue(target.exists())
            self.run_files('remove', '--confirm', target)
            self.assertFalse(target.exists())

    def test_copy_refuses_overwrite_and_cleans_temporary(self):
        with tempfile.TemporaryDirectory() as root:
            source, target = Path(root) / 'a', Path(root) / 'b'
            source.write_text('source')
            target.write_text('preserve')
            self.run_files('copy', source, target, ok=False)
            self.run_files('copy', source, source, ok=False)
            self.assertEqual(target.read_text(), 'preserve')
            self.assertEqual(source.read_text(), 'source')
            self.assertEqual(sorted(p.name for p in Path(root).iterdir()), ['a', 'b'])

    def test_symlinks_not_followed_for_copy(self):
        with tempfile.TemporaryDirectory() as root:
            source = Path(root) / 'source'
            source.write_text('safe')
            link = Path(root) / 'link'
            link.symlink_to(source)
            self.run_files('copy', link, Path(root) / 'out', ok=False)
            self.run_files('copy', source, link, ok=False)
            self.assertEqual(source.read_text(), 'safe')
            info = json.loads(self.run_files('info', link).stdout)
            self.assertEqual(info['type'], 'symlink')

    def test_special_files_and_directories_refused(self):
        with tempfile.TemporaryDirectory() as root:
            pipe = Path(root) / 'fifo'
            os.mkfifo(pipe)
            self.run_files('copy', pipe, Path(root) / 'out', ok=False)
            self.run_files('copy', root, Path(root) / 'out', ok=False)
            self.run_files('remove', '--confirm', root, ok=False)
            self.assertTrue(Path(root).is_dir())

    def test_move_and_directory_operations(self):
        with tempfile.TemporaryDirectory() as root:
            a, b, c = [Path(root) / name for name in ('a', 'b', 'c')]
            self.run_files('mkdir', a)
            self.run_files('mkdir', b)
            self.run_files('move', a, b, ok=False)
            self.run_files('move', a, c)
            self.assertFalse(a.exists())
            self.assertTrue(c.is_dir())
            self.assertEqual(json.loads(self.run_files('info', c).stdout)['type'], 'directory')

    def test_missing_directory_returns_error(self):
        with tempfile.TemporaryDirectory() as root:
            result = self.run_files('list', Path(root) / 'absent', ok=False)
            self.assertIn('error', json.loads(result.stdout))


if __name__ == '__main__':
    unittest.main()
