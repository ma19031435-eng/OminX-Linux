#!/usr/bin/env python3
"""Fail before compiling if Kconfig silently dropped required facilities.

The image packages no loadable modules, so every feature the desktop or the
Wine/Proton layer depends on must be built in. Grouped by consumer so a
failure message names the layer that broke. """
from pathlib import Path
import sys

GRAPHICS = (
    'DRM', 'DRM_SIMPLEDRM', 'DRM_FBDEV_EMULATION', 'FB_CORE', 'FB_DEVICE',
    'FRAMEBUFFER_CONSOLE', 'VT', 'VT_CONSOLE', 'INPUT_EVDEV', 'UNIX98_PTYS',
    'DRM_BOCHS', 'DRM_VIRTIO_GPU', 'DRM_QXL', 'DRM_VMWGFX', 'DRM_I915',
    'DRM_AMDGPU', 'DRM_NOUVEAU',
)
# Wine, Proton and their first-boot/background services: binfmt for direct
# .exe execution, namespaces/cgroups/seccomp for Steam-style containers,
# SysV/POSIX IPC and notification APIs Windows programs expect, userfaultfd,
# tmpfs xattrs/ACLs for prefix files, FUSE/overlay for compatibility tools,
# udmabuf and game-controller devices, and desktop audio.
WINDOWS = (
    'BINFMT_ELF', 'BINFMT_MISC', 'BINFMT_SCRIPT', 'IA32_EMULATION',
    'NAMESPACES', 'UTS_NS', 'IPC_NS', 'USER_NS', 'PID_NS', 'NET_NS',
    'CGROUPS', 'CGROUP_SCHED', 'MEMCG', 'SECCOMP', 'SECCOMP_FILTER',
    'SYSVIPC', 'POSIX_MQUEUE', 'INOTIFY_USER', 'FANOTIFY', 'USERFAULTFD',
    'TMPFS', 'TMPFS_POSIX_ACL', 'TMPFS_XATTR', 'FUSE_FS', 'OVERLAY_FS',
    'UDMABUF', 'INPUT_JOYDEV', 'INPUT_UINPUT', 'UHID', 'HIDRAW',
    'SOUND', 'SND', 'SND_HDA_INTEL', 'SND_USB_AUDIO',
    'TRANSPARENT_HUGEPAGE', 'IKCONFIG', 'IKCONFIG_PROC',
    'EXT4_FS', 'VFAT_FS', 'EXFAT_FS', 'NTFS3_FS', 'ISO9660_FS', 'UDF_FS',
)
REQUIRED = GRAPHICS + WINDOWS


def check(text):
    lines = set(text.splitlines())
    problems = []
    for group, keys in (('graphics', GRAPHICS), ('windows-compatibility', WINDOWS)):
        missing = [key for key in keys if f'CONFIG_{key}=y' not in lines]
        if missing:
            problems.append(group + ': ' + ', '.join(missing))
    if problems:
        raise ValueError('Required built-in kernel options missing: ' + '; '.join(problems))


if __name__ == '__main__':
    if len(sys.argv) != 2:
        raise SystemExit('Usage: check-kernel-graphics.py KERNEL_CONFIG')
    try:
        check(Path(sys.argv[1]).read_text())
    except ValueError as error:
        raise SystemExit(str(error))
