#!/bin/sh
# Build the OminX installable live ISO. Run on a Debian-compatible amd64 host.
set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$ROOT"

if [ "$(id -u)" -ne 0 ]; then
    if command -v sudo >/dev/null 2>&1; then
        exec sudo -- "$0" "$@"
    fi
    echo "build.sh needs root (install sudo or run it as root)." >&2
    exit 1
fi

if ! command -v python3 >/dev/null 2>&1; then
    echo "Python 3 is required to generate the original OminX boot splash; install python3 and try again." >&2
    exit 1
fi

if ! command -v lb >/dev/null 2>&1; then
    cat >&2 <<'EOF'
Debian live-build is not installed. On Debian 13, install the build tools with:
  apt-get update
  apt-get install live-build debootstrap xorriso squashfs-tools dosfstools mtools \
    grub-pc-bin grub-efi-amd64-bin isolinux syslinux-common syslinux-utils \
    debian-archive-keyring
Then run ./build.sh again.
EOF
    exit 1
fi

python3 scripts/generate-boot-splash.py
./auto/config "$@"
lb build
scripts/verify-boot-menu.sh

ISO="$ROOT/live-image-amd64.hybrid.iso"
if [ -f "$ISO" ]; then
    (cd "$ROOT" && sha256sum "$(basename "$ISO")" > SHA256SUMS)
    printf '\nBuilt %s\n' "$ISO"
    printf 'Checksum: %s/SHA256SUMS\n' "$ROOT"
else
    echo "Build completed, but the expected ISO was not found at $ISO." >&2
    exit 1
fi
