#!/bin/sh
# Fast, dependency-light validation of the checked-in image recipe.
set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$ROOT"

shell_files="auto/config build.sh config/hooks/normal/1000-ominx-finalize.hook.chroot config/includes.chroot/usr/local/bin/ominx-welcome config/includes.chroot/usr/local/bin/ominx-protontricks config/includes.chroot/usr/local/bin/ominx-open-windows"
for file in $shell_files; do
    sh -n "$file"
done

python3 - <<'PY'
import ast
import os
import subprocess
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

root = Path.cwd()
config_root = root / "config/includes.chroot"

ast.parse((config_root / "usr/lib/ominx/welcome.py").read_text(encoding="utf-8"))
for svg in config_root.rglob("*.svg"):
    ET.parse(svg)

required = {
    "cinnamon-desktop-environment",
    "desktop-file-utils",
    "shared-mime-info",
    "lightdm",
    "firefox-esr",
    "libreoffice",
    "flatpak",
    "firmware-linux-nonfree",
    "wine",
    "wine64",
    "wine32:i386",
    "wine-binfmt",
    "steam-installer",
    "winetricks",
    "lutris",
    "zenity",
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

applications = config_root / "usr/share/applications"
handler_entry = applications / "ominx-windows-app.desktop"
mime_defaults = applications / "mimeapps.list"
handler_text = handler_entry.read_text(encoding="utf-8")
mime_defaults_text = mime_defaults.read_text(encoding="utf-8")
registered_mimes = {
    "application/x-msdos-program",
    "application/x-ms-dos-executable",
    "application/x-msdos-executable",
    "application/vnd.microsoft.portable-executable",
    "application/x-msdownload",
    "application/x-msi",
}
if "Exec=/usr/local/bin/ominx-open-windows %f" not in handler_text:
    raise SystemExit("Windows app desktop entry must pass clicked files to the OminX launcher")
if not registered_mimes.issubset(set(handler_text.split("MimeType=", 1)[-1].splitlines()[0].rstrip(";").split(";"))):
    raise SystemExit("Windows app desktop entry is missing one or more Windows executable MIME types")
default_section = mime_defaults_text.split("[Default Applications]", 1)
if len(default_section) != 2:
    raise SystemExit("System-wide Windows app defaults are missing")
default_section = default_section[1].split("[", 1)[0]
for mime in registered_mimes:
    association = f"{mime}=ominx-windows-app.desktop;"
    if association not in default_section:
        raise SystemExit(f"No system default OminX Windows app handler is configured for {mime}")

skeleton_mime_defaults = (config_root / "etc/skel/.config/mimeapps.list").read_text(encoding="utf-8")
for mime in registered_mimes:
    if f"{mime}=ominx-windows-app.desktop;" not in skeleton_mime_defaults:
        raise SystemExit(f"New users will not get the OminX Windows app default for {mime}")
if "desktop-file-validate /usr/share/applications/ominx-windows-app.desktop" not in hook:
    raise SystemExit("The image hook must validate the OminX Windows app desktop entry")
if "update-desktop-database --quiet /usr/share/applications" not in hook:
    raise SystemExit("The image hook must refresh desktop application MIME registrations")

# Exercise the actual launcher with a mock Wine command. This checks that
# double-click paths containing spaces remain a single argument and that
# installer files are launched from their own directory.
launcher = config_root / "usr/local/bin/ominx-open-windows"
if not os.access(launcher, os.X_OK):
    raise SystemExit("OminX Windows app launcher must be executable")
with tempfile.TemporaryDirectory(prefix="ominx-wine-test-") as temporary:
    test_root = Path(temporary)
    mock_bin = test_root / "bin"
    mock_bin.mkdir()
    wine_log = test_root / "wine-arguments"
    mock_wine = mock_bin / "wine"
    mock_wine.write_text(
        "#!/bin/sh\n"
        "printf '%s\\n' \"$PWD\" \"$@\" > \"$OMINX_WINE_TEST_LOG\"\n",
        encoding="utf-8",
    )
    mock_wine.chmod(0o755)
    test_env = os.environ.copy()
    test_env["PATH"] = f"{mock_bin}:{test_env.get('PATH', '')}"
    test_env["OMINX_WINE_TEST_LOG"] = str(wine_log)

    def exercise_launch(filename, expected_command):
        target_directory = test_root / "folder with spaces"
        target_directory.mkdir(exist_ok=True)
        target = target_directory / filename
        target.write_bytes(b"test fixture")
        wine_log.unlink(missing_ok=True)
        result = subprocess.run(
            [str(launcher), str(target)],
            env=test_env,
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            raise SystemExit(f"Windows app launcher failed for {filename}: {result.stderr.strip()}")
        actual = wine_log.read_text(encoding="utf-8").splitlines()
        expected = [str(target_directory.resolve()), *expected_command(str(target.resolve()))]
        if actual != expected:
            raise SystemExit(f"Windows app launcher passed incorrect arguments for {filename}: {actual!r}")

    exercise_launch("setup with spaces $value.EXE", lambda path: [path])
    exercise_launch("product installer.msi", lambda path: ["msiexec", "/i", path])

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
