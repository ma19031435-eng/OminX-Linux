#!/usr/bin/env python3
"""Real QEMU serial boot acceptance; no display or KVM required."""
import os
from pathlib import Path
import selectors
import subprocess
import time

command = ['qemu-system-x86_64', '-m', '256', '-kernel', 'build/bzImage',
           '-initrd', 'build/initramfs.cpio.gz', '-append',
           'console=ttyS0 rdinit=/init panic=-1 ominx.recovery=1', '-nographic', '-no-reboot', '-nic', 'none']
process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                           stderr=subprocess.STDOUT)
log = bytearray()
selector = selectors.DefaultSelector()
selector.register(process.stdout, selectors.EVENT_READ)
cursor = 0
deadline = time.monotonic() + 120


def receive():
    for key, _ in selector.select(1):
        chunk = os.read(key.fileobj.fileno(), 65536)
        if chunk:
            log.extend(chunk)
        else:
            selector.unregister(key.fileobj)


def expect(marker):
    global cursor
    while True:
        found = log.find(marker, cursor)
        if found >= 0:
            cursor = found + len(marker)
            return
        if time.monotonic() >= deadline:
            raise RuntimeError(f'Timed out waiting for {marker!r}')
        if not selector.get_map():
            raise RuntimeError(f'Emulator closed before {marker!r}')
        receive()


def send(command):
    process.stdin.write(command + b'\n')
    process.stdin.flush()


try:
    expect(b'OminX console ready.')
    expect(b'ominx:/root# ')
    send(b'uname')
    expect(b'Linux ')
    expect(b'ominx:/root# ')
    send(b'write /root/probe OMINX_BOOT_OK')
    expect(b'ominx:/root# ')
    send(b'cat /root/probe')
    # Require actual file contents on their own line, not echoed input.
    expect(b'\r\nOMINX_BOOT_OK\r\n')
    expect(b'ominx:/root# ')
    send(b'exit')
    expect(b'OminX console ready.')
    expect(b'ominx:/root# ')
    send(b'cat /root/probe')
    expect(b'\r\nOMINX_BOOT_OK\r\n')
    expect(b'ominx:/root# ')
    send(b'poweroff')
    expect(b'Power down')
    process.wait(timeout=max(1, deadline - time.monotonic()))
    while selector.get_map():
        receive()
    if process.returncode != 0 or b'Kernel panic' in log:
        raise RuntimeError('Abnormal emulator exit or kernel panic')
    proof = 'PASS: kernel boot, original init, uname, file round-trip, console restart, poweroff'
    log.extend(('\n' + proof + '\n').encode())
finally:
    if process.poll() is None:
        process.kill()
    process.wait()
    selector.close()
    Path('build/boot.log').write_bytes(log)
    print(log.decode(errors='replace'))
