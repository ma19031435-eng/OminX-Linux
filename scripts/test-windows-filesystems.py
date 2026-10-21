#!/usr/bin/env python3
"""Read-only Windows filesystem interoperability on exclusive disposable images."""
import hashlib
import json
from pathlib import Path
import subprocess
import importlib.util
spec = importlib.util.spec_from_file_location('platforms', Path(__file__).with_name('test-platforms.py'))
platforms = importlib.util.module_from_spec(spec)
spec.loader.exec_module(platforms)
VM, OUT, ROOT = platforms.VM, platforms.OUT, platforms.ROOT


def run(*args):
    result = subprocess.run(list(map(str, args)), capture_output=True)
    if result.returncode:
        raise RuntimeError(f'{args}: {result.stdout.decode(errors="replace")} {result.stderr.decode(errors="replace")}')


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def check_format(kind):
    data = OUT / (kind + '-primary.raw')
    disk = OUT / (kind + '-fixture.raw')
    for path in (data, disk):
        with path.open('xb') as stream:
            stream.truncate(64 * 1024 * 1024)
    run('mkfs.ext4', '-q', '-F', data)
    seed = OUT / (kind + '-seed.txt')
    seed.write_bytes(b'OMINX_WINDOWS_FILE_READ\r\n')
    if kind == 'vfat':
        run('mkfs.vfat', '-F', '32', disk)
        run('mcopy', '-i', disk, seed, '::/Windows Notes.txt')
    elif kind == 'ntfs3':
        run('mkntfs', '-F', '-Q', disk)
        run('ntfscp', '-f', disk, seed, '/Windows Notes.txt')
    else:
        run('mkfs.exfat', disk)
        # Seed using our source-built guest kernel, not privileged host mounts.
        fixture = OUT / 'seed-exfat'
        run(ROOT / 'build/toolchain/bin/x86_64-linux-musl-gcc', '-static', '-O2',
            '-Wall', '-Wextra', '-Werror', ROOT / 'tests/fixtures/seed-exfat.c', '-o', fixture)
        pack_spec = importlib.util.spec_from_file_location('packer', Path(__file__).with_name('make-initramfs.py'))
        packer = importlib.util.module_from_spec(pack_spec)
        pack_spec.loader.exec_module(packer)
        ramdisk = OUT / 'seed-exfat.cpio.gz'
        ramdisk.write_bytes(packer.archive(packer.static_elf(fixture)))
        result = subprocess.run(['qemu-system-x86_64', '-m', '256', '-kernel', str(ROOT / 'build/bzImage'),
                                 '-initrd', str(ramdisk), '-append', 'console=ttyS0 rdinit=/init panic=-1',
                                 '-nographic', '-no-reboot', '-nic', 'none',
                                 '-drive', f'if=virtio,format=raw,file={disk}'],
                                capture_output=True, timeout=90)
        log = result.stdout + result.stderr
        (OUT / 'exfat-fixture.txt').write_bytes(log)
        if result.returncode or b'OMINX_FIXTURE_READY' not in log or b'Power down' not in log:
            raise RuntimeError('Guest exFAT fixture preparation failed: ' + log[-4000:].decode(errors='replace'))
    before = digest(disk)
    case = dict(recovery=True, name='windows-' + kind, machine='q35', ram=512, cpu='qemu64', disk='virtio', uefi=True)
    vm = VM(case, data, 'readonly', extras=[disk])
    try:
        vm.expect('OminX console ready.')
        vm.prompt()
        vm.command(f'attach /dev/vdb ro {kind}', 'Data attached')
        vm.command('files list /mnt/data', 'Windows Notes.txt')
        vm.command('cat "/mnt/data/Windows Notes.txt"', 'OMINX_WINDOWS_FILE_READ')
        vm.command('files copy "/mnt/data/Windows Notes.txt" "/root/imported notes.txt"', '{"ok":true}')
        vm.command('cat "/root/imported notes.txt"', 'OMINX_WINDOWS_FILE_READ')
        vm.command('write /mnt/data/forbidden blocked', 'Read-only file system')
        vm.command('files remove --confirm "/mnt/data/Windows Notes.txt"', 'Read-only file system')
        vm.command('detach', 'Data detached')
        vm.shutdown()
    finally:
        vm.close()
    if digest(disk) != before:
        raise RuntimeError(f'{kind}: supposedly read-only image was modified')
    data.unlink()
    disk.unlink()


if __name__ == '__main__':
    results = []
    try:
        for kind in ('vfat', 'exfat', 'ntfs3'):
            try:
                check_format(kind)
            except Exception as error:
                results.append(dict(filesystem=kind, result='FAIL', error=str(error)))
                raise
            results.append(dict(filesystem=kind, result='PASS'))
            print(f'PASS {kind}: list/read/import spaced filename, write/delete refusal, unchanged image SHA256', flush=True)
    finally:
        (OUT / 'windows-filesystems.json').write_text(json.dumps(results, indent=2) + '\n')
