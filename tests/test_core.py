import gzip
import os
import importlib.util
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
BINARY = Path(os.environ.get('OMINX_TEST_BINARY', ROOT / 'build/ominx'))
spec = importlib.util.spec_from_file_location('initramfs', ROOT / 'scripts/make-initramfs.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class CoreTests(unittest.TestCase):
    def shell(self, text, cwd=None):
        return subprocess.run([str(BINARY), '--shell'], input=text,
                              text=True, capture_output=True, cwd=cwd, timeout=5)

    def test_files(self):
        with tempfile.TemporaryDirectory() as directory:
            result = self.shell('mkdir work\ncd work\nwrite note hello OminX\ncat note\npwd\nls\nexit\n', directory)
            self.assertEqual(result.returncode, 0)
            self.assertEqual(result.stderr, '')
            self.assertEqual((Path(directory) / 'work/note').read_text(), 'hello OminX\n')
            self.assertIn('hello OminX', result.stdout)
            self.assertIn('/work', result.stdout)

    def test_copy_move_delete(self):
        with tempfile.TemporaryDirectory() as directory:
            result = self.shell('write original keepme\ncp original copy\ncp original original\n'
                                'mv copy moved\ncat moved\nrm moved\nexit\n', directory)
            self.assertIn('File exists', result.stderr)
            self.assertEqual((Path(directory) / 'original').read_text(), 'keepme\n')
            self.assertFalse((Path(directory) / 'copy').exists())
            self.assertFalse((Path(directory) / 'moved').exists())

    def test_storage_host_guard(self):
        result = self.shell('attach /dev/does-not-exist\ndetach\nexit\n')
        self.assertEqual(result.stdout.count('Disk attachment only'), 2)
        self.assertEqual(result.stderr, '')

    def test_quoted_names(self):
        with tempfile.TemporaryDirectory() as directory:
            result = self.shell('write "résumé notes.txt" "hello world"\n'
                                "cat 'résumé notes.txt'\n"
                                'echo a\\ b "" c\n'
                                'echo "unterminated\n'
                                'echo recovered\nexit\n', directory)
            self.assertIn('hello world', result.stdout)
            self.assertIn('a b  c', result.stdout)
            self.assertIn('Malformed quoting', result.stdout)
            self.assertIn('recovered', result.stdout)
            self.assertEqual(result.stderr, '')

    def test_errors_and_safety(self):
        result = self.shell('cat /nonexistent-ominx-file\ncd\nreboot\npoweroff\nhelp\nexit\n')
        self.assertIn('No such file', result.stderr)
        self.assertIn('wrong argument count', result.stdout)
        self.assertEqual(result.stdout.count('Power controls only'), 2)
        self.assertIn('quotes', result.stdout)

    def test_limits_and_eof(self):
        result = self.shell('echo ' + 'word ' * 80 + '\nuname\n')
        self.assertIn('Too many arguments', result.stdout)
        self.assertIn('Linux', result.stdout)
        self.assertEqual(result.returncode, 0)

    def test_explicit_execution(self):
        result = self.shell('/bin/echo external-ok\nexit\n')
        self.assertIn('external-ok', result.stdout)

    def test_archive(self):
        binary = BINARY.read_bytes()
        files = Path(os.environ['OMINX_FILES_BINARY']).read_bytes()
        packed = module.archive(binary, files)
        self.assertEqual(packed, module.archive(binary, files))
        raw = gzip.decompress(packed)
        entries = {}
        pos = 0
        while True:
            self.assertEqual(raw[pos:pos + 6], b'070701')
            fields = [int(raw[pos + 6 + i * 8:pos + 14 + i * 8], 16) for i in range(13)]
            start = pos + 110
            name = raw[start:start + fields[11] - 1].decode()
            data_start = (start + fields[11] + 3) & ~3
            data = raw[data_start:data_start + fields[6]]
            entries[name] = (fields, data)
            pos = (data_start + fields[6] + 3) & ~3
            if name == 'TRAILER!!!':
                break
        self.assertEqual(entries['init'][1], binary)
        self.assertEqual(entries['bin/ominx-files'][1], files)
        self.assertEqual(entries['init'][0][1], 0o100755)
        self.assertEqual(entries['dev/console'][0][9:11], [5, 1])
        self.assertEqual(entries['tmp'][0][1], 0o41777)
        self.assertEqual(entries['root'][0][1], 0o40700)
        self.assertEqual(entries['home/ominx'][0][2:4], [1000, 1000])
        self.assertEqual(entries['home/ominx'][0][1], 0o40700)
        self.assertEqual(entries['etc/shadow'][0][1], 0o100600)
        self.assertIn(b'root:!', entries['etc/shadow'][1])
        self.assertIn(b'ID=ominx', entries['etc/os-release'][1])

    def test_reject_malformed_elf(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / 'broken'
            for data in (b'', b'\x7fELF', b'\x7fELF\x02\x01' + b'\x00' * 58):
                path.write_bytes(data)
                with self.assertRaises(ValueError):
                    module.static_elf(path)

    def test_reject_dynamic_binary(self):
        with tempfile.TemporaryDirectory() as directory:
            result = subprocess.run(['python3', str(ROOT / 'scripts/make-initramfs.py'),
                                     '/bin/ls', directory + '/bad.gz', str(BINARY)], capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertFalse(Path(directory, 'bad.gz').exists())


if __name__ == '__main__':
    unittest.main()
