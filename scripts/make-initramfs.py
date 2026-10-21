#!/usr/bin/env python3
"""Deterministic Linux newc initramfs, without root privileges or host cpio."""
import argparse
import gzip
import importlib.util
import re
from pathlib import Path
import stat
import struct
import sys


def archive(binary, files=None, control=None, graphics_probe=None, quick_probe=None, bus=None, qt_bus_probe=None, qt_bus_licenses=None, runtime=None, login=None, accounts=None):
    if qt_bus_probe is not None and (bus is None or not qt_bus_licenses):
        raise ValueError("Qt bus probe requires source bus bundle and Qt license texts")
    if (login is None) != (accounts is None):
        raise ValueError("Graphical login requires both its binaries and its account records")
    output = bytearray()
    installed = {}
    def entry(name, mode, data=b'', major=0, minor=0, uid=0, gid=0):
        if name in installed:
            if stat.S_ISDIR(mode) and installed[name] == mode:
                return
            raise ValueError('Duplicate image path: ' + name)
        installed[name] = mode
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
          (b'messagebus:x:81:81:System bus:/run/dbus:/bin/false\n' if bus is not None else b'') +
          (b'greeter:x:1001:1001:Login screen:/run/ominx/greeter:/bin/false\n'
           b'guest:x:1002:1002:Locked guest:/home/guest:/bin/false\n' if login is not None else b''))
    entry('etc/group', stat.S_IFREG | 0o644,
          b'root:x:0:\ntty:x:5:\nvideo:x:44:ominx\ninput:x:104:ominx\nrender:x:107:ominx\nominx:x:1000:\n' +
          (b'messagebus:x:81:\n' if bus is not None else b'') +
          (b'greeter:x:1001:\nguest:x:1002:\n' if login is not None else b''))
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
    if login is not None:
        entry('etc/ominx', stat.S_IFDIR | 0o755)
        entry('home/guest', stat.S_IFDIR | 0o700, uid=1002, gid=1002)
        for name, path in LOGIN_PATHS.items():
            entry(path, stat.S_IFREG | 0o755, login[name])
        # Root-only credentials plus the marker that makes /init start the seat.
        entry('etc/ominx/accounts', stat.S_IFREG | 0o400, accounts)
        entry('etc/ominx/graphical-login', stat.S_IFREG | 0o444, b'1\n')
        for name in ('LICENSE', 'QTBASE-LICENSES'):
            entry('usr/share/licenses/ominx-desktop-shell/' + name, stat.S_IFREG | 0o644, login[name])
    if qt_bus_probe is not None:
        entry('bin/ominx-qt-bus-probe', stat.S_IFREG | 0o755, qt_bus_probe)
        entry('usr/share/licenses/ominx-qt-bus-LICENSES', stat.S_IFREG | 0o644, qt_bus_licenses)
    entry('etc/os-release' , stat.S_IFREG | 0o644,
          b'NAME=OminX\nID=ominx\nPRETTY_NAME="OminX source-built console"\n')
    if runtime is not None:
        spec = importlib.util.spec_from_file_location('runtime_elf', Path(__file__).with_name('runtime-elf.py'))
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        nodes, _ = module.audit(runtime)
        for name, (mode, data) in sorted(nodes.items()):
            entry(name, mode, data)
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
LOGIN_BINARIES = ('ominx-login', 'ominx-seat', 'ominx-passwd', 'ominx-desktop', 'ominx-login-probe')
LOGIN_PATHS = {'ominx-login': 'sbin/ominx-login', 'ominx-seat': 'sbin/ominx-seat',
               'ominx-passwd': 'bin/ominx-passwd', 'ominx-desktop': 'bin/ominx-desktop',
               'ominx-login-probe': 'bin/ominx-login-probe'}
LOGIN_LICENSES = ('LICENSE', 'QTBASE-LICENSES')
# Mirrors src/login/login.c so packaging cannot ship records the service rejects.
ACCOUNT_LINE = re.compile(
    r'^([a-z_][a-z0-9_-]{0,31}):([1-9][0-9]{3,4}):([1-9][0-9]{3,4}):'
    r'(/home/[a-z_][a-z0-9_-]{0,31}):/bin/ominx-desktop:([01]):'
    r'(!|\$6\$[./0-9A-Za-z]{1,16}\$[./0-9A-Za-z]{86})$')


def account_records(path):
    text = Path(path).read_bytes()
    if not 0 < len(text) <= 4096:
        raise ValueError('Account records must be 1-4096 bytes')
    lines = text.decode('ascii').splitlines()
    if not lines or text.endswith(b'\n') is False:
        raise ValueError('Account records must end with a newline')
    names = set()
    for line in lines:
        match = ACCOUNT_LINE.fullmatch(line)
        if not match:
            raise ValueError('Invalid packaged account record: ' + line.split(':')[0])
        name, uid, gid = match.group(1), int(match.group(2)), int(match.group(3))
        if name in ('root', 'greeter') or 1001 in (uid, gid) or uid != gid or uid >= 60000:
            raise ValueError('Refusing reserved identity in account record: ' + name)
        if match.group(4) != '/home/' + name or name in names:
            raise ValueError('Account home must match its unique name: ' + name)
        names.add(name)
    return text


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
    parser.add_argument('--runtime-dir', type=Path)
    parser.add_argument('--login-dir', type=Path)
    parser.add_argument('--login-accounts', type=Path)
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
        login = accounts = None
        if args.login_dir is not None or args.login_accounts is not None:
            if args.login_dir is None or args.login_accounts is None:
                raise ValueError('Graphical login needs both --login-dir and --login-accounts')
            login = {name: static_elf(args.login_dir / name) for name in LOGIN_BINARIES}
            login.update({name: (args.login_dir / name).read_bytes() for name in LOGIN_LICENSES})
            for name, data in login.items():
                if not data:
                    raise ValueError('Empty login component: ' + name)
            accounts = account_records(args.login_accounts)
        packed = archive(static_elf(args.init), static_elf(args.files), static_elf(args.control), probe, quick, bus, qt_bus, qt_licenses, args.runtime_dir, login, accounts)
    except (ValueError, OSError) as error:
        raise SystemExit(str(error))
    Path(args.output).write_bytes(packed)
