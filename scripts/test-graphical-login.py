#!/usr/bin/env python3
"""Boot the packaged media and use the real graphical login end to end.

Verifies: themed greeter rendering, a rejected password, broker authorization for
the greeter identity only, an accepted password starting a real user session,
logout returning to the greeter, and power actions through the fixed services.
"""
import importlib.util
import json
from pathlib import Path
import subprocess
import time

spec = importlib.util.spec_from_file_location('platforms', Path(__file__).with_name('test-platforms.py'))
platforms = importlib.util.module_from_spec(spec)
spec.loader.exec_module(platforms)
VM, OUT = platforms.VM, platforms.OUT
PASSWORD = (Path(__file__).resolve().parents[1] / 'desktop/desktop-shell/demo-password').read_text().strip()
KEYS = {'\n': 'ret', ' ': 'spc', '-': 'minus'}
results = []


def type_text(vm, text, hold=90, pause=0.14):
    for char in text:
        vm.qmp_command('send-key', {'keys': [{'type': 'qcode', 'data': KEYS.get(char, char)}], 'hold-time': hold})
        time.sleep(pause)


def press(vm, *qcodes, hold=90):
    vm.qmp_command('send-key', {'keys': [{'type': 'qcode', 'data': code} for code in qcodes], 'hold-time': hold})
    time.sleep(0.3)


def read_file(vm, path):
    start = len(vm.log)
    vm.send('cat ' + path)
    vm.prompt()
    return bytes(vm.log[start:]).decode('utf-8', 'replace')


def wait_for(vm, path, marker, attempts=60, pause=3):
    for _ in range(attempts):
        if marker in read_file(vm, path):
            return
        time.sleep(pause)
    raise AssertionError(f'{marker!r} never appeared in {path}')


def wait_for_count(vm, path, marker, minimum, attempts=60, pause=3):
    for _ in range(attempts):
        if read_file(vm, path).count(marker) >= minimum:
            return
        time.sleep(pause)
    raise AssertionError(f'{marker!r} appeared fewer than {minimum} times in {path}')


def colors(vm, name, wanted):
    vm.qmp_command('screendump', {'filename': str(OUT / (vm.name + '-' + name + '.ppm'))})
    image = (OUT / (vm.name + '-' + name + '.ppm')).read_bytes()
    assert image.startswith(b'P6\n'), 'Expected a QEMU RGB framebuffer dump'
    pixels = image.split(b'\n', 3)[3]
    return {color: sum(pixels[i:i + 3] == bytes.fromhex(color) for i in range(0, len(pixels), 3))
            for color in wanted}


cases = [
    dict(name='login-bios', machine='q35', ram=1024, cpu='qemu64', disk='virtio', vga='std'),
    dict(name='login-uefi', machine='q35', ram=1024, cpu='qemu64', disk='virtio', vga='virtio', uefi=True),
]
try:
    for case in cases:
        disk = OUT / (case['name'] + '.raw')
        with disk.open('xb') as stream:
            stream.truncate(64 * 1024 * 1024)
        subprocess.run(['mkfs.ext4', '-q', '-F', str(disk)], check=True)
        vm = VM(case, disk, 'login')
        # A full login, logout and power cycle legitimately exceeds the default window.
        vm.deadline = time.monotonic() + 1500
        try:
            vm.expect('OminX console ready.')
            vm.prompt()
            vm.command('id', 'uid=1000 euid=1000 suid=1000')
            wait_for(vm, '/run/ominx/seat.log', 'greeter started pid=')
            wait_for(vm, '/run/ominx/greeter.log', 'OMINX_GREETER_READY')
            counts = colors(vm, 'greeter', ('74e0c7', '0b1520'))
            assert counts['74e0c7'] > 2000, 'themed greeter accent not rendered: %r' % counts
            assert counts['0b1520'] == 0, 'session taskbar visible before login: %r' % counts
            # The remembered username is prefilled, so focus starts on the
            # password field exactly as it does for a returning user.
            type_text(vm, 'wrong-password\n')
            wait_for(vm, '/run/ominx/greeter.log', 'OMINX_LOGIN_DENIED user=ominx reason=credentials')
            wait_for(vm, '/run/ominx/login-service.log', 'login: denied name=ominx reason=credentials')
            assert 'session started' not in read_file(vm, '/run/ominx/seat.log'), 'session started after refusal'
            # The ordinary console identity may not use the login service at all.
            vm.command('write /home/ominx/credential %s' % PASSWORD)
            vm.command('/bin/ominx-login-probe AUTH ominx --password-file /home/ominx/credential', 'DENY')
            vm.command('/bin/ominx-login-probe SESSION', 'DENY')
            vm.command('/bin/ominx-login-probe LIST', 'DENY')
            # The correct password starts the real user session.
            type_text(vm, PASSWORD + '\n')
            wait_for(vm, '/run/ominx/seat.log', 'session started uid=1000')
            wait_for(vm, '/run/ominx/session.log', 'OMINX_SESSION_READY user=ominx home=/home/ominx')
            session_colors = colors(vm, 'session', ('0b1520', '74e0c7'))
            assert session_colors['0b1520'] > 20000, 'desktop taskbar not rendered: %r' % session_colors
            assert session_colors['74e0c7'] < 500, 'greeter still drawn over the session: %r' % session_colors
            # Log out through the shell: Esc opens the start menu, whose focus
            # starts on Log out, so Enter is the deliberate logout action.
            press(vm, 'esc')
            press(vm, 'ret')
            wait_for(vm, '/run/ominx/seat.log', 'session ended uid=1000')
            wait_for(vm, '/run/ominx/session.log', 'OMINX_SESSION_LOGOUT')
            wait_for_count(vm, '/run/ominx/greeter.log', 'OMINX_GREETER_READY', 2)
            # Power off from the login screen goes through the fixed services.
            # The seat logs to /run/ominx/seat.log, so the observable result of
            # the greeter -> broker -> seat -> power broker chain is the shutdown
            # itself; nothing else in this guest can trigger it.
            press(vm, 'ctrl', 'alt', 'end')
            vm.expect('Power down')
            vm.process.wait(timeout=30)
        except Exception as error:
            results.append(dict(name=case['name'], result='FAIL', error=str(error)))
            raise
        finally:
            vm.close()
        disk.unlink()
        results.append(dict(name=case['name'], result='PASS'))
        print('PASS ' + case['name'] + ': themed greeter, refused password, greeter-only authorization, '
              'authenticated session, logout, login-screen poweroff', flush=True)

    # Recovery keeps the explicit root console and can change the credentials.
    case = dict(recovery=True, name='login-recovery', machine='q35', ram=1024, cpu='qemu64', disk='virtio')
    disk = OUT / (case['name'] + '.raw')
    with disk.open('xb') as stream:
        stream.truncate(64 * 1024 * 1024)
    subprocess.run(['mkfs.ext4', '-q', '-F', str(disk)], check=True)
    vm = VM(case, disk, 'recovery')
    vm.deadline = time.monotonic() + 900
    try:
        vm.expect('WARNING: explicit unauthenticated root recovery session.')
        vm.prompt()
        vm.command('write /root/credential %s' % PASSWORD)
        vm.command('write /root/changed recovery-changed')
        vm.command('write /root/wrong not-the-password')
        vm.command('/bin/ominx-passwd --list', 'password-set')
        vm.command('/sbin/ominx-login --check ominx --password-file /root/credential', 'OK\t1000')
        vm.command('/sbin/ominx-login --check ominx --password-file /root/wrong', 'DENY')
        vm.command('/sbin/ominx-login --check guest --password-file /root/credential', 'DENY')
        vm.command('/bin/ominx-passwd --set ominx --password-file /root/changed', 'OK password-updated name=ominx')
        vm.command('/sbin/ominx-login --check ominx --password-file /root/changed', 'OK\t1000')
        vm.command('/sbin/ominx-login --check ominx --password-file /root/credential', 'DENY')
        vm.command('/bin/ominx-passwd --set nobody --password-file /root/changed', 'Refusing: no such packaged account')
        vm.command('/bin/ominx-passwd --set root --password-file /root/changed', 'Refusing: invalid account name')
        # An oversized password file is refused rather than truncated.
        vm.command('/sbin/ominx-login --check ominx --password-file /etc/ominx/accounts', 'Refusing')
        vm.command('rm /root/credential')
        vm.command('/sbin/ominx-login --check ominx --password-file /root/credential', 'Refusing')
        vm.shutdown()
    except Exception as error:
        results.append(dict(name=case['name'], result='FAIL', error=str(error)))
        raise
    finally:
        vm.close()
    disk.unlink()
    results.append(dict(name=case['name'], result='PASS'))
    print('PASS login-recovery: explicit root console, musl crypt verification, password change, '
          'no account creation', flush=True)
finally:
    (OUT / 'graphical-login.json').write_text(json.dumps(results, indent=2) + '\n')
