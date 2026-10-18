#!/bin/sh
# Verify the generated boot menus and their Debian Installer payloads before publishing an ISO.
set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$ROOT"

GRUB_MENU="$ROOT/binary/boot/grub/grub.cfg"
ISOLINUX_MENU="$ROOT/binary/isolinux/live.cfg"

for required_file in "$GRUB_MENU" "$ISOLINUX_MENU"; do
    if [ ! -s "$required_file" ]; then
        echo "Expected generated boot menu is missing: $required_file" >&2
        echo "Available candidates:" >&2
        find "$ROOT/binary" -type f \( -name grub.cfg -o -name live.cfg \) -print 2>/dev/null | head -40 >&2 || true
        exit 1
    fi
done

for title in "Try OminX Aurora" "Install OminX (graphical)" "OminX Aurora (safe graphics)"; do
    if ! grep -Fq "$title" "$GRUB_MENU"; then
        echo "Generated GRUB menu is missing: $title" >&2
        exit 1
    fi
    if ! grep -Fq "$title" "$ISOLINUX_MENU"; then
        echo "Generated ISOLINUX menu is missing: $title" >&2
        exit 1
    fi
done

if grep -Eq 'KERNEL_(LIVE|GI)|APPEND_(LIVE(_FAILSAFE)?|GI|INSTALL)|INITRD_(LIVE|GI)|LINUX_(LIVE|INSTALL|ADVANCED_INSTALL)|MEMTEST|@(KERNEL|LINUX|INITRD|APPEND|FLAVOUR)@' \
    "$GRUB_MENU" "$ISOLINUX_MENU"; then
    echo "An unresolved live-build boot-menu token remains in the generated menus." >&2
    exit 1
fi

for installer_file in \
    "$ROOT/binary/install/vmlinuz" \
    "$ROOT/binary/install/initrd.gz" \
    "$ROOT/binary/install/gtk/vmlinuz" \
    "$ROOT/binary/install/gtk/initrd.gz"; do
    if [ ! -s "$installer_file" ]; then
        echo "Debian Installer payload is missing: $installer_file" >&2
        exit 1
    fi
done

for splash in \
    "$ROOT/binary/boot/grub/splash.png" \
    "$ROOT/binary/isolinux/splash.png"; do
    if [ ! -s "$splash" ]; then
        echo "OminX boot splash is missing from the binary image: $splash" >&2
        exit 1
    fi
done

if ! command -v grub-script-check >/dev/null 2>&1; then
    echo "grub-script-check is required to validate the generated GRUB menu." >&2
    exit 1
fi
grub-script-check "$GRUB_MENU"
printf 'Verified OminX GRUB and ISOLINUX menus, both Debian Installer modes, and boot splash assets.\n'
