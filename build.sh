#!/bin/sh
# Source-built target only. Legacy Debian build remains a separate opt-in command.
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
cd "$ROOT"
. toolchain/sources.env
PREFIX="$ROOT/build/toolchain/bin/$TARGET-"
if [ ! -x "${PREFIX}gcc" ]; then
    echo 'Build the source toolchain first: make toolchain' >&2
    exit 1
fi
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
    -e USB_HID -e HID_GENERIC -e USB_XHCI_HCD -e USB_XHCI_PCI \
    -e VIRTIO_PCI -e VIRTIO_BLK -e EXT4_FS -e SATA_AHCI -e BLK_DEV_NVME \
    -e USB_STORAGE -e FAT_FS -e VFAT_FS
make -C "$LINUX_SOURCE" O="$ROOT/build/kernel" ARCH=x86_64 CROSS_COMPILE="$PREFIX" olddefconfig
make -C "$LINUX_SOURCE" O="$ROOT/build/kernel" ARCH=x86_64 CROSS_COMPILE="$PREFIX" -j"${JOBS:-2}" bzImage
cp build/kernel/arch/x86/boot/bzImage build/bzImage
cp build/kernel/.config build/provenance/kernel.config
cp toolchain/sources.env build/provenance/
"${PREFIX}gcc" -v 2> build/provenance/compiler.txt
"${PREFIX}readelf" -l build/ominx > build/provenance/ominx-elf.txt
if grep -q INTERP build/provenance/ominx-elf.txt; then
    echo 'Unexpected dynamic target executable' >&2; exit 1
fi
scripts/build-media.sh
