"""Header classification must be exact: every later launch trusts it."""
import ctypes
from pathlib import Path
import struct
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
OLE = bytes.fromhex('d0cf11e0a1b11ae1')


def pe_image(machine=0x8664, bits=64, dll=False, subsystem=2, dotnet=False,
             sections=3, optional=True, size=1024):
    data = bytearray(size)
    data[0:2] = b'MZ'
    struct.pack_into('<I', data, 0x3c, 128)
    data[128:132] = b'PE\0\0'
    struct.pack_into('<H', data, 132, machine)
    struct.pack_into('<H', data, 134, sections)
    optional_size = 240 if bits == 64 else 224
    struct.pack_into('<H', data, 148, optional_size if optional else 0)
    struct.pack_into('<H', data, 150, 0x2000 if dll else 0x0022)
    if optional:
        opt = 152
        struct.pack_into('<H', data, opt, 0x20b if bits == 64 else 0x10b)
        struct.pack_into('<H', data, opt + 68, subsystem)
        struct.pack_into('<I', data, opt + (108 if bits == 64 else 92), 16)
        if dotnet:
            struct.pack_into('<II', data, opt + (112 if bits == 64 else 96) + 14 * 8,
                             0x2000, 72)
    return bytes(data)


class Info(ctypes.Structure):
    _fields_ = [('kind', ctypes.c_int), ('arch', ctypes.c_int), ('bits', ctypes.c_int),
                ('subsystem', ctypes.c_int), ('dotnet', ctypes.c_int),
                ('sections', ctypes.c_uint), ('file_size', ctypes.c_ulonglong),
                ('error', ctypes.c_char * 64)]


class PeInspectorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        library = Path(cls.temp.name) / 'pe.so'
        subprocess.run(['cc', '-shared', '-fPIC', '-O2', '-Wall', '-Wextra', '-Werror',
                        str(ROOT / 'src/lib/pe.c'), '-o', str(library)], check=True)
        cls.lib = ctypes.CDLL(str(library))
        cls.lib.ominx_pe_inspect_bytes.argtypes = [ctypes.c_char_p, ctypes.c_size_t,
                                                   ctypes.c_ulonglong, ctypes.POINTER(Info)]
        cls.lib.ominx_pe_inspect_bytes.restype = ctypes.c_int
        cls.lib.ominx_pe_kind_name.restype = ctypes.c_char_p
        cls.lib.ominx_pe_arch_name.restype = ctypes.c_char_p
        cls.lib.ominx_pe_suffix.argtypes = [ctypes.c_char_p]
        cls.lib.ominx_pe_suffix.restype = ctypes.c_int

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def inspect(self, data, file_size=None):
        info = Info()
        result = self.lib.ominx_pe_inspect_bytes(
            data, len(data), len(data) if file_size is None else file_size, ctypes.byref(info))
        return result, info

    def test_64_bit_gui_program(self):
        result, info = self.inspect(pe_image())
        self.assertEqual(result, 0)
        self.assertEqual((info.kind, info.arch, info.bits, info.subsystem), (1, 2, 64, 2))
        self.assertEqual(self.lib.ominx_pe_kind_name(info.kind), b'exe')
        self.assertEqual(self.lib.ominx_pe_arch_name(info.arch), b'x86-64')

    def test_32_bit_console_and_dotnet(self):
        result, info = self.inspect(pe_image(machine=0x014c, bits=32, subsystem=3, dotnet=True))
        self.assertEqual(result, 0)
        self.assertEqual((info.bits, info.subsystem, info.dotnet), (32, 3, 1))

    def test_dll_is_never_a_program(self):
        result, info = self.inspect(pe_image(dll=True))
        self.assertEqual((result, info.kind), (0, 2))

    def test_arm64_identified_for_refusal(self):
        result, info = self.inspect(pe_image(machine=0xaa64))
        self.assertEqual((result, info.arch, info.bits), (0, 4, 64))

    def test_msi_magic_and_truncated_msi(self):
        result, info = self.inspect(OLE + b'\0' * 600)
        self.assertEqual((result, info.kind), (0, 3))
        result, info = self.inspect(OLE + b'\0' * 40)
        self.assertEqual((result, info.kind, info.error), (-1, 4, b'truncated-msi'))

    def test_other_files_are_unknown_not_invalid(self):
        for data in (b'\x7fELF' + b'\0' * 100, b'hello world, plain text', b'#!/bin/sh\nexit\n'):
            result, info = self.inspect(data)
            self.assertEqual((result, info.kind), (0, 0), data[:8])

    def test_malformed_headers(self):
        cases = {
            'truncated-dos-header': b'MZ' + b'\0' * 10,
            'empty-file': b'',
            'bad-pe-signature': pe_image().replace(b'PE\0\0', b'PX\0\0'),
            'bad-section-count': pe_image(sections=0),
            'unsupported-machine': pe_image(machine=0x9999),
            'bits-mismatch': pe_image(machine=0x014c, bits=64),
        }
        for error, data in cases.items():
            with self.subTest(error=error):
                result, info = self.inspect(data)
                self.assertEqual(result, -1)
                self.assertEqual(info.error.decode(), error)

    def test_header_window_never_reads_past_buffer(self):
        # A 600-byte window over a 1 MiB file whose PE header sits at 128
        # still classifies, but a header beyond the window is refused.
        result, _ = self.inspect(pe_image(size=600), file_size=1 << 20)
        self.assertEqual(result, 0)
        far = bytearray(512)
        far[0:2] = b'MZ'
        struct.pack_into('<I', far, 0x3c, 4096)
        result, info = self.inspect(bytes(far), file_size=1 << 20)
        self.assertEqual((result, info.error), (-1, b'truncated-header'))

    def test_suffix_is_only_a_hint(self):
        self.assertEqual(self.lib.ominx_pe_suffix(b'/games/Setup.EXE'), 1)
        self.assertEqual(self.lib.ominx_pe_suffix(b'/games/app.Msi'), 2)
        self.assertEqual(self.lib.ominx_pe_suffix(b'/games/d3d11.dll'), 3)
        self.assertEqual(self.lib.ominx_pe_suffix(b'/games/executable'), 0)
        self.assertEqual(self.lib.ominx_pe_suffix(b'/games/a.exe.backup'), 0)


if __name__ == '__main__':
    unittest.main()
