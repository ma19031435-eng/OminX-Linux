import importlib.util
from pathlib import Path
import os
import struct
import subprocess
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('runtime',ROOT/'scripts/runtime-elf.py')
m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m)


class RuntimeTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.root=Path(self.temp.name)
        (self.root/'usr/lib').mkdir(parents=True)
        self.source=self.root/'source.c'; self.source.write_text('int exported(void) { return 7; }\n')
        self.lib=self.root/'usr/lib/libsample.so.1'
        subprocess.run(['cc','-shared','-fPIC','-nostdlib','-Wl,--soname,libsample.so.1',str(self.source),'-o',str(self.lib)],check=True)
        self.source.unlink()
    def tearDown(self):
        self.temp.cleanup()
    def test_shared_library_and_relative_alias(self):
        (self.root/'usr/lib/libsample.so').symlink_to('libsample.so.1')
        nodes,binaries=m.audit(self.root)
        self.assertEqual(binaries['usr/lib/libsample.so.1']['soname'],'libsample.so.1')
        self.assertIn('usr/lib/libsample.so',nodes)
    def test_host_interpreter_rejected(self):
        with self.assertRaisesRegex(ValueError,'interpreter'):
            m.elf(Path('/bin/ls').read_bytes())
    def test_truncated_elf(self):
        for data in (b'',b'\x7fELF',self.lib.read_bytes()[:100]):
            with self.assertRaises(ValueError):m.elf(data)
    def test_missing_dependency(self):
        source=self.root/'use.c'; source.write_text('extern int exported(void); int call(void){return exported();}')
        subprocess.run(['cc','-shared','-nostdlib','-fPIC',str(source),str(self.lib),'-o',str(self.root/'usr/lib/libuse.so')],check=True)
        source.unlink(); self.lib.unlink()
        with self.assertRaisesRegex(ValueError,'Unresolved dependency'):m.audit(self.root)
    def test_rpath_rejected(self):
        source=self.root/'bad.c'; source.write_text('int x;')
        subprocess.run(['cc','-shared','-nostdlib','-fPIC','-Wl,-rpath,/host/lib',str(source),'-o',str(self.lib)],check=True)
        source.unlink()
        with self.assertRaisesRegex(ValueError,'RPATH'):m.audit(self.root)
    def test_links_and_privileged_modes(self):
        link=self.root/'usr/lib/bad.so'
        for target in ('/etc/passwd','../../../etc/passwd','missing','bad.so'):
            link.symlink_to(target)
            with self.assertRaises(ValueError):m.audit(self.root)
            link.unlink()
        self.lib.chmod(0o4755)
        with self.assertRaisesRegex(ValueError,'permissions'):m.audit(self.root)
    def test_core_override_and_special_files(self):
        (self.root/'init').write_bytes(self.lib.read_bytes())
        with self.assertRaisesRegex(ValueError,'Disallowed'):m.audit(self.root)
        (self.root/'init').unlink()
        os.mkfifo(self.root/'usr/lib/fifo')
        with self.assertRaisesRegex(ValueError,'Special'):m.audit(self.root)
    def test_non_elf_dependency(self):
        source=self.root/'use.c'; source.write_text('extern int exported(void); int call(void){return exported();}')
        subprocess.run(['cc','-shared','-nostdlib','-fPIC',str(source),str(self.lib),'-o',str(self.root/'usr/lib/libuse.so')],check=True)
        source.unlink();self.lib.write_bytes(b'not ELF');self.lib.chmod(0o644)
        with self.assertRaisesRegex(ValueError,'not ELF'):m.audit(self.root)
