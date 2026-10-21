#!/usr/bin/env python3
"""Real-media shared-loader, Wayland protocol, keyboard-map and Mesa shader tests."""
import importlib.util
import json
from pathlib import Path
import subprocess
spec=importlib.util.spec_from_file_location('platforms',Path(__file__).with_name('test-platforms.py'))
p=importlib.util.module_from_spec(spec);spec.loader.exec_module(p)
cases=[dict(name='runtime-bios',machine='q35',ram=1024,cpu='qemu64',disk='virtio',vga='std'),
       dict(name='runtime-uefi',machine='q35',ram=1024,cpu='qemu64',disk='virtio',vga='virtio',uefi=True)]
results=[]
try:
    for case in cases:
        disk=p.OUT/(case['name']+'.raw')
        with disk.open('xb') as f:f.truncate(64*1024*1024)
        subprocess.run(['mkfs.ext4','-q','-F',str(disk)],check=True)
        vm=p.VM(case,disk,'shared')
        try:
            vm.expect('OminX console ready.');vm.prompt()
            vm.command('id','uid=1000 euid=1000 suid=1000')
            vm.command('/usr/bin/ominx-render-probe --guest-test','PASS source shared graphics: Wayland, XKB, EGL and shader pixels')
            # A second process must work too: socket and rendering teardown mattered.
            vm.command('/usr/bin/ominx-render-probe --guest-test','PASS source shared graphics: Wayland, XKB, EGL and shader pixels')
            vm.command('control','OK service=ominx-control protocol=1')
            vm.shutdown()
        except Exception as error:
            results.append(dict(name=case['name'],result='FAIL',error=str(error)));raise
        finally:vm.close()
        disk.unlink();results.append(dict(name=case['name'],result='PASS'))
        print('PASS '+case['name']+': source shared loader, Wayland sync, XKB, Mesa shader pixels, repeat launch, poweroff',flush=True)
finally:(p.OUT/'graphics-runtime.json').write_text(json.dumps(results,indent=2)+'\n')
