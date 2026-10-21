#!/usr/bin/env python3
"""Source-built D-Bus service checks in real boot media, never host bus tests."""
import importlib.util
import json
from pathlib import Path
import subprocess

spec = importlib.util.spec_from_file_location('platforms', Path(__file__).with_name('test-platforms.py'))
p = importlib.util.module_from_spec(spec)
spec.loader.exec_module(p)
results = []
cases = [
    dict(name='bus-bios', machine='q35', ram=512, cpu='qemu64', disk='virtio'),
    dict(name='bus-uefi', machine='q35', ram=512, cpu='qemu64', disk='virtio', uefi=True),
    dict(name='bus-isolation', machine='q35', ram=512, cpu='qemu64', disk='virtio', recovery=True),
]
try:
    for case in cases:
        disk = p.OUT / (case['name'] + '.raw')
        with disk.open('xb') as stream:
            stream.truncate(64 * 1024 * 1024)
        subprocess.run(['mkfs.ext4', '-q', '-F', str(disk)], check=True)
        vm = p.VM(case, disk, 'ipc')
        try:
            vm.expect('OminX console ready.')
            vm.prompt()
            if case.get('recovery'):
                vm.command('/bin/ominx-bus-probe --deny-other-uid', 'PASS bus cross-uid isolation')
                vm.command('/sbin/ominx-desktop-bus', 'bus supervisor already running')
            else:
                vm.command('id', 'uid=1000 euid=1000 suid=1000')
                vm.command('/bin/ominx-bus-probe --guest-test', 'PASS bus: external credentials, system policy, session roundtrip, supervised restart')
                vm.command('files info /etc/machine-id', '"mode":292,"uid":0,"gid":0')
                vm.command('write /etc/machine-id denied', 'Permission denied')
                vm.command('/sbin/ominx-desktop-bus', 'requires root source boot context')
                vm.command('id', 'uid=1000 euid=1000 suid=1000')
            vm.command('control', 'OK service=ominx-control protocol=1')
            vm.shutdown()
        except Exception as error:
            results.append(dict(name=case['name'], result='FAIL', error=str(error)))
            raise
        finally:
            vm.close()
        disk.unlink()
        results.append(dict(name=case['name'], result='PASS'))
        print(f"PASS {case['name']}: source-linked IPC, fixed privilege policy, supervised service, controlled shutdown", flush=True)
finally:
    (p.OUT / 'desktop-bus.json').write_text(json.dumps(results, indent=2) + '\n')
