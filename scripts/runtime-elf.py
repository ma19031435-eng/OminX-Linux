#!/usr/bin/env python3
"""Non-executing x86-64 musl runtime audit. Never invoke ldd on build inputs."""
from pathlib import Path, PurePosixPath
import posixpath
import re
import stat
import struct

LOADER = '/lib/ld-musl-x86_64.so.1'


def elf(data):
    def require(ok, message):
        if not ok:
            raise ValueError(message)
    require(len(data) >= 64 and data[:7] == b'\x7fELF\x02\x01\x01', 'Invalid ELF64 header')
    kind, machine = struct.unpack_from('<HH', data, 16)
    require(kind in (2, 3) and machine == 62, 'Runtime must be x86-64 executable/shared ELF')
    offset = struct.unpack_from('<Q', data, 32)[0]
    size, count = struct.unpack_from('<HH', data, 54)
    require(0 < count <= 4096 and size == 56 and offset >= 64 and offset + size * count <= len(data), 'Invalid program headers')
    loads, dynamic, interpreter = [], None, None
    for i in range(count):
        ptype, flags, start, address, physical, length, memory, align = struct.unpack_from('<IIQQQQQQ', data, offset+i*size)
        require(start + length <= len(data), 'Segment exceeds file')
        if ptype == 1:
            require(length <= memory, 'Invalid load segment')
            loads.append((address, start, length))
        elif ptype == 2:
            require(dynamic is None and length % 16 == 0, 'Invalid dynamic segment')
            dynamic = data[start:start+length]
        elif ptype == 3:
            require(interpreter is None and data[start:start+length] == LOADER.encode()+b'\0', 'Foreign or malformed ELF interpreter')
            interpreter = LOADER
    require(loads, 'No loadable segments')
    if dynamic is None:
        require(interpreter is None, 'Interpreter without dynamic section')
        return {'kind': kind, 'interpreter': None, 'needed': [], 'soname': None}
    tags, terminated = {}, False
    for offset in range(0, len(dynamic), 16):
        tag, value = struct.unpack_from('<qQ', dynamic, offset)
        if tag == 0:
            terminated = True
            break
        tags.setdefault(tag, []).append(value)
    require(terminated, 'Unterminated dynamic table')
    require(not (15 in tags or 29 in tags), 'Runtime RPATH/RUNPATH is forbidden')
    require(not (22 in tags or any(v & 4 for v in tags.get(30, []))), 'Runtime text relocations are forbidden')
    require(len(tags.get(5, [])) == 1 and len(tags.get(10, [])) == 1, 'Missing/duplicate dynamic string table')
    address, length = tags[5][0], tags[10][0]
    tables = [data[start+address-base:start+address-base+length] for base,start,n in loads
              if base <= address and address+length <= base+n]
    require(len(tables) == 1 and length > 0, 'Invalid dynamic string table mapping')
    table = tables[0]
    require(b'GLIBC_' not in table, 'glibc symbol versions in musl runtime')
    def string(index):
        require(index < len(table), 'Invalid dynamic string index')
        end = table.find(b'\0', index)
        require(end >= 0, 'Unterminated dynamic string')
        value = table[index:end].decode('ascii', errors='strict')
        require(re.fullmatch(r'[A-Za-z0-9_+.-]+', value) is not None and value not in ('.', '..'), 'Unsafe library name')
        return value
    needed = [string(i) for i in tags.get(1, [])]
    require(len(tags.get(14, [])) <= 1, 'Duplicate SONAME')
    return {'kind': kind, 'interpreter': interpreter, 'needed': needed,
            'soname': string(tags[14][0]) if 14 in tags else None}


def audit(root):
    root = Path(root)
    if root.is_symlink() or not root.is_dir():
        raise ValueError('Runtime root must be a real directory')
    nodes, binaries = {}, {}
    allowed = ('lib/', 'usr/lib/', 'usr/bin/', 'usr/share/')
    parents = {'lib', 'usr', 'usr/lib', 'usr/bin', 'usr/share'}
    for path in sorted(root.rglob('*')):
        name = path.relative_to(root).as_posix()
        mode = path.lstat().st_mode
        if name in parents and not stat.S_ISDIR(mode):
            raise ValueError('Runtime container must be a directory')
        if not (name in parents or name.startswith(allowed)):
            raise ValueError('Disallowed runtime path: ' + name)
        if any(part in ('', '.', '..') for part in PurePosixPath(name).parts):
            raise ValueError('Unsafe runtime path')
        if stat.S_ISDIR(mode):
            if stat.S_IMODE(mode) != 0o755:
                raise ValueError('Runtime directory must be 0755: ' + name)
            nodes[name] = (stat.S_IFDIR | 0o755, b'')
        elif stat.S_ISREG(mode):
            if stat.S_IMODE(mode) not in (0o644, 0o755):
                raise ValueError('Unsafe runtime file permissions: ' + name)
            data = path.read_bytes()
            if data.startswith(b'\x7fELF'):
                binaries[name] = elf(data)
            elif mode & 0o111:
                raise ValueError('Executable runtime file is not ELF: ' + name)
            nodes[name] = (stat.S_IFREG | stat.S_IMODE(mode), data)
        elif stat.S_ISLNK(mode):
            target = path.readlink().as_posix()
            if not target or target.startswith('/'):
                raise ValueError('Runtime links must be relative')
            nodes[name] = (stat.S_IFLNK | 0o777, target.encode())
        else:
            raise ValueError('Special runtime file: ' + name)
    def resolve(name):
        seen = set()
        while name in nodes and stat.S_ISLNK(nodes[name][0]):
            if name in seen:
                raise ValueError('Runtime symlink cycle')
            seen.add(name)
            name = posixpath.normpath(posixpath.join(posixpath.dirname(name), nodes[name][1].decode()))
            if name.startswith('../') or name == '..':
                raise ValueError('Escaping runtime symlink')
        if name not in nodes or not stat.S_ISREG(nodes[name][0]):
            raise ValueError('Runtime symlink/dependency missing or not a file: ' + name)
        return name
    for name, (mode, _) in nodes.items():
        if stat.S_ISLNK(mode):
            resolve(name)
    for name, info in binaries.items():
        if info['interpreter']:
            loader = resolve(LOADER[1:])
            if loader not in binaries or not nodes[loader][0] & 0o111:
                raise ValueError('Missing executable musl loader')
        for needed in info['needed']:
            choices = [directory+needed for directory in ('lib/', 'usr/lib/') if directory+needed in nodes]
            if not choices:
                raise ValueError(f'Unresolved dependency {needed} of {name}')
            targets = [resolve(p) for p in choices]
            if any(p not in binaries or binaries[p]['kind'] != 3 for p in targets):
                raise ValueError('Dependency is not ELF: ' + needed)
            if len({nodes[p][1] for p in targets}) > 1:
                raise ValueError('Conflicting library resolutions: ' + needed)
    if not binaries:
        raise ValueError('Empty runtime library bundle')
    return nodes, binaries
