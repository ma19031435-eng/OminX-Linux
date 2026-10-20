#!/usr/bin/env python3
"""Deterministic Linux newc initramfs, without root privileges or host cpio."""
import gzip
from pathlib import Path
import stat
import struct
import sys


def archive(binary, files=None):
    output = bytearray()
    def entry(name, mode, data=b'', major=0, minor=0, uid=0, gid=0):
        encoded = name.encode() + b'\0'
        values = [1, mode, uid, gid, 1, 0, len(data), 0, 0, major, minor, len(encoded), 0]
        output.extend(b'070701' + b''.join(f'{v:08x}'.encode() for v in values))
        output.extend(encoded)
        output.extend(b'\0' * (-len(output) % 4))
        output.extend(data)
        output.extend(b'\0' * (-len(output) % 4))
    for name in ('dev', 'proc', 'sys', 'run', 'tmp', 'etc', 'bin', 'mnt', 'mnt/data'):
        entry(name, stat.S_IFDIR | (0o1777 if name == 'tmp' else 0o755))
    entry('root', stat.S_IFDIR | 0o700)
    entry('home', stat.S_IFDIR | 0o755)
    entry('home/ominx', stat.S_IFDIR | 0o700, uid=1000, gid=1000)
    entry('etc/passwd', stat.S_IFREG | 0o644,
          b'root:x:0:0:Recovery:/root:/init\nominx:x:1000:1000:OminX live user:/home/ominx:/init\n')
    entry('etc/group', stat.S_IFREG | 0o644,
          b'root:x:0:\nvideo:x:44:ominx\ninput:x:104:ominx\nrender:x:107:ominx\nominx:x:1000:\n')
    entry('etc/shadow', stat.S_IFREG | 0o600,
          b'root:!:0:0:99999:7:::\nominx:!:0:0:99999:7:::\n')
    entry('dev/console' , stat.S_IFCHR | 0o600, major=5, minor=1)
    entry('init', stat.S_IFREG | 0o755, binary)
    if files is not None:
        entry('bin/ominx-files', stat.S_IFREG | 0o755, files)
    entry('etc/os-release', stat.S_IFREG | 0o644,
          b'NAME=OminX\nID=ominx\nPRETTY_NAME="OminX source-built console"\n')
    entry('TRAILER!!!', 0)
    return gzip.compress(bytes(output), mtime=0)


def static_elf(path):
    binary = Path(path).read_bytes()
    if len(binary) < 64 or binary[:6] != b'\x7fELF\x02\x01':
        raise ValueError('Expected a complete 64-bit little-endian ELF header')
    if struct.unpack_from('<HH', binary, 16) != (2, 62):
        raise ValueError('Expected x86-64 ET_EXEC executable')
    offset = struct.unpack_from('<Q', binary, 32)[0]
    size, count = struct.unpack_from('<HH', binary, 54)
    if not count or size != 56 or offset < 64 or offset + size * count > len(binary):
        raise ValueError('Invalid ELF program header table')
    if any(struct.unpack_from('<I', binary, offset + i * size)[0] == 3 for i in range(count)):
        raise ValueError('Executable must be statically linked (PT_INTERP found)')
    return binary


if __name__ == '__main__':
    if len(sys.argv) != 4:
        raise SystemExit('Usage: make-initramfs.py INIT OUTPUT FILES_EXECUTABLE')
    try:
        packed = archive(static_elf(sys.argv[1]), static_elf(sys.argv[3]))
    except ValueError as error:
        raise SystemExit(str(error))
    Path(sys.argv[2]).write_bytes(packed)
