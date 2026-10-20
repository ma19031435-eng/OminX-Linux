#!/usr/bin/env python3
"""Render the original theme in upstream SDDM/Qt6 test mode. No PAM test claimed."""
import os
from pathlib import Path
import subprocess
import time

root = Path(__file__).resolve().parents[2]
out = root / 'build/greeter'
out.mkdir(parents=True, exist_ok=True)
env = dict(os.environ, QT_QUICK_BACKEND='software', QT_QUICK_CONTROLS_STYLE='Basic')
logpath = out / 'real-sddm.txt'
with logpath.open('w') as log:
    process = subprocess.Popen([str(root / 'build/sddm-host/src/greeter/sddm-greeter-qt6'),
                                '--test-mode', '--theme', str(root / 'desktop/sddm/ominx')],
                               stdout=log, stderr=subprocess.STDOUT, env=env)
    try:
        time.sleep(4)
        assert process.poll() is None, 'SDDM greeter exited early'
        subprocess.run(['import', '-window', 'root', str(out / 'real-sddm-1440.png')], check=True, timeout=10)
    finally:
        process.terminate()
        process.wait(timeout=10)
text = logpath.read_text()
for marker in ('Fallback to embedded theme', 'ReferenceError', 'TypeError', 'is not a type', 'Cannot assign', 'Unable to assign'):
    assert marker not in text, text
assert (out / 'real-sddm-1440.png').stat().st_size > 5000
print('PASS upstream SDDM 0.21 Qt6 test-mode rendered OminX theme without fallback/QML errors; no authentication/session launch asserted')
