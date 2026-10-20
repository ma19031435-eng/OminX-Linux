#!/bin/sh
# Build a standalone x86-64 Linux + original OminX initramfs. No root needed.
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
cd "$ROOT"
make initramfs
if [ -z "${LINUX_SOURCE:-}" ]; then
    echo 'Initramfs built. To build the kernel, set LINUX_SOURCE to an upstream Linux source tree.'
    echo 'Example: LINUX_SOURCE=/path/to/linux ./build.sh'
    exit 0
fi
LINUX_SOURCE=$(CDPATH= cd -- "$LINUX_SOURCE" && pwd)
[ -f "$LINUX_SOURCE/Kbuild" ] || { echo 'Not a Linux source tree' >&2; exit 1; }
mkdir -p "$ROOT/build/kernel"
make -C "$LINUX_SOURCE" O="$ROOT/build/kernel" ARCH=x86_64 x86_64_defconfig
"$LINUX_SOURCE/scripts/config" --file "$ROOT/build/kernel/.config" \
    -e BLK_DEV_INITRD -e RD_GZIP -e DEVTMPFS -e PROC_FS -e SYSFS \
    -e TMPFS -e SERIAL_8250 -e SERIAL_8250_CONSOLE -e BINFMT_ELF
make -C "$LINUX_SOURCE" O="$ROOT/build/kernel" ARCH=x86_64 olddefconfig
make -C "$LINUX_SOURCE" O="$ROOT/build/kernel" ARCH=x86_64 -j"${JOBS:-2}" bzImage
cp build/kernel/arch/x86/boot/bzImage build/bzImage
(cd build && sha256sum bzImage initramfs.cpio.gz > SHA256SUMS)
echo 'Built kernel and initramfs. Run make run for a serial QEMU console.'
