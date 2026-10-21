#!/usr/bin/env python3
"""Fail before compiling if Kconfig silently dropped required graphics facilities."""
from pathlib import Path
import sys

REQUIRED = (
    'DRM', 'DRM_SIMPLEDRM', 'DRM_FBDEV_EMULATION', 'FB_CORE', 'FB_DEVICE',
    'FRAMEBUFFER_CONSOLE', 'VT', 'VT_CONSOLE', 'INPUT_EVDEV', 'UNIX98_PTYS',
    'DRM_BOCHS', 'DRM_VIRTIO_GPU', 'DRM_QXL', 'DRM_VMWGFX', 'DRM_I915',
    'DRM_AMDGPU', 'DRM_NOUVEAU',
)


def check(text):
    lines = set(text.splitlines())
    missing = [key for key in REQUIRED if f'CONFIG_{key}=y' not in lines]
    if missing:
        raise ValueError('Required built-in kernel options missing: ' + ', '.join(missing))


if __name__ == '__main__':
    if len(sys.argv) != 2:
        raise SystemExit('Usage: check-kernel-graphics.py KERNEL_CONFIG')
    try:
        check(Path(sys.argv[1]).read_text())
    except ValueError as error:
        raise SystemExit(str(error))
