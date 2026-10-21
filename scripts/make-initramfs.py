#!/usr/bin/env python3
"""Deterministic Linux newc initramfs, without root privileges or host cpio."""
import argparse
import gzip
from pathlib import Path
import stat
import struct
import sys


def archive(binary, files=None, control=None, graphics_probe=None, quick_probe=None, bus=None, qt_bus_probe=None, qt_bus_licenses=None):
    if qt_bus_probe is not None and (bus is None or not qt_bus_licenses):
        raise ValueError("Qt bus probe requires source bus bundle and Qt license texts")
    output = bytearray()
    def entry(name, mode, data=b'', major=0, minor=0, uid=0, gid=0):
        encoded = name.encode() + b'\0'
        values = [1, mode, uid, gid, 1, 0, len(data), 0, 0, major, minor, len(encoded), 0]
        output.extend(b'070701' + b''.join(f'{v:08x}'.encode() for v in values))
        output.extend(encoded)
        output.extend(b'\0' * (-len(output) % 4))
        output.extend(data)
        output.extend(b'\0' * (-len(output) % 4))
    for name in ('dev', 'proc', 'sys', 'run', 'tmp', 'etc', 'bin', 'sbin', 'mnt', 'mnt/data'):
        entry(name, stat.S_IFDIR | (0o1777 if name == 'tmp' else 0o755))
    entry('root', stat.S_IFDIR | 0o700)
    entry('home', stat.S_IFDIR | 0o755)
    entry('home/ominx', stat.S_IFDIR | 0o700, uid=1000, gid=1000)
    entry('etc/passwd', stat.S_IFREG | 0o644,
          b'root:x:0:0:Recovery:/root:/init\nominx:x:1000:1000:OminX live user:/home/ominx:/init\n' +
          (b'messagebus:x:81:81:System bus:/run/dbus:/bin/false\n' if bus is not None else b''))
    entry('etc/group', stat.S_IFREG | 0o644,
          b'root:x:0:\ntty:x:5:\nvideo:x:44:ominx\ninput:x:104:ominx\nrender:x:107:ominx\nominx:x:1000:\n' +
          (b'messagebus:x:81:\n' if bus is not None else b''))
    entry('etc/shadow', stat.S_IFREG | 0o600,
          b'root:!:0:0:99999:7:::\nominx:!:0:0:99999:7:::\n' +
          (b'messagebus:!:0:0:99999:7:::\n' if bus is not None else b''))
    entry('dev/console' , stat.S_IFCHR | 0o600, major=5, minor=1)
    entry('init', stat.S_IFREG | 0o755, binary)
    if files is not None:
        entry('bin/ominx-files', stat.S_IFREG | 0o755, files)
    if control is not None:
        entry('sbin/ominx-control', stat.S_IFREG | 0o755, control)
    if graphics_probe is not None:
        entry('bin/ominx-graphics-probe', stat.S_IFREG | 0o755, graphics_probe)
    if quick_probe is not None:
        entry('bin/ominx-quick-probe', stat.S_IFREG | 0o755, quick_probe)
    if bus is not None:
        for name in ('etc/dbus-1', 'var', 'var/lib', 'var/lib/dbus', 'usr', 'usr/share',
                     'usr/share/licenses', 'usr/share/licenses/ominx-desktop-bus'):
            entry(name, stat.S_IFDIR | 0o755)
        for name in ('dbus-daemon', 'ominx-desktop-bus'):
            entry('sbin/' + name, stat.S_IFREG | 0o755, bus[name])
        entry('bin/ominx-bus-probe', stat.S_IFREG | 0o755, bus['ominx-bus-probe'])
        for name in ('system', 'session'):
            policy = Path(__file__).resolve().parents[1] / 'desktop/bus' / (name + '.conf')
            entry('etc/dbus-1/ominx-' + name + '.conf', stat.S_IFREG | 0o644, policy.read_bytes())
        entry('var/lib/dbus/machine-id', stat.S_IFLNK | 0o777, b'/etc/machine-id')
        for name in BUS_LICENSES:
            entry('usr/share/licenses/ominx-desktop-bus/' + name, stat.S_IFREG | 0o644, bus[name])
    if qt_bus_probe is not None:
        entry('bin/ominx-qt-bus-probe', stat.S_IFREG | 0o755, qt_bus_probe)
        entry('usr/share/licenses/ominx-qt-bus-LICENSES', stat.S_IFREG | 0o644, qt_bus_licenses)
    entry('etc/os-release' , stat.S_IFREG | 0o644,
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


BUS_LICENSES = ('DBUS-LICENSES', 'DBUS-COPYING', 'DBUS-AFL-2.1.txt', 'DBUS-GPL-2.0-or-later.txt', 'EXPAT-COPYING')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('init')
    parser.add_argument('output')
    parser.add_argument('files')
    parser.add_argument('control')
    parser.add_argument('graphics_probe', nargs='?')
    parser.add_argument('quick_probe', nargs='?')
    parser.add_argument('--bus-dir', type=Path)
    parser.add_argument('--qt-bus-probe', type=Path)
    args = parser.parse_args()
    try:
        probe = static_elf(args.graphics_probe) if args.graphics_probe else None
        quick = static_elf(args.quick_probe) if args.quick_probe else None
        bus = None
        if args.bus_dir is not None:
            bus = {name: static_elf(args.bus_dir / name) for name in
                   ('dbus-daemon', 'ominx-desktop-bus', 'ominx-bus-probe')}
            bus.update({name: (args.bus_dir / name).read_bytes() for name in BUS_LICENSES})
        qt_bus = static_elf(args.qt_bus_probe) if args.qt_bus_probe else None
        qt_licenses = (args.qt_bus_probe.parent / 'QTBASE-LICENSES').read_bytes() if args.qt_bus_probe else None
        packed = archive(static_elf(args.init), static_elf(args.files), static_elf(args.control), probe, quick, bus, qt_bus, qt_licenses)
    except (ValueError, OSError) as error:
        raise SystemExit(str(error))
    Path(args.output).write_bytes(packed)
