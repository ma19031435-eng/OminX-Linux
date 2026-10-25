#!/bin/sh
# Source-built target only. No distribution base is used.
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
cd "$ROOT"
. toolchain/sources.env
PREFIX="$ROOT/build/toolchain/bin/$TARGET-"
if [ ! -x "${PREFIX}gcc" ]; then
    echo 'Build the source toolchain first: make toolchain' >&2
    exit 1
fi
LIBC=$(readlink -f "$("${PREFIX}gcc" -print-file-name=libc.a)")
case "$LIBC" in
    "$ROOT/build/toolchain/"*) ;;
    *) echo "Refusing target libc outside source toolchain: $LIBC" >&2; exit 1 ;;
esac
mkdir -p build/sources build/kernel build/provenance
LINUX_SOURCE="$ROOT/build/sources/linux"
scripts/fetch-source.sh https://github.com/gregkh/linux.git "$LINUX_TAG" "$LINUX_COMMIT" "$LINUX_SOURCE"
# Force a target rebuild even if a prior host-test executable exists.
make -B initramfs CC="${PREFIX}gcc"
make -C "$LINUX_SOURCE" O="$ROOT/build/kernel" ARCH=x86_64 CROSS_COMPILE="$PREFIX" x86_64_defconfig
"$LINUX_SOURCE/scripts/config" --file "$ROOT/build/kernel/.config" \
    -e BLK_DEV_INITRD -e RD_GZIP -e DEVTMPFS -e PROC_FS -e SYSFS \
    -e TMPFS -e SERIAL_8250 -e SERIAL_8250_CONSOLE -e BINFMT_ELF \
    -e EFI -e EFI_STUB -e SYSFB_SIMPLEFB -e DRM -e DRM_SIMPLEDRM \
    -e FRAMEBUFFER_CONSOLE -e VT -e VT_CONSOLE -e INPUT_EVDEV \
    -e UNIX98_PTYS -e FB_DEVICE -e DRM_FBDEV_EMULATION -e DRM_BOCHS -e DRM_VIRTIO_GPU \
    -e DRM_QXL -e DRM_VMWGFX -e DRM_I915 -e DRM_AMDGPU -e DRM_NOUVEAU \
    -e USB_HID -e HID_GENERIC -e USB_XHCI_HCD -e USB_XHCI_PCI \
    -e VIRTIO_PCI -e VIRTIO_BLK -e EXT4_FS -e SATA_AHCI -e BLK_DEV_NVME \
    -e USB_STORAGE -e FAT_FS -e VFAT_FS -e EXFAT_FS -e NTFS3_FS -e NLS_UTF8 -e NLS_CODEPAGE_437 -e NLS_ISO8859_1 \
    -e ISO9660_FS -e UDF_FS
# Windows compatibility (Wine/Proton) and final-desktop prerequisites. Every
# symbol here is asserted by scripts/check-kernel-graphics.py so a Kconfig
# change cannot silently drop it before the multi-hour kernel build.
"$LINUX_SOURCE/scripts/config" --file "$ROOT/build/kernel/.config" \
    -e BINFMT_MISC -e BINFMT_SCRIPT -e IA32_EMULATION \
    -e NAMESPACES -e UTS_NS -e IPC_NS -e USER_NS -e PID_NS -e NET_NS \
    -e CGROUPS -e CGROUP_SCHED -e MEMCG -e SECCOMP -e SECCOMP_FILTER \
    -e SYSVIPC -e POSIX_MQUEUE -e INOTIFY_USER -e FANOTIFY -e USERFAULTFD \
    -e TMPFS_POSIX_ACL -e TMPFS_XATTR -e FUSE_FS -e OVERLAY_FS -e UDMABUF \
    -e INPUT_JOYDEV -e INPUT_UINPUT -e UHID -e HIDRAW \
    -e SOUND -e SND -e SND_HDA_INTEL -e SND_USB_AUDIO \
    -e TRANSPARENT_HUGEPAGE -e IKCONFIG -e IKCONFIG_PROC
make -C "$LINUX_SOURCE" O="$ROOT/build/kernel" ARCH=x86_64 CROSS_COMPILE="$PREFIX" olddefconfig
python3 scripts/check-kernel-graphics.py build/kernel/.config
make -C "$LINUX_SOURCE" O="$ROOT/build/kernel" ARCH=x86_64 CROSS_COMPILE="$PREFIX" -j"${JOBS:-2}" bzImage
cp build/kernel/arch/x86/boot/bzImage build/bzImage
cp build/kernel/.config build/provenance/kernel.config
cp toolchain/sources.env build/provenance/
"${PREFIX}gcc" -v 2> build/provenance/compiler.txt
"${PREFIX}readelf" -l build/ominx > build/provenance/ominx-elf.txt
if grep -q INTERP build/provenance/ominx-elf.txt; then
    echo 'Unexpected dynamic target executable' >&2; exit 1
fi
sha256sum "$LIBC" > build/provenance/target-libc.sha256
scripts/build-media.sh
