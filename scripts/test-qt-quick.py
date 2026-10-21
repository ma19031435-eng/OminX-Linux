#!/usr/bin/env python3
"""Source-linked Qt Quick/theme rendering and fail-closed input; no authentication."""
import importlib.util
import json
from pathlib import Path
import subprocess
import time

spec = importlib.util.spec_from_file_location('platforms', Path(__file__).with_name('test-platforms.py'))
p = importlib.util.module_from_spec(spec)
spec.loader.exec_module(p)
results = []
cases = [
    dict(name='quick-bochs', machine='q35', ram=1024, cpu='qemu64', disk='virtio', vga='std'),
    dict(name='quick-virtio', machine='q35', ram=1024, cpu='qemu64', disk='virtio', vga='virtio', uefi=True),
    dict(name='quick-qxl', machine='pc', ram=1024, cpu='qemu64', disk='virtio', vga='qxl'),
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
            vm.send('/bin/ominx-quick-probe -platform linuxfb:fb=/dev/fb0')
            vm.expect('OMINX_QUICK_FRAME_READY')
            screenshot = p.OUT / (vm.name + '-quick.ppm')
            for attempt in range(20):
                vm.qmp_command('screendump', {'filename': str(screenshot)})
                image = screenshot.read_bytes()
                assert image.startswith(b'P6\n'), 'Expected a QEMU RGB framebuffer dump'
                pixels = image.split(b'\n', 3)[3]
                counts = [sum(pixels[i:i+3] == color for i in range(0, len(pixels), 3))
                          for color in (bytes.fromhex('74e0c7'), bytes.fromhex('51242a'))]
                if min(counts) > 1000:
                    break
            else:
                raise AssertionError('Actual theme and validation banner colours absent')
            # These are explicitly dummy strings for a disabled-context graphics test.
            # No login backend or installed desktop session exists in this application.
            for char in 'probe\nprobe\n':
                key = 'ret' if char == '\n' else char
                vm.qmp_command('send-key', {'keys': [{'type': 'qcode', 'data': key}], 'hold-time': 80})
                # Waiting for release avoids overlapping QMP key-down events.
                time.sleep(0.12)
            vm.expect('OMINX_QUICK_NO_SESSION_REFUSED')
            vm.qmp_command('send-key', {'keys': [{'type': 'qcode', 'data': 'esc'}], 'hold-time': 80})
            vm.expect('OMINX_QUICK_INPUT_OK')
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
        print(f"PASS {case['name']}: source-built Qt Quick, actual theme pixels, masked input, absent-session refusal, Escape clearing", flush=True)
finally:
    (p.OUT / 'qt-quick.json').write_text(json.dumps(results, indent=2) + '\n')
