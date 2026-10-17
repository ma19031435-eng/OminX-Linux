#!/bin/sh
# Fast, dependency-light validation of the checked-in image recipe.
set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$ROOT"

shell_files="auto/config build.sh config/hooks/normal/1000-ominx-finalize.hook.chroot config/includes.chroot/usr/local/bin/ominx-welcome config/includes.chroot/usr/local/bin/ominx-protontricks"
for file in $shell_files; do
    sh -n "$file"
done

python3 - <<'PY'
import ast
import xml.etree.ElementTree as ET
from pathlib import Path

root = Path.cwd()
config_root = root / "config/includes.chroot"

ast.parse((config_root / "usr/lib/ominx/welcome.py").read_text(encoding="utf-8"))
for svg in config_root.rglob("*.svg"):
    ET.parse(svg)

required = {
    "cinnamon-desktop-environment",
    "lightdm",
    "firefox-esr",
    "libreoffice",
    "flatpak",
    "firmware-linux-nonfree",
    "wine32:i386",
    "steam-installer",
    "winetricks",
    "lutris",
    "mesa-vulkan-drivers:i386",
    "gnome-software-plugin-deb",
    "gnome-software-plugin-flatpak",
    "systemd-zram-generator",
    "gamemode",
    "orca",
}
package_list = (root / "config/package-lists/ominx.list.chroot").read_text()
hook = (root / "config/hooks/normal/1000-ominx-finalize.hook.chroot").read_text()
combined = package_list + "\n" + hook
missing = sorted(name for name in required if name not in combined)
if missing:
    raise SystemExit("Missing required image components: " + ", ".join(missing))

release = (config_root / "etc/os-release").read_text()
if 'NAME="OminX"' not in release or 'ID=ominx' not in release or 'ID_LIKE=debian' not in release:
    raise SystemExit("OminX release identity is incomplete")

zram = (config_root / "etc/systemd/zram-generator.conf").read_text()
if "compression-algorithm = zstd" not in zram or "swap-priority = 100" not in zram:
    raise SystemExit("Compressed zram defaults are incomplete")

performance = (config_root / "usr/share/doc/ominx/performance.md").read_text()
if "does **not** freeze, close, hibernate" not in performance or "promise a 50% latency reduction" not in performance:
    raise SystemExit("Performance documentation must explain the limits and non-pausing memory behavior")

lines = []
for line in package_list.splitlines():
    stripped = line.strip()
    if stripped and not stripped.startswith("#"):
        lines.append(stripped)
duplicates = sorted(name for name in set(lines) if lines.count(name) > 1)
if duplicates:
    raise SystemExit("Duplicate package entries: " + ", ".join(duplicates))

print("OminX configuration checks passed.")
PY
