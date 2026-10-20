#!/usr/bin/env python3
"""Boot the default (not recovery) ISO and verify real guest permission boundaries."""
import importlib.util
import json
from pathlib import Path
import subprocess

spec = importlib.util.spec_from_file_location('platforms', Path(__file__).with_name('test-platforms.py'))
platforms = importlib.util.module_from_spec(spec)
spec.loader.exec_module(platforms)
VM, OUT = platforms.VM, platforms.OUT


def check(case):
    case = dict(case, recovery=False, name='session-' + case['name'])
    disk = OUT / (case['name'] + '.raw')
    with disk.open('xb') as stream:
        stream.truncate(64 * 1024 * 1024)
    subprocess.run(['mkfs.ext4', '-q', '-F', str(disk)], check=True)
    vm = VM(case, disk, 'user')
    try:
        vm.expect('unprivileged user ominx')
        vm.expect('OminX console ready.')
        vm.prompt()
        vm.send('id')
        vm.expect('uid=1000 euid=1000 suid=1000 gid=1000 egid=1000 sgid=1000 no_new_privs=1')
        vm.expect('groups=44,104,107')
        vm.expect('HOME=/home/ominx XDG_RUNTIME_DIR=/run/user/1000')
        vm.prompt()
        vm.send('cat /proc/self/status')
        vm.expect('CapPrm:\t0000000000000000')
        vm.expect('CapEff:\t0000000000000000')
        vm.expect('CapAmb:\t0000000000000000')
        vm.expect('NoNewPrivs:\t1')
        vm.prompt()
        vm.command('files info /run/user/1000', '"mode":448,"uid":1000,"gid":1000')
        vm.command('files info /home/ominx', '"mode":448,"uid":1000,"gid":1000')
        vm.command('write "my notes.txt" "unprivileged document"')
        vm.command('files copy "my notes.txt" "copy.txt"', '{"ok":true}')
        vm.command('files info copy.txt', '"mode":384,"uid":1000,"gid":1000')
        vm.command('cat copy.txt', '\r\nunprivileged document\r\n')
        vm.command('write /etc/forbidden denied', 'Permission denied')
        vm.command('cat /etc/shadow', 'Permission denied')
        vm.command('ls /root', 'Permission denied')
        vm.command(f'cat {vm.device}', 'Permission denied')
        vm.command(f'attach {vm.device}', 'Recovery mode required')
        vm.command('detach', 'Recovery mode required')
        vm.command('poweroff', 'Recovery mode required')
        vm.command('reboot', 'Recovery mode required')
        vm.command('files info /dev/dri/card0', '"mode":432,"uid":0,"gid":44')
        vm.command('files info /dev/input/event0', '"mode":432,"uid":0,"gid":104')
        vm.keyboard_check()
        # Check drop survives an exec into a fresh shell and console replacement.
        vm.send('/init --shell')
        vm.expect('OminX console ready.')
        vm.prompt()
        vm.command('id', 'uid=1000 euid=1000 suid=1000')
        vm.send('exit')
        vm.prompt()
        vm.send('exit')
        vm.expect('unprivileged user ominx')
        vm.expect('OminX console ready.')
        vm.prompt()
        vm.command('id', 'uid=1000 euid=1000 suid=1000')
        vm.command('cat "my notes.txt"', '\r\nunprivileged document\r\n')
        # Shutdown is deliberately not delegated to a live user yet; stop through
        # the external VM manager, not a hidden in-guest root escape.
        vm.qmp_command('quit')
        vm.process.wait(timeout=10)
        if vm.process.returncode or b'Kernel panic' in vm.log:
            raise RuntimeError('Abnormal session guest exit')
    finally:
        vm.close()
    disk.unlink()


if __name__ == '__main__':
    results = []
    try:
        for case in platforms.CASES:
            try:
                check(case)
            except Exception as error:
                results.append(dict(name=case['name'], result='FAIL', error=str(error)))
                raise
            results.append(dict(name=case['name'], result='PASS'))
            print(f"PASS {case['name']}: default user, UID/GID/capabilities, runtime, device policy, "
                  'protected files/disks, file operations, keyboard, exec and respawn', flush=True)
    finally:
        (OUT / 'sessions.json').write_text(json.dumps(results, indent=2) + '\n')
