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


def unpack(archive, digest, destination, *, allow_internal_links=False, allow_internal_directories=False, max_unpacked=256*1024*1024):
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
    # Build a virtual source tree first. File/directory aliases are materialized
    # without creating or following any filesystem link. Prefix cycles, missing
    # targets, special files, expansion bombs and escaping links fail closed.
    directories = {''}
    for name in names:
        directories.update(str(p) if str(p) != '.' else '' for p in PurePosixPath(name).parents)
    directories.update(names - set(files) - set(links))
    for name in names:
        if any(str(parent) in files or str(parent) in links for parent in PurePosixPath(name).parents):
            raise ValueError('Source member has a non-directory ancestor')
    children = {}
    for name in set(files) | set(links) | directories - {''}:
        children.setdefault(posixpath.dirname(name), set()).add(name)
    def contents(name, seen):
        if name in seen or len(seen) >= 64:
            raise ValueError('Cyclic/deep internal source link')
        seen = seen | {name}
        if name in links:
            yield from contents(links[name], seen)
        elif name in files:
            yield '', files[name]
        elif name in directories:
            if not allow_internal_directories:
                raise ValueError('Directory source alias requires explicit opt-in: ' + name)
            for child in sorted(children.get(name, ())):
                for suffix, value in contents(child, seen):
                    yield posixpath.join(posixpath.basename(child), suffix).rstrip('/'), value
        else:
            # A target can name a file beneath another internal directory alias.
            parts = PurePosixPath(name).parts
            for index in range(1, len(parts)):
                prefix = '/'.join(parts[:index])
                if prefix in links:
                    if prefix in seen:
                        raise ValueError('Cyclic source alias prefix')
                    yield from contents(posixpath.join(links[prefix], *parts[index:]), seen | {prefix})
                    return
            raise ValueError('Missing internal source link target: ' + name)
    materialized = {}
    for name in links:
        for suffix, value in contents(name, set()):
            dest = posixpath.join(name, suffix).rstrip('/')
            if dest in files or dest in materialized:
                raise ValueError('Colliding expanded source aliases')
            total += len(value[0])
            if total > max_unpacked or len(files) + len(materialized) >= 100000:
                raise ValueError('Expanded source aliases too large')
            materialized[dest] = value
    files.update(materialized)
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
    parser.add_argument('--allow-internal-directory-links', action='store_true')
    parser.add_argument('--max-download-mib', type=int, choices=(64,128), default=64)
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
            payload = response.read(args.max_download_mib * 1024 * 1024 + 1)
            content_type = response.headers.get("Content-Type", "unknown")
        actual = hashlib.sha256(payload).hexdigest()
        if len(payload) > args.max_download_mib * 1024 * 1024 or actual != args.sha256:
            raise SystemExit(f'Invalid downloaded source archive: bytes={len(payload)}, sha256={actual}, content-type={content_type}, prefix={payload[:32].hex()}')
        cached.write_bytes(payload)
    unpack(cached, args.sha256, dest, allow_internal_links=args.allow_internal_file_links, allow_internal_directories=args.allow_internal_directory_links, max_unpacked=args.max_unpacked_mib*1024*1024)
