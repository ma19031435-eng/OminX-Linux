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
        try:
            vm.expect('OminX console ready.')
            vm.prompt()
            vm.command('id', 'uid=1000 euid=1000 suid=1000')
            wait_for(vm, '/run/ominx/seat.log', 'greeter started pid=')
            wait_for(vm, '/run/ominx/greeter.log', 'OMINX_GREETER_READY')
            counts = colors(vm, 'greeter', ('74e0c7', '101d32', '4fa3ff'))
            assert counts['74e0c7'] > 400, 'themed greeter accent not rendered: %r' % counts
            assert counts['101d32'] > 4000, 'greeter background not rendered: %r' % counts
            assert counts['4fa3ff'] == 0, 'session colours visible before login: %r' % counts
            # A wrong password must be refused and must not start a session.
            type_text(vm, 'ominx\nwrong-password\n')
            wait_for(vm, '/run/ominx/greeter.log', 'OMINX_LOGIN_DENIED user=ominx reason=credentials')
            wait_for(vm, '/run/ominx/login-service.log', 'login: denied name=ominx reason=credentials')
            assert 'session started' not in read_file(vm, '/run/ominx/seat.log'), 'session started after refusal'
            # The ordinary console identity may not use the login service at all.
            vm.send('echo %s | /bin/ominx-login-probe AUTH ominx' % PASSWORD)
            vm.expect('DENY')
            vm.prompt()
            vm.command('/bin/ominx-login-probe SESSION', 'DENY')
            vm.command('/bin/ominx-login-probe LIST', 'DENY')
            # The correct password starts the real user session.
            type_text(vm, 'ominx\n' + PASSWORD + '\n')
            wait_for(vm, '/run/ominx/seat.log', 'session started uid=1000')
            wait_for(vm, '/run/ominx/session.log', 'OMINX_SESSION_READY user=ominx home=/home/ominx')
            session_colors = colors(vm, 'session', ('4fa3ff', '74e0c7', '0b1520'))
            assert session_colors['4fa3ff'] > 60, 'desktop shell accent not rendered: %r' % session_colors
            assert session_colors['0b1520'] > 2000, 'desktop taskbar not rendered: %r' % session_colors
            # Log out through the shell: the start menu focus starts on Log out.
            press(vm, 'meta_l')
            press(vm, 'ret')
            wait_for(vm, '/run/ominx/seat.log', 'session ended uid=1000')
            wait_for(vm, '/run/ominx/greeter.log', 'OMINX_SESSION_LOGOUT')
            vm.expect('ominx:/home/ominx$ ')
            after = read_file(vm, '/run/ominx/greeter.log')
            assert after.count('OMINX_GREETER_READY') >= 2, 'greeter did not return after logout'
            # Power off from the login screen goes through the fixed services.
            press(vm, 'ctrl', 'alt', 'end')
            vm.expect('shutdown requested from the login screen')
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
    try:
        vm.expect('WARNING: explicit unauthenticated root recovery session.')
        vm.prompt()
        vm.command('/bin/ominx-passwd --list', 'password-set')
        vm.command('echo %s | /sbin/ominx-login --check ominx' % PASSWORD, 'OK\t1000')
        vm.command('echo %s | /sbin/ominx-login --check ominx' % 'not-the-password', 'DENY')
        vm.command('echo %s | /bin/ominx-passwd --set ominx' % 'recovery-changed', 'OK password-updated name=ominx')
        vm.command('echo %s | /sbin/ominx-login --check ominx' % 'recovery-changed', 'OK\t1000')
        vm.command('echo %s | /sbin/ominx-login --check ominx' % PASSWORD, 'DENY')
        vm.command('/bin/ominx-passwd --set nobody', 'Refusing')
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
