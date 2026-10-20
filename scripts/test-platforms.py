#!/usr/bin/env python3
"""Boot real ISO media on an x86-64 firmware/device matrix, not direct -kernel."""
import json
import os
from pathlib import Path
import selectors
import shutil
import socket
import subprocess
import time

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'build/acceptance'
OUT.mkdir(parents=True, exist_ok=True)
ISO = ROOT / 'build/ominx-x86_64.iso'
RECOVERY_ISO = ROOT / 'build/ominx-recovery-x86_64.iso'
CASES = [
    dict(recovery=True, name='bios-pc-256', machine='pc', ram=256, cpu='qemu64', disk='virtio'),
    dict(recovery=True, name='bios-q35-512', machine='q35', ram=512, cpu='max', disk='sata'),
    dict(recovery=True, name='uefi-q35-512', machine='q35', ram=512, cpu='qemu64', disk='virtio', uefi=True),
    dict(recovery=True, name='uefi-pc-1024', machine='pc', ram=1024, cpu='max', disk='nvme', uefi=True),
    dict(recovery=True, name='bios-usb-512', machine='q35', ram=512, cpu='qemu64', disk='virtio', usb=True),
]


class VM:
    def __init__(self, case, data, attempt, extras=()):
        self.name = case['name'] + '-' + attempt
        recovery = case.get('recovery', False)
        iso = RECOVERY_ISO if recovery else ISO
        self.home = '/root' if recovery else '/home/ominx'
        self.prompt_text = f'ominx:{self.home}' + ('# ' if recovery else '$ ')
        self.log = bytearray()
        self.cursor = 0
        self.deadline = time.monotonic() + 180
        self.qmp_path = OUT / (self.name + '.sock')
        self.qmp_path.unlink(missing_ok=True)
        args = ['qemu-system-x86_64', '-machine', case['machine'], '-accel', 'tcg',
                '-cpu', case['cpu'], '-m', str(case['ram']), '-display', 'none',
                '-serial', 'stdio', '-monitor', 'none', '-nic', 'none',
                '-qmp', f'unix:{self.qmp_path},server=on,wait=off']
        if case.get('vga'):
            args += ['-vga', case['vga']]
        if case.get('usb'):
            args += ['-device', 'qemu-xhci', '-drive', f'if=none,id=bootusb,file={iso},format=raw,readonly=on',
                     '-device', 'usb-storage,drive=bootusb,bootindex=1']
        else:
            args += ['-cdrom', str(iso), '-boot', 'order=d']
        if case.get('uefi'):
            code = Path('/usr/share/OVMF/OVMF_CODE_4M.fd')
            variables = Path('/usr/share/OVMF/OVMF_VARS_4M.fd')
            if not code.exists() or not variables.exists():
                raise RuntimeError('Install OVMF with the 4M firmware pair')
            local_vars = OUT / (self.name + '-vars.fd')
            shutil.copyfile(variables, local_vars)
            args += ['-drive', f'if=pflash,format=raw,unit=0,readonly=on,file={code}',
                     '-drive', f'if=pflash,format=raw,unit=1,file={local_vars}']
        if case['disk'] == 'virtio':
            args += ['-drive', f'if=virtio,format=raw,file={data}']
            self.device = '/dev/vda'
        elif case['disk'] == 'sata':
            args += ['-drive', f'if=ide,format=raw,file={data}']
            self.device = '/dev/sda'
        else:
            args += ['-drive', f'if=none,id=data,format=raw,file={data}',
                     '-device', 'nvme,drive=data,serial=OMINXTEST']
            self.device = '/dev/nvme0n1'
        for extra in extras:
            args += ['-drive', f'if=virtio,format=raw,readonly=on,file={extra}']
        self.process = subprocess.Popen(args, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                        stderr=subprocess.STDOUT)
        self.selector = selectors.DefaultSelector()
        self.selector.register(self.process.stdout, selectors.EVENT_READ)
        self.qmp = None
        self.qfile = None

    def expect(self, marker):
        marker = marker.encode()
        while True:
            found = self.log.find(marker, self.cursor)
            if found >= 0:
                self.cursor = found + len(marker)
                return
            if time.monotonic() > self.deadline:
                raise RuntimeError(f'{self.name}: timeout waiting for {marker!r}')
            if not self.selector.get_map():
                raise RuntimeError(f'{self.name}: emulator closed before {marker!r}')
            for key, _ in self.selector.select(1):
                chunk = os.read(key.fileobj.fileno(), 65536)
                if chunk:
                    self.log.extend(chunk)
                else:
                    self.selector.unregister(key.fileobj)

    def prompt(self):
        self.expect(self.prompt_text)

    def send(self, command):
        self.process.stdin.write(command.encode() + b'\n')
        self.process.stdin.flush()

    def command(self, command, output=None):
        self.send(command)
        if output:
            self.expect(output)
        self.prompt()

    def qmp_command(self, name, arguments=None):
        if self.qmp is None:
            self.qmp = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            self.qmp.settimeout(10)
            self.qmp.connect(str(self.qmp_path))
            self.qfile = self.qmp.makefile('rwb')
            json.loads(self.qfile.readline())  # greeting
            self.qmp_command('qmp_capabilities')
        self.qfile.write((json.dumps(dict(execute=name, arguments=arguments or {})) + '\n').encode())
        self.qfile.flush()
        while True:
            response = json.loads(self.qfile.readline())
            if 'error' in response:
                raise RuntimeError(response)
            if 'return' in response:
                return response['return']

    def keyboard_check(self):
        # Send actual virtual PS/2 keyboard events to tty1, not to the serial shell.
        for char in f'write {self.home}/keyboard keyboardok\n':
            key = {' ': 'spc', '/': 'slash', '\n': 'ret'}.get(char, char)
            self.qmp_command('send-key', {'keys': [{'type': 'qcode', 'data': key}], 'hold-time': 20})
            time.sleep(0.06)
        self.command(f'cat {self.home}/keyboard', '\r\nkeyboardok\r\n')
        self.qmp_command('screendump', {'filename': str(OUT / (self.name + '-display.ppm'))})

    def shutdown(self):
        self.send('poweroff')
        self.expect('Power down')
        self.process.wait(timeout=20)
        if self.process.returncode != 0 or b'Kernel panic' in self.log:
            raise RuntimeError('Guest failed to shut down cleanly')

    def close(self):
        if self.process.poll() is None:
            self.process.kill()
        self.process.wait()
        if self.qfile:
            self.qfile.close()
        if self.qmp:
            self.qmp.close()
        self.selector.close()
        self.qmp_path.unlink(missing_ok=True)
        (OUT / (self.name + '.txt')).write_bytes(self.log)


def run_case(case):
    data = OUT / (case['name'] + '-data.raw')
    # Never accept a host device path or overwrite a pre-existing disk image.
    with data.open('xb') as stream:
        stream.truncate(64 * 1024 * 1024)
    subprocess.run(['mkfs.ext4', '-q', '-F', str(data)], check=True)
    vm = VM(case, data, 'write')
    try:
        vm.expect('OminX console ready.')
        vm.prompt()
        vm.command('uname', 'Linux 6.12.60 x86_64')
        vm.command('cat /etc/os-release', 'ID=ominx')
        vm.command('nonsense', 'Unknown command')
        vm.command('cat /missing-ominx-test', 'No such file')
        vm.command('attach /etc/os-release', 'not a block device')
        vm.command('write /root/probe ramdata')
        vm.command('cp /root/probe /root/copy')
        vm.command('mv /root/copy /root/moved')
        vm.command('cat /root/moved', '\r\nramdata\r\n')
        vm.command('rm /root/moved')
        vm.command('write "file with spaces.txt" "quoted contents"')
        vm.command('files copy "file with spaces.txt" "copied file.txt"', '{"ok":true}')
        vm.command('cat "copied file.txt"', '\r\nquoted contents\r\n')
        vm.command('files copy "file with spaces.txt" "copied file.txt"', 'File exists')
        vm.command('files list /root', '"complete":true')
        vm.command('files move "copied file.txt" "moved file.txt"', '{"ok":true}')
        vm.command('files remove --confirm "moved file.txt"', '{"ok":true}')
        vm.send('exit')
        vm.expect('OminX console ready.')
        vm.prompt()
        vm.command('cat /root/probe', '\r\nramdata\r\n')
        vm.keyboard_check()
        vm.command(f'attach {vm.device}', 'Data attached')
        vm.command(f'attach {vm.device}', 'already attached')
        vm.command('write /mnt/data/probe persistentdata')
        vm.command('cat /mnt/data/probe', '\r\npersistentdata\r\n')
        vm.command('detach', 'Data detached')
        vm.shutdown()
    finally:
        vm.close()
    vm = VM(case, data, 'read')
    try:
        vm.expect('OminX console ready.')
        vm.prompt()
        vm.command(f'attach {vm.device} ro', 'Data attached')
        vm.command('cat /mnt/data/probe', '\r\npersistentdata\r\n')
        vm.command('write /mnt/data/forbidden no', 'Read-only file system')
        vm.command('detach', 'Data detached')
        vm.send('reboot')
        vm.expect('reboot: Restarting system')
        vm.expect('OminX console ready.')
        vm.prompt()
        vm.command(f'attach {vm.device}', 'Data attached')
        vm.command('cat /mnt/data/probe', '\r\npersistentdata\r\n')
        vm.shutdown()  # also tests automatic clean data unmount on poweroff
    finally:
        vm.close()
    subprocess.run(['e2fsck', '-fn', str(data)], check=True, capture_output=True)
    data.unlink()  # disposable test image; never part of release artifacts


if __name__ == '__main__':
    results = []
    try:
        for case in CASES:
            start = time.monotonic()
            try:
                run_case(case)
            except Exception as error:
                results.append(dict(**case, result='FAIL', error=str(error)))
                raise
            results.append(dict(**case, result='PASS', seconds=round(time.monotonic() - start, 1)))
            print(f"PASS {case['name']}: firmware/media boot, terminal, keyboard/display, file operations, "
                  'console restart, persistent storage, read-only refusal, reboot, clean poweroff', flush=True)
    finally:
        (OUT / 'results.json').write_text(json.dumps(results, indent=2) + '\n')
