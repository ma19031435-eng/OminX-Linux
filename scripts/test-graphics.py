#!/usr/bin/env python3
"""Actual source-kernel KMS/fbcon tests. Not a Qt/KDE or 3D-acceleration claim."""
import importlib.util
import json
from pathlib import Path
import subprocess

spec = importlib.util.spec_from_file_location('platforms', Path(__file__).with_name('test-platforms.py'))
platforms = importlib.util.module_from_spec(spec)
spec.loader.exec_module(platforms)
VM, OUT = platforms.VM, platforms.OUT
# Linux 6.12 uses drm_driver.name + "drmfb" (Bochs name is "bochs-drm").
cases = [
    dict(name='graphics-bochs', machine='q35', ram=512, cpu='qemu64', disk='virtio', vga='std', framebuffer='bochs-drmdrmfb'),
    dict(name='graphics-virtio', machine='q35', ram=512, cpu='qemu64', disk='virtio', vga='virtio', uefi=True, framebuffer='virtio_gpudrmfb'),
    dict(name='graphics-qxl', machine='pc', ram=512, cpu='qemu64', disk='virtio', vga='qxl', framebuffer='qxldrmfb'),
]
results = []
try:
    for case in cases:
        disk = OUT / (case['name'] + '.raw')
        with disk.open('xb') as stream:
            stream.truncate(64 * 1024 * 1024)
        subprocess.run(['mkfs.ext4', '-q', '-F', str(disk)], check=True)
        vm = VM(case, disk, 'kms')
        try:
            vm.expect('unprivileged user ominx')
            vm.expect('OminX console ready.')
            vm.prompt()
            vm.command('cat /proc/fb', case['framebuffer'])
            vm.command('files list /dev/dri', 'card0')
            vm.command('files info /dev/dri/card0', '"mode":432,"uid":0,"gid":44')
            vm.keyboard_check()
            # Read a real framebuffer dump, and reject a blank/unpainted surface.
            image = (OUT / (vm.name + '-display.ppm')).read_bytes()
            assert image.startswith(b'P6'), 'Missing framebuffer image'
            pixels = image.split(b'\n', 3)[3]
            assert pixels != pixels[:3] * (len(pixels) // 3), 'Blank framebuffer'
            vm.command('control', 'OK service=ominx-control protocol=1')
            vm.shutdown()
        except Exception as error:
            results.append(dict(name=case['name'], result='FAIL', error=str(error)))
            raise
        finally:
            vm.close()
        disk.unlink()
        results.append(dict(name=case['name'], result='PASS'))
        print(f"PASS {case['name']}: native framebuffer, unprivileged device policy, displayed console, keyboard, broker poweroff", flush=True)
finally:
    (OUT / 'graphics.json').write_text(json.dumps(results, indent=2) + '\n')
