#!/usr/bin/env python3
"""Audit a source-built glibc Wine/Proton runtime tree for packaging.

The target itself is musl-based; Windows programs run from an isolated
glibc prefix at /usr/lib/ominx/wine-runtime whose dynamic linker path is
compiled into every ELF at build time (scripts/build-wine-runtime.sh).
This audit is the packaging gate: it proves, without executing anything,
that the tree is self-contained (all DT_NEEDED resolve inside the prefix),
x86-64 only, has no privileged or escaping links, and provides the fixed
layout ominx-wined expects. A distribution Wine copy or a stray host
binary fails here instead of at a user's first double-click."""
from pathlib import Path, PurePosixPath
import posixpath
import re
import stat
import struct

PREFIX = 'usr/lib/ominx/wine-runtime'
LOADER = '/usr/lib/ominx/wine-runtime/lib/ld-linux-x86-64.so.2'
MAX_TOTAL = 2 * 1024 * 1024 * 1024


def elf(data):
    def require(ok, message):
        if not ok:
            raise ValueError(message)
    require(len(data) >= 64 and data[:6] == b'\x7fELF\x02\x01', 'Invalid ELF64 header')
    kind, machine = struct.unpack_from('<HH', data, 16)
    require(kind in (2, 3) and machine == 62, 'Wine runtime must be x86-64 ELF')
    offset = struct.unpack_from('<Q', data, 32)[0]
    size, count = struct.unpack_from('<HH', data, 54)
    require(0 < count <= 4096 and size == 56 and offset >= 64 and
            offset + size * count <= len(data), 'Invalid program headers')
    loads, dynamic, interpreter = [], None, None
    for i in range(count):
        ptype, _flags, start, address, _phys, length, memory, _align = \
            struct.unpack_from('<IIQQQQQQ', data, offset + i * size)
        require(start + length <= len(data), 'Segment exceeds file')
        if ptype == 1:
            require(length <= memory, 'Invalid load segment')
            loads.append((address, start, length))
        elif ptype == 2:
            require(dynamic is None and length % 16 == 0, 'Invalid dynamic segment')
            dynamic = data[start:start + length]
        elif ptype == 3:
            require(interpreter is None, 'Duplicate interpreter')
            require(data[start:start + length].endswith(b'\0'), 'Malformed interpreter')
            interpreter = data[start:start + length - 1].decode('ascii')
    require(loads, 'No loadable segments')
    if dynamic is None:
        return {'kind': kind, 'interpreter': interpreter, 'needed': []}
    tags, terminated = {}, False
    for at in range(0, len(dynamic), 16):
        tag, value = struct.unpack_from('<qQ', dynamic, at)
        if tag == 0:
            terminated = True
            break
        tags.setdefault(tag, []).append(value)
    require(terminated, 'Unterminated dynamic table')
    require(len(tags.get(5, [])) == 1 and len(tags.get(10, [])) == 1,
            'Missing dynamic string table')
    address, length = tags[5][0], tags[10][0]
    tables = [data[s + address - b:s + address - b + length]
              for b, s, n in loads if b <= address and address + length <= b + n]
    require(len(tables) == 1 and length > 0, 'Invalid string table mapping')
    table = tables[0]

    def string(index):
        require(index < len(table), 'Invalid dynamic string index')
        end = table.find(b'\0', index)
        require(end >= 0, 'Unterminated dynamic string')
        value = table[index:end].decode('ascii')
        require(re.fullmatch(r'[A-Za-z0-9_+.-]+', value) is not None and value not in ('.', '..'),
                'Unsafe library name')
        return value
    return {'kind': kind, 'interpreter': interpreter,
            'needed': [string(i) for i in tags.get(1, [])]}


def audit(root):
    """Return {image_path: (mode, bytes)} for everything under the prefix."""
    root = Path(root)
    if root.is_symlink() or not root.is_dir():
        raise ValueError('Wine runtime root must be a real directory')
    nodes = {}
    libraries = {}
    total = 0
    for directory in ('usr', 'usr/lib', 'usr/lib/ominx'):
        nodes[directory] = (stat.S_IFDIR | 0o755, b'')
    for path in sorted(root.rglob('*')):
        relative = path.relative_to(root).as_posix()
        name = PREFIX + '/' + relative
        if any(part in ('', '.', '..') for part in PurePosixPath(relative).parts):
            raise ValueError('Unsafe runtime path: ' + relative)
        mode = path.lstat().st_mode
        if stat.S_ISDIR(mode):
            if stat.S_IMODE(mode) != 0o755:
                raise ValueError('Runtime directory must be 0755: ' + relative)
            nodes[name] = (stat.S_IFDIR | 0o755, b'')
        elif stat.S_ISREG(mode):
            if stat.S_IMODE(mode) not in (0o644, 0o755) or mode & 0o7000:
                raise ValueError('Unsafe runtime file permissions: ' + relative)
            data = path.read_bytes()
            total += len(data)
            if total > MAX_TOTAL:
                raise ValueError('Wine runtime exceeds its 2 GiB packaging budget')
            if data.startswith(b'\x7fELF'):
                info = elf(data)
                if mode & 0o111 and info['interpreter'] not in (None, LOADER):
                    raise ValueError(
                        'Foreign dynamic linker in executable ' + relative +
                        ': rebuild against the OminX prefix')
                libraries[PurePosixPath(relative).name] = (name, info)
                nodes[name] = (stat.S_IFREG | stat.S_IMODE(mode), data)
            else:
                # Windows-side PE modules are data for the loader, often
                # installed executable by Wine/DXVK. Anything else that is
                # executable but not ELF (scripts, stray host tools) fails.
                if mode & 0o111 and not data.startswith(b'MZ'):
                    raise ValueError('Executable runtime file is not ELF: ' + relative)
                nodes[name] = (stat.S_IFREG | stat.S_IMODE(mode), data)
        elif stat.S_ISLNK(mode):
            target = path.readlink().as_posix()
            if not target or target.startswith('/'):
                raise ValueError('Runtime links must be relative: ' + relative)
            resolved = posixpath.normpath(posixpath.join(posixpath.dirname(relative), target))
            if resolved.startswith('../') or resolved == '..':
                raise ValueError('Escaping runtime symlink: ' + relative)
            if not (root / resolved).exists():
                raise ValueError('Dangling runtime symlink: ' + relative)
            libraries.setdefault(PurePosixPath(relative).name,
                                 (name, libraries.get(PurePosixPath(resolved).name, (name, None))[1]))
            nodes[name] = (stat.S_IFLNK | 0o777, target.encode())
        else:
            raise ValueError('Special runtime file: ' + relative)
    for required, description in (('VERSION', 'runtime version file'),
                                  ('bin/wine', 'Wine loader'),
                                  ('lib/ld-linux-x86-64.so.2', 'glibc dynamic linker')):
        if PREFIX + '/' + required not in nodes:
            raise ValueError('Missing ' + description + ': ' + required)
    version = nodes[PREFIX + '/VERSION'][1].decode('ascii', errors='strict').strip()
    if not re.fullmatch(r'wine-[0-9A-Za-z.+~_-]+', version.splitlines()[0]):
        raise ValueError('VERSION must begin with one wine-<version> line')
    wine_mode = nodes[PREFIX + '/bin/wine'][0]
    if not wine_mode & 0o111:
        raise ValueError('bin/wine is not executable')
    unresolved = []
    for basename, (path_name, info) in libraries.items():
        if not info:
            continue
        for needed in info['needed']:
            if needed not in libraries:
                unresolved.append(f'{needed} (needed by {basename})')
    if unresolved:
        raise ValueError('Unresolved runtime dependencies: ' + ', '.join(sorted(unresolved)))
    return nodes
