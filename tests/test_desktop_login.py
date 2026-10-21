"""Packaging rules for the optional graphical login media."""
import importlib.util
import os
from pathlib import Path
import stat
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('packaging', ROOT / 'scripts/make-initramfs.py')
packaging = importlib.util.module_from_spec(spec)
spec.loader.exec_module(packaging)
hash_spec = importlib.util.spec_from_file_location('hashing', ROOT / 'scripts/ominx-hash.py')
hashing = importlib.util.module_from_spec(hash_spec)
hash_spec.loader.exec_module(hashing)
INIT = Path(os.environ.get('OMINX_TEST_BINARY', ROOT / 'build/host/ominx'))
FILES = Path(os.environ.get('OMINX_FILES_BINARY', ROOT / 'build/host/ominx-files'))
CONTROL = Path(os.environ.get('OMINX_CONTROL_BINARY', ROOT / 'build/host/ominx-control'))


def entries(blob):
    import gzip
    data = gzip.decompress(blob)
    found = {}
    offset = 0
    while True:
        assert data[offset:offset + 6] == b'070701', 'bad magic'
        values = [int(data[offset + 6 + i * 8: offset + 14 + i * 8], 16) for i in range(13)]
        mode, uid, gid, filesize, name_size = values[1], values[2], values[3], values[6], values[11]
        name = data[offset + 110: offset + 110 + name_size - 1].decode()
        body_start = offset + 110 + name_size
        body_start += -body_start % 4
        if name == 'TRAILER!!!':
            break
        found[name] = (mode, uid, gid, data[body_start:body_start + filesize])
        offset = body_start + filesize
        offset += -offset % 4
    return found


class GraphicalLoginPackagingTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.directory = Path(self.temporary.name)
        # Any static ELF stands in: packaging rules are about structure, not code.
        binary = FILES.read_bytes()
        for name in packaging.LOGIN_BINARIES + packaging.LOGIN_LICENSES:
            (self.directory / name).write_bytes(binary if name not in packaging.LOGIN_LICENSES else b'notice\n')
        self.accounts = self.directory / 'accounts'
        self.accounts.write_text(
            'ominx:1000:1000:/home/ominx:/bin/ominx-desktop:0:%s\n'
            'guest:1002:1002:/home/guest:/bin/ominx-desktop:1:!\n' % hashing.generate('demo', 'testsalt0000000'))

    def tearDown(self):
        self.temporary.cleanup()

    def login_bundle(self):
        bundle = {name: packaging.static_elf(self.directory / name) for name in packaging.LOGIN_BINARIES}
        bundle.update({name: (self.directory / name).read_bytes() for name in packaging.LOGIN_LICENSES})
        return bundle

    def test_default_media_is_unchanged(self):
        image = entries(packaging.archive(INIT.read_bytes(), FILES.read_bytes(), CONTROL.read_bytes()))
        self.assertNotIn('etc/ominx/accounts', image)
        self.assertNotIn('sbin/ominx-seat', image)
        self.assertNotIn('greeter:x:1001', image['etc/passwd'][3].decode())

    def test_login_media_contents_and_modes(self):
        blob = packaging.archive(INIT.read_bytes(), FILES.read_bytes(), CONTROL.read_bytes(),
                                 login=self.login_bundle(), accounts=packaging.account_records(self.accounts))
        image = entries(blob)
        for name in ('sbin/ominx-login', 'sbin/ominx-seat', 'bin/ominx-passwd', 'bin/ominx-desktop'):
            self.assertEqual(stat.S_IMODE(image[name][0]), 0o755, name)
        mode, uid, gid, data = image['etc/ominx/accounts']
        self.assertEqual((stat.S_IMODE(mode), uid, gid), (0o400, 0, 0))
        self.assertEqual(data, self.accounts.read_bytes())
        self.assertIn('greeter:x:1001:1001', image['etc/passwd'][3].decode())
        self.assertIn('guest:x:1002:1002', image['etc/passwd'][3].decode())
        self.assertEqual(stat.S_IMODE(image['home/guest'][0]), 0o700)
        self.assertEqual(image['home/guest'][1], 1002)
        self.assertEqual(stat.S_IMODE(image['etc/ominx/graphical-login'][0]), 0o444)
        self.assertIn('usr/share/licenses/ominx-desktop-shell/QTBASE-LICENSES', image)

    def test_partial_login_packaging_refused(self):
        with self.assertRaisesRegex(ValueError, 'both'):
            packaging.archive(INIT.read_bytes(), FILES.read_bytes(), CONTROL.read_bytes(),
                              login=self.login_bundle())
        with self.assertRaisesRegex(ValueError, 'both'):
            packaging.archive(INIT.read_bytes(), FILES.read_bytes(), CONTROL.read_bytes(),
                              accounts=packaging.account_records(self.accounts))

    def test_account_record_rules(self):
        valid = 'ominx:1000:1000:/home/ominx:/bin/ominx-desktop:0:%s\n' % hashing.generate('x', 'testsalt0000000')
        for broken in ('', 'ominx:1000:1000:/home/ominx:/bin/sh:0:!\n',
                       'ominx:1001:1001:/home/ominx:/bin/ominx-desktop:0:!\n',
                       'greeter:1002:1002:/home/greeter:/bin/ominx-desktop:0:!\n',
                       'root:1002:1002:/home/root:/bin/ominx-desktop:0:!\n',
                       'ominx:1000:1000:/home/someone:/bin/ominx-desktop:0:!\n',
                       'ominx:1000:1000:/home/ominx:/bin/ominx-desktop:2:!\n',
                       'ominx:1000:1000:/home/ominx:/bin/ominx-desktop:0:$6$short\n',
                       'OMINX:1000:1000:/home/OMINX:/bin/ominx-desktop:0:!\n',
                       'ominx:1000:1000:/home/ominx:/bin/ominx-desktop:0:!\nominx:1002:1002:/home/ominx:/bin/ominx-desktop:0:!\n',
                       valid.replace('\n', '')):
            with self.subTest(record=broken[:40]), tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / 'accounts'
                path.write_text(broken)
                with self.assertRaises(ValueError):
                    packaging.account_records(path)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'accounts'
            path.write_text(valid)
            self.assertEqual(packaging.account_records(path), valid.encode())


if __name__ == '__main__':
    unittest.main()
