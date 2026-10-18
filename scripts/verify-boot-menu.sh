#!/bin/sh
# Verify the generated GRUB menu and Debian Installer payloads before publishing an ISO.
set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$ROOT"

GRUB_MENU="$ROOT/binary/boot/grub/grub.cfg"
EFI_GRUB_CONFIG="$ROOT/binary/boot/grub/x86_64-efi/grub.cfg"

if [ ! -s "$GRUB_MENU" ]; then
    echo "Expected generated GRUB menu is missing: $GRUB_MENU" >&2
    echo "Available GRUB configs:" >&2
    find "$ROOT/binary" -type f -name grub.cfg -print 2>/dev/null | head -40 >&2 || true
    exit 1
fi

for title in "Try OminX Aurora" "Install OminX (graphical)" "OminX Aurora (safe graphics)"; do
    if ! grep -Fq "$title" "$GRUB_MENU"; then
        echo "Generated GRUB menu is missing: $title" >&2
        exit 1
    fi
done

if grep -Eq 'KERNEL_(LIVE|GI)|APPEND_(LIVE(_FAILSAFE)?|GI|INSTALL)|INITRD_(LIVE|GI)|LINUX_(LIVE|INSTALL|ADVANCED_INSTALL)|MEMTEST|@(KERNEL|LINUX|INITRD|APPEND|FLAVOUR)@' \
    "$GRUB_MENU"; then
    echo "An unresolved live-build boot-menu token remains in the generated GRUB menu." >&2
    exit 1
fi

if [ ! -s "$EFI_GRUB_CONFIG" ]; then
    echo "UEFI GRUB configuration is missing: $EFI_GRUB_CONFIG" >&2
    exit 1
fi
if ! grep -Fq "configfile" "$EFI_GRUB_CONFIG" && ! grep -Fq "Try OminX Aurora" "$EFI_GRUB_CONFIG"; then
    echo "UEFI GRUB is missing its handoff to the shared OminX menu: $EFI_GRUB_CONFIG" >&2
    exit 1
fi

# The current ISO recipe uses GRUB for BIOS and UEFI. If an ISOLINUX loader is
# enabled in a future recipe, require its generated menu to carry the same OminX
# labels rather than silently falling back to an unbranded menu.
if [ -s "$ROOT/binary/isolinux/isolinux.bin" ]; then
    for title in "Try OminX Aurora" "Install OminX (graphical)" "OminX Aurora (safe graphics)"; do
        if ! grep -R -I -Fq "$title" "$ROOT/binary/isolinux"; then
            echo "Generated ISOLINUX menu is missing: $title" >&2
            exit 1
        fi
    done
    if grep -R -I -E -q '(@(LINUX|INITRD|APPEND|FLAVOUR)@|@KERNEL@)' "$ROOT/binary/isolinux"; then
        echo "An unresolved live-build token remains in the generated ISOLINUX files." >&2
        exit 1
    fi
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

if [ ! -s "$ROOT/binary/boot/grub/splash.png" ]; then
    echo "OminX GRUB splash is missing from the binary image." >&2
    exit 1
fi

if ! command -v grub-script-check >/dev/null 2>&1; then
    echo "grub-script-check is required to validate the generated GRUB menu." >&2
    exit 1
fi
grub-script-check "$GRUB_MENU"
grub-script-check "$EFI_GRUB_CONFIG"
printf 'Verified the OminX GRUB BIOS/UEFI menus, graphical/text Debian Installer payloads, and boot splash.\n'
