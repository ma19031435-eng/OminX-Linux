#!/usr/bin/env python3
"""Deterministic Linux newc initramfs, without root privileges or host cpio."""
import gzip
from pathlib import Path
import stat
import struct
import sys


def archive(binary):
    output = bytearray()
    def entry(name, mode, data=b'', major=0, minor=0):
        encoded = name.encode() + b'\0'
        values = [1, mode, 0, 0, 1, 0, len(data), 0, 0, major, minor, len(encoded), 0]
        output.extend(b'070701' + b''.join(f'{v:08x}'.encode() for v in values))
        output.extend(encoded)
        output.extend(b'\0' * (-len(output) % 4))
        output.extend(data)
        output.extend(b'\0' * (-len(output) % 4))
    for name in ('dev', 'proc', 'sys', 'run', 'tmp', 'root', 'etc', 'bin'):
        entry(name, stat.S_IFDIR | (0o1777 if name == 'tmp' else 0o755))
    entry('dev/console', stat.S_IFCHR | 0o600, major=5, minor=1)
    entry('init', stat.S_IFREG | 0o755, binary)
    entry('etc/os-release', stat.S_IFREG | 0o644,
          b'NAME=OminX\nID=ominx\nPRETTY_NAME="OminX source-built console"\n')
    entry('TRAILER!!!', 0)
    return gzip.compress(bytes(output), mtime=0)


if __name__ == '__main__':
    binary = Path(sys.argv[1]).read_bytes()
    if binary[:4] != b'\x7fELF' or binary[4:6] != b'\x02\x01':
        raise SystemExit('Expected a 64-bit little-endian ELF executable')
    if struct.unpack_from('<H', binary, 18)[0] != 62:
        raise SystemExit('Expected x86-64 executable')
    # Reject dynamic executables: early userspace has no dynamic loader.
    offset = struct.unpack_from('<Q', binary, 32)[0]
    size, count = struct.unpack_from('<HH', binary, 54)
    if any(struct.unpack_from('<I', binary, offset + i * size)[0] == 3 for i in range(count)):
        raise SystemExit('Executable must be statically linked (PT_INTERP found)')
    Path(sys.argv[2]).write_bytes(archive(binary))
