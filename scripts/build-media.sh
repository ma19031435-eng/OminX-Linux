#!/bin/sh
# Compile the upstream bootloader and author BIOS/UEFI bootable media.
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$ROOT"
. toolchain/sources.env
SOURCE="$ROOT/build/sources/limine"
PREFIX="$ROOT/build/toolchain/bin/$TARGET-"
scripts/fetch-source.sh https://github.com/limine-bootloader/limine.git "$LIMINE_TAG" "$LIMINE_COMMIT" "$SOURCE"
if [ ! -f "$SOURCE/configure" ]; then (cd "$SOURCE" && ./bootstrap); fi
mkdir -p build/limine
(cd build/limine && "$SOURCE/configure" --enable-bios --enable-bios-cd \
    --enable-uefi-x86-64 --enable-uefi-cd TOOLCHAIN_FOR_TARGET="${PREFIX%-}")
make -C build/limine -j"${JOBS:-2}"
STAGE="$ROOT/build/media-root"
mkdir -p "$STAGE/boot/limine" "$STAGE/EFI/BOOT"
cp build/bzImage build/initramfs.cpio.gz "$STAGE/boot/"
cp boot/limine.conf "$STAGE/boot/limine/limine.conf"
cp build/limine/bin/limine-bios.sys build/limine/bin/limine-bios-cd.bin \
    build/limine/bin/limine-uefi-cd.bin "$STAGE/boot/limine/"
cp build/limine/bin/BOOTX64.EFI "$STAGE/EFI/BOOT/BOOTX64.EFI"
xorriso -as mkisofs -R -r -J -V OMINX_CORE \
    -b boot/limine/limine-bios-cd.bin -no-emul-boot -boot-load-size 4 -boot-info-table \
    --efi-boot boot/limine/limine-uefi-cd.bin -efi-boot-part --efi-boot-image \
    --protective-msdos-label "$STAGE" -o build/ominx-x86_64.iso
build/limine/bin/limine bios-install build/ominx-x86_64.iso
(cd build && sha256sum bzImage initramfs.cpio.gz ominx-x86_64.iso > SHA256SUMS)
