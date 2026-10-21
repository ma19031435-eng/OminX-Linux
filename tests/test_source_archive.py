import hashlib
import importlib.util
import io
from pathlib import Path
import tarfile
import tempfile
import unittest

spec = importlib.util.spec_from_file_location('source_archive', Path(__file__).resolve().parents[1] / 'scripts/fetch-archive.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


class SourceArchiveTests(unittest.TestCase):
    def fixture(self, directory, names=('upstream/file',), link=False):
        archive = Path(directory) / 'source.tar'
        with tarfile.open(archive, 'w') as output:
            for name in names:
                info = tarfile.TarInfo(name)
                if link:
                    info.type = tarfile.SYMTYPE
                    info.linkname = '../../escape'
                    output.addfile(info)
                else:
                    info.size = 6
                    info.mode = 0o644
                    output.addfile(info, io.BytesIO(b'source'))
        return archive, hashlib.sha256(archive.read_bytes()).hexdigest()

    def test_verified_reuse_and_mutation(self):
        with tempfile.TemporaryDirectory() as directory:
            path, digest = self.fixture(directory)
            dest = Path(directory) / 'tree'
            m.unpack(path, digest, dest)
            self.assertEqual((dest / 'file').read_bytes(), b'source')
            m.unpack(path, digest, dest)
            (dest / 'file').write_bytes(b'changed')
            with self.assertRaisesRegex(ValueError, 'Modified'):
                m.unpack(path, digest, dest)

    def test_digest(self):
        with tempfile.TemporaryDirectory() as directory:
            path, _ = self.fixture(directory)
            dest = Path(directory) / 'tree'
            with self.assertRaisesRegex(ValueError, 'SHA256 mismatch'):
                m.unpack(path, '0' * 64, dest)
            self.assertFalse(dest.exists())

    def test_unsafe_members(self):
        cases = [(('upstream/../escape',), False), (('/absolute/file',), False),
                 (('upstream/link',), True), (('upstream/file', 'upstream/file'), False),
                 (('one/file', 'two/file'), False)]
        for names, link in cases:
            with self.subTest(names=names), tempfile.TemporaryDirectory() as directory:
                path, digest = self.fixture(directory, names, link)
                dest = Path(directory) / 'tree'
                with self.assertRaises(ValueError):
                    m.unpack(path, digest, dest)
                self.assertFalse(dest.exists())

    def test_added_file_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path, digest = self.fixture(directory)
            dest = Path(directory) / 'tree'
            m.unpack(path, digest, dest)
            (dest / 'injected').write_text('not upstream')
            with self.assertRaisesRegex(ValueError, 'Modified'):
                m.unpack(path, digest, dest)

    def test_opt_in_internal_file_aliases(self):
        with tempfile.TemporaryDirectory() as directory:
            path, _ = self.fixture(directory)
            with tarfile.open(path, 'a') as out:
                for name, target, kind in [('upstream/alias', 'file', tarfile.SYMTYPE),
                                            ('upstream/hard', 'upstream/alias', tarfile.LNKTYPE)]:
                    info=tarfile.TarInfo(name);info.type=kind;info.linkname=target;out.addfile(info)
            digest=hashlib.sha256(path.read_bytes()).hexdigest();dest=Path(directory)/'tree'
            with self.assertRaises(ValueError):m.unpack(path,digest,dest)
            m.unpack(path,digest,dest,allow_internal_links=True)
            self.assertFalse((dest/'alias').is_symlink())
            self.assertEqual((dest/'hard').read_bytes(),b'source')
            m.unpack(path,digest,dest,allow_internal_links=True)
            (dest/'alias').write_bytes(b'change')
            with self.assertRaises(ValueError):m.unpack(path,digest,dest,allow_internal_links=True)

    def test_internal_alias_restrictions(self):
        for target in ('/etc/passwd','../../escape','missing','alias'):
            with self.subTest(target=target),tempfile.TemporaryDirectory() as directory:
                path,_=self.fixture(directory)
                with tarfile.open(path,'a') as out:
                    info=tarfile.TarInfo('upstream/alias');info.type=tarfile.SYMTYPE;info.linkname=target;out.addfile(info)
                digest=hashlib.sha256(path.read_bytes()).hexdigest();dest=Path(directory)/'tree'
                with self.assertRaises(ValueError):m.unpack(path,digest,dest,allow_internal_links=True)
                self.assertFalse(dest.exists())

    def test_expansion_limit(self):
        with tempfile.TemporaryDirectory() as directory:
            path,digest=self.fixture(directory)
            with self.assertRaises(ValueError):m.unpack(path,digest,Path(directory)/'tree',max_unpacked=5)
