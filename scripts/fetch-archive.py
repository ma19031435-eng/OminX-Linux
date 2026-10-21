#!/usr/bin/env python3
"""Verified upstream source archives, restricted extraction, checked reuse."""
import argparse
import hashlib
from pathlib import Path, PurePosixPath
import re
import posixpath
import shutil
import tarfile
import tempfile
import urllib.request

ROOT = Path(__file__).resolve().parents[1]


def unpack(archive, digest, destination, *, allow_internal_links=False, max_unpacked=256*1024*1024):
    if not 1 <= max_unpacked <= 512*1024*1024:
        raise ValueError("Invalid source expansion limit")
    archive, destination = Path(archive), Path(destination)
    if not re.fullmatch('[0-9a-f]{64}', digest):
        raise ValueError('Expected SHA256 digest')
    if hashlib.sha256(archive.read_bytes()).hexdigest() != digest:
        raise ValueError('Source archive SHA256 mismatch')
    files, roots, total, names, links = {}, set(), 0, set(), {}
    with tarfile.open(archive) as source:
        for member in source:
            path = PurePosixPath(member.name)
            if path.is_absolute() or '..' in path.parts or not path.parts:
                raise ValueError('Unsafe source path')
            roots.add(path.parts[0])
            if not (member.isfile() or member.isdir() or (allow_internal_links and (member.issym() or member.islnk()))):
                raise ValueError('Source links and special files are not permitted: ' + member.name)
            if len(path.parts) == 1:
                if not member.isdir():
                    raise ValueError('Expected one enclosing source directory')
                continue
            name = str(PurePosixPath(*path.parts[1:]))
            if name in names:
                raise ValueError('Duplicate source member')
            names.add(name)
            total += member.size
            if total > max_unpacked or len(names) > 100000:
                raise ValueError('Source archive too large')
            if member.issym() or member.islnk():
                if not member.linkname or member.linkname.startswith('/'):
                    raise ValueError('Invalid internal source link')
                target = posixpath.normpath(posixpath.join(str(path.parent), member.linkname) if member.issym() else member.linkname)
                if not target.startswith(path.parts[0] + '/'):
                    raise ValueError('Escaping internal source link')
                links[name] = target.split('/', 1)[1]
            if member.isfile():
                files[name] = (source.extractfile(member).read(), 0o755 if member.mode & 0o111 else 0o644)
    # Materialize bounded internal *file* aliases as regular files. No filesystem
    # symlink is ever extracted or followed; directory links and cycles fail closed.
    for name in links:
        target, seen = name, set()
        while target in links:
            if target in seen or len(seen) >= 64:
                raise ValueError('Cyclic/deep internal source link')
            seen.add(target)
            target = links[target]
        if target not in files:
            raise ValueError('Missing/non-file internal source link target')
        total += len(files[target][0])
        if total > max_unpacked:
            raise ValueError('Expanded source aliases too large')
        files[name] = files[target]
    if len(roots) != 1 or not files:
        raise ValueError('Expected one nonempty source tree')
    if destination.exists() or destination.is_symlink():
        if destination.is_symlink() or not destination.is_dir():
            raise ValueError('Invalid source destination')
        actual = set()
        for path in destination.rglob('*'):
            if path.is_symlink() or not (path.is_file() or path.is_dir()):
                raise ValueError('Modified source tree contains a link/special file')
            if path.is_file():
                name = path.relative_to(destination).as_posix()
                actual.add(name)
                if name not in files or (path.read_bytes(), path.stat().st_mode & 0o7777) != files[name]:
                    raise ValueError('Modified source tree: ' + name)
        if actual != set(files):
            raise ValueError('Incomplete source tree')
        return
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix='.source-', dir=destination.parent))
    try:
        for name, (data, mode) in files.items():
            path = temporary / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
            path.chmod(mode)
        temporary.rename(destination)
    finally:
        if temporary.exists():
            shutil.rmtree(temporary)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('url')
    parser.add_argument('sha256')
    parser.add_argument('destination', type=Path)
    parser.add_argument('--allow-internal-file-links', action='store_true')
    parser.add_argument('--max-unpacked-mib', type=int, choices=(256,512), default=256)
    args = parser.parse_args()
    build = ROOT / 'build'
    dest = args.destination.absolute()
    if not dest.resolve().is_relative_to(build.resolve()) or dest.resolve() == build.resolve():
        raise SystemExit('Source destination must be inside the disposable build directory')
    if not args.url.startswith('https://') or not re.fullmatch('[0-9a-f]{64}', args.sha256):
        raise SystemExit('An HTTPS URL and SHA256 are required')
    downloads = build / 'downloads'
    downloads.mkdir(parents=True, exist_ok=True)
    cached = downloads / (args.sha256 + '.tar')
    if not cached.exists():
        with urllib.request.urlopen(args.url, timeout=60) as response:
            payload = response.read(64 * 1024 * 1024 + 1)
        if len(payload) > 64 * 1024 * 1024 or hashlib.sha256(payload).hexdigest() != args.sha256:
            raise SystemExit('Invalid downloaded source archive')
        cached.write_bytes(payload)
    unpack(cached, args.sha256, dest, allow_internal_links=args.allow_internal_file_links, max_unpacked=args.max_unpacked_mib*1024*1024)
