#!/usr/bin/env python3
"""Source-linked target Qt raster rendering + real evdev input, not KDE/login."""
import importlib.util
import json
from pathlib import Path
import subprocess

spec = importlib.util.spec_from_file_location('platforms', Path(__file__).with_name('test-platforms.py'))
p = importlib.util.module_from_spec(spec)
spec.loader.exec_module(p)
results = []
cases = [
    dict(name='qt-bochs', machine='q35', ram=768, cpu='qemu64', disk='virtio', vga='std'),
    dict(name='qt-virtio', machine='q35', ram=768, cpu='qemu64', disk='virtio', vga='virtio', uefi=True),
    dict(name='qt-qxl', machine='pc', ram=768, cpu='qemu64', disk='virtio', vga='qxl'),
]
try:
    for case in cases:
        disk = p.OUT / (case['name'] + '.raw')
        with disk.open('xb') as stream:
            stream.truncate(64 * 1024 * 1024)
        subprocess.run(['mkfs.ext4', '-q', '-F', str(disk)], check=True)
        vm = p.VM(case, disk, 'target')
        try:
            vm.expect('unprivileged user ominx')
            vm.expect('OminX console ready.')
            vm.prompt()
            vm.command('id', 'uid=1000 euid=1000 suid=1000')
            vm.send('/bin/ominx-graphics-probe -platform linuxfb:fb=/dev/fb0')
            vm.expect('OMINX_QT_FRAME_PAINTED')
            # A queued Qt paint acknowledgement is not evidence that QEMU displays it.
            # Capture after an input round-trip, then verify the exact raster colours.
            vm.qmp_command('send-key', {'keys': [{'type': 'qcode', 'data': 'spc'}], 'hold-time': 50})
            vm.expect('OMINX_QT_INPUT_OK')
            screenshot = p.OUT / (vm.name + '-qt.ppm')
            # Capture until a rendered frame appears; bounded by QMP command timeout
            # and a finite attempt count, never accept merely nonblank firmware pixels.
            for attempt in range(20):
                vm.qmp_command('screendump', {'filename': str(screenshot)})
                image = screenshot.read_bytes()
                assert image.startswith(b'P6\n'), 'Expected a QEMU RGB framebuffer dump'
                pixels = image.split(b'\n', 3)[3]
                counts = [sum(pixels[i:i+3] == color for i in range(0, len(pixels), 3))
                          for color in (bytes.fromhex('0b1220'), bytes.fromhex('334155'), bytes.fromhex('ffb454'))]
                if min(counts) > len(pixels) // 300:
                    break
            else:
                raise AssertionError('Target Qt colours missing from actual display')
            vm.qmp_command('send-key', {'keys': [{'type': 'qcode', 'data': 'ret'}], 'hold-time': 50})
            vm.expect('OMINX_QT_EXIT_OK')
            vm.prompt()
            vm.command('id', 'uid=1000 euid=1000 suid=1000')
            vm.shutdown()
        except Exception as error:
            results.append(dict(name=case['name'], result='FAIL', error=str(error)))
            raise
        finally:
            vm.close()
        disk.unlink()
        results.append(dict(name=case['name'], result='PASS', colors=counts))
        print(f"PASS {case['name']}: source-built musl Qt, UID1000 raster display, real keyboard, return to console", flush=True)
finally:
    (p.OUT / 'qt-target.json').write_text(json.dumps(results, indent=2) + '\n')
