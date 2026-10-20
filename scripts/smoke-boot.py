#!/usr/bin/env python3
"""Real QEMU serial boot acceptance; no display or KVM required."""
import os
from pathlib import Path
import selectors
import subprocess
import time

command = ['qemu-system-x86_64', '-m', '256', '-kernel', 'build/bzImage',
           '-initrd', 'build/initramfs.cpio.gz', '-append',
           'console=ttyS0 rdinit=/init panic=-1', '-nographic', '-no-reboot', '-nic', 'none']
process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                           stderr=subprocess.STDOUT)
log = bytearray()
selector = selectors.DefaultSelector()
selector.register(process.stdout, selectors.EVENT_READ)
# Test file operations and console restart, then orderly shutdown.
stages = [(b'OminX console ready.', b'write /root/probe OMINX_BOOT_OK\ncat /root/probe\nexit\n'),
          (b'OminX console ready.', b'poweroff\n')]
stage = 0
cursor = 0
try:
    deadline = time.monotonic() + 120
    while time.monotonic() < deadline:
        for key, _ in selector.select(1):
            chunk = os.read(key.fileobj.fileno(), 65536)
            if not chunk:
                selector.unregister(key.fileobj)
                continue
            log.extend(chunk)
        if stage < len(stages) and stages[stage][0] in log[cursor:]:
            cursor = len(log)
            process.stdin.write(stages[stage][1])
            process.stdin.flush()
            stage += 1
        if process.poll() is not None:
            break
    else:
        raise RuntimeError('Boot test timed out')
    if process.returncode != 0 or stage != 2 or b'\r\nOMINX_BOOT_OK\r\n' not in log:
        raise RuntimeError('Boot, file round-trip, console restart or shutdown failed')
    if b'Kernel panic' in log:
        raise RuntimeError('Kernel panic')
    print('PASS: kernel boot, original init, file round-trip, console restart, poweroff')
finally:
    if process.poll() is None:
        process.kill()
    process.wait()
    selector.close()
    Path('build/boot.log').write_bytes(log)
    print(log.decode(errors='replace'))
