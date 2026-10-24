#!/bin/sh
# Fast, dependency-light validation of the checked-in image recipe.
set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$ROOT"

shell_files="auto/config build.sh scripts/build-debian-legacy.sh scripts/verify-boot-menu.sh config/hooks/normal/1000-ominx-finalize.hook.chroot config/includes.chroot/usr/local/bin/ominx-welcome config/includes.chroot/usr/local/bin/ominx-protontricks config/includes.chroot/usr/local/bin/ominx-open-windows config/includes.chroot/usr/local/bin/ominx-wine-firstboot config/includes.chroot/usr/local/bin/ominx-store config/includes.chroot/usr/local/bin/ominx-settings config/includes.chroot/usr/local/bin/ominx-setup"
for file in $shell_files; do
    sh -n "$file"
done

python3 - <<'PY'
import ast
import configparser
import json
import os
import shutil
import struct
import subprocess
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

root = Path.cwd()
config_root = root / "config/includes.chroot"
package_list_path = root / "config/package-lists/ominx.list.chroot"
package_list = package_list_path.read_text(encoding="utf-8")
hook_path = root / "config/hooks/normal/1000-ominx-finalize.hook.chroot"
hook = hook_path.read_text(encoding="utf-8")
build_script = (root / "scripts/build-debian-legacy.sh").read_text(encoding="utf-8")
build_workflow = (root / ".github/workflows/build-iso.yml").read_text(encoding="utf-8")

for marker in ("build-info.txt", "${GITHUB_SHA}", "${GITHUB_RUN_ID}", "date -u"):
    if marker not in build_workflow:
        raise SystemExit(f"ISO build provenance stamp is missing {marker}")
if "python3 live-build" not in build_workflow:
    raise SystemExit("The ISO build container must install Python 3 for splash generation")
if "scripts/verify-boot-menu.sh" not in build_script:
    raise SystemExit("The ISO build must verify generated boot menus before reporting success")

for python_app in ("welcome.py", "store.py", "settings.py", "setup.py", "ui.py"):
    ast.parse((config_root / "usr/lib/ominx" / python_app).read_text(encoding="utf-8"))
for python_script in ("smoke-gtk-apps.py", "generate-boot-splash.py"):
    ast.parse((root / "scripts" / python_script).read_text(encoding="utf-8"))
for svg in config_root.rglob("*.svg"):
    ET.parse(svg)

# The package list is the single source of truth for the primary desktop.
packages = [
    line.strip()
    for line in package_list.splitlines()
    if line.strip() and not line.lstrip().startswith("#")
]
duplicates = sorted(name for name in set(packages) if packages.count(name) > 1)
if duplicates:
    raise SystemExit("Duplicate package entries: " + ", ".join(duplicates))
required_packages = {
    "plasma-desktop",
    "plasma-workspace",
    "kwin-x11",
    "xserver-xorg",
    "lightdm",
    "dolphin",
    "kio-extras",
    "systemsettings",
    "kinfocenter",
    "plasma-systemmonitor",
    "plasma-nm",
    "plasma-pa",
    "bluedevil",
    "breeze",
    "breeze-gtk-theme",
    "breeze-icon-theme",
    "breeze-cursor-theme",
    "plasma-discover",
    "plasma-discover-backend-flatpak",
    "flatpak",
    "firefox-esr",
    "libreoffice",
    "gamemode",
    "systemd-zram-generator",
    "python3-gi",
    "gir1.2-gtk-3.0",
}
missing_packages = sorted(required_packages - set(packages))
if missing_packages:
    raise SystemExit("Missing required OminX packages: " + ", ".join(missing_packages))
for legacy in ("cinnamon-desktop-environment", "gnome-software", "gnome-software-plugin", "nemo"):
    if legacy in package_list.lower():
        raise SystemExit(f"The Plasma package selection still includes the legacy desktop component {legacy}")
for required_hook_package in (
    "steam-installer",
    "steam-devices",
    "wine64",
    "wine32:i386",
    "winetricks",
    "lutris",
    "mesa-vulkan-drivers:i386",
    "libvulkan1:i386",
    "libasound2-plugins:i386",
):
    if required_hook_package not in hook:
        raise SystemExit(f"The image hook is missing gaming/performance support: {required_hook_package}")

# Verify LightDM still starts the Plasma X11 session and that first-login
# configuration selects the original OminX theme rather than Cinnamon/GNOME.
lightdm_session = (config_root / "etc/lightdm/lightdm.conf.d/50-ominx.conf").read_text(encoding="utf-8")
if "user-session=plasmax11" not in lightdm_session:
    raise SystemExit("LightDM must start the Plasma X11 session")
if (config_root / "etc/dconf/db/local.d/00-ominx").exists():
    raise SystemExit("Legacy Cinnamon dconf defaults must not be included in the Plasma image")
if (config_root / "usr/share/cinnamon").exists() or (config_root / "usr/share/themes/OminX/cinnamon").exists():
    raise SystemExit("Legacy Cinnamon shell assets must not be included in the Plasma image")

# Plasma theme package, panel, color palette, and KDE system defaults.
look_and_feel = config_root / "usr/share/plasma/look-and-feel/com.ominx.aurora"
metadata = json.loads((look_and_feel / "metadata.json").read_text(encoding="utf-8"))
if metadata.get("KPackageStructure") != "Plasma/LookAndFeel":
    raise SystemExit("OminX Aurora is not a Plasma Look-and-Feel package")
if metadata.get("KPlugin", {}).get("Id") != "com.ominx.aurora":
    raise SystemExit("OminX Aurora has the wrong Plasma Look-and-Feel ID")
layout_path = look_and_feel / "contents/layouts/org.kde.plasma.desktop-layout.js"
layout = layout_path.read_text(encoding="utf-8")
for setting in (
    'panel.location = "bottom"',
    'panel.alignment = "center"',
    'panel.lengthMode = "custom"',
    "panel.height = 46",
    "panel.floating = true",
    'panel.opacity = "translucent"',
    "ominx-wallpaper.svg",
):
    if setting not in layout:
        raise SystemExit(f"OminX Plasma panel layout is missing {setting}")
for widget in (
    "org.kde.plasma.kickoff",
    "org.kde.plasma.pager",
    "org.kde.plasma.icontasks",
    "org.kde.plasma.systemtray",
    "org.kde.plasma.digitalclock",
    "org.kde.plasma.showdesktop",
):
    if widget not in layout:
        raise SystemExit(f"OminX Plasma panel is missing {widget}")
for favorite in (
    "org.kde.dolphin.desktop",
    "firefox-esr.desktop",
    "ominx-store.desktop",
    "ominx-settings.desktop",
    "libreoffice-writer.desktop",
    "steam.desktop",
):
    if favorite not in layout:
        raise SystemExit(f"OminX Plasma launcher/task manager is missing {favorite}")
if 'launcher.writeConfig("icon", "ominx-start")' not in layout:
    raise SystemExit("The Plasma launcher must use the original OminX icon")
if shutil.which("node"):
    subprocess.run(["node", "--check", str(layout_path)], check=True)

plasma_theme = config_root / "usr/share/plasma/desktoptheme/ominx-aurora"
theme_metadata = (plasma_theme / "metadata.desktop").read_text(encoding="utf-8")
if "X-KDE-PluginInfo-Name=ominx-aurora" not in theme_metadata or "OminX Aurora" not in theme_metadata:
    raise SystemExit("The Plasma desktop theme metadata is incomplete")
for filename, required_ids in (
    ("widgets/panel-background.svg", ("topleft", "top", "topright", "left", "center", "right", "bottomleft", "bottom", "bottomright", "hint-stretch-borders")),
    ("widgets/tooltip.svg", ("center", "hint-left-margin", "hint-right-margin", "hint-top-margin", "hint-bottom-margin")),
    ("widgets/background.svg", ("center", "hint-left-margin", "hint-right-margin", "hint-top-margin", "hint-bottom-margin")),
):
    tree = ET.parse(plasma_theme / filename)
    ids = {element.attrib.get("id") for element in tree.iter()}
    missing_ids = sorted(set(required_ids) - ids)
    if missing_ids:
        raise SystemExit(f"OminX Plasma theme asset {filename} is missing: {', '.join(missing_ids)}")

color_path = config_root / "usr/share/color-schemes/OminX-Aurora.colors"
colors = configparser.ConfigParser(interpolation=None, strict=True)
with color_path.open(encoding="utf-8") as source:
    colors.read_file(source)
for section in ("General", "Colors:Button", "Colors:Selection", "Colors:View", "Colors:Window", "WM"):
    if not colors.has_section(section):
        raise SystemExit(f"OminX Aurora color scheme is missing [{section}]")
for section in colors.sections():
    for key, value in colors.items(section):
        if key.startswith(("background", "foreground", "decoration", "active", "inactive")):
            channels = value.split(",")
            if len(channels) != 3 or any(not channel.strip().isdigit() or not 0 <= int(channel) <= 255 for channel in channels):
                raise SystemExit(f"Invalid RGB color for [{section}] {key}: {value}")

kdeglobals = (config_root / "etc/xdg/kdeglobals").read_text(encoding="utf-8")
plasmarc = (config_root / "etc/xdg/plasmarc").read_text(encoding="utf-8")
kwinrc = (config_root / "etc/xdg/kwinrc").read_text(encoding="utf-8")
if "LookAndFeelPackage=com.ominx.aurora" not in kdeglobals or "ColorScheme=OminX-Aurora" not in kdeglobals:
    raise SystemExit("New Plasma sessions must select the OminX Look-and-Feel and color scheme")
if "Theme=breeze-dark" not in kdeglobals or "widgetStyle=Breeze" not in kdeglobals:
    raise SystemExit("The KDE UI must use the intended dark icon and Breeze widget themes")
if "name=ominx-aurora" not in plasmarc or "blurEnabled=true" not in kwinrc:
    raise SystemExit("KWin/Plasma defaults are missing the OminX theme or floating-panel blur")

# Dolphin replaces Nemo, retaining a readable, folder-first list view.
dolphinrc = (config_root / "etc/xdg/dolphinrc").read_text(encoding="utf-8")
dolphin_view = (config_root / "etc/skel/.local/share/dolphin/view_properties/global/.directory").read_text(encoding="utf-8")
for setting in ("EditableUrl=false", "ShowStatusBar=1", "GlobalViewProps=true"):
    if setting not in dolphinrc:
        raise SystemExit(f"Dolphin defaults are missing {setting}")
for setting in ("ViewMode=1", "SortRole=text", "SortFoldersFirst=true"):
    if setting not in dolphin_view:
        raise SystemExit(f"Dolphin default folder view is missing {setting}")

# Keep the OminX GTK apps cohesive inside the Plasma session and greeter.
ui_css = (config_root / "usr/share/ominx/ui/ominx-ui.css").read_text(encoding="utf-8")
if ui_css.count("{") != ui_css.count("}"):
    raise SystemExit("OminX Store and Settings stylesheet has unbalanced braces")
for selector in (".ominx-sidebar", ".ominx-hero", ".ominx-card", ".ominx-primary", ".ominx-setup-page", ".ominx-setup-footer"):
    if selector not in ui_css:
        raise SystemExit(f"OminX app hub styling is missing {selector}")
if "selection-background-color" in ui_css:
    raise SystemExit("OminX app hub CSS must use GTK3 CSS properties")
gtk_css = (config_root / "usr/share/themes/OminX/gtk-3.0/gtk.css").read_text(encoding="utf-8")
theme_index = (config_root / "usr/share/themes/OminX/index.theme").read_text(encoding="utf-8")
if "GtkTheme=OminX" not in theme_index or gtk_css.count("{") != gtk_css.count("}") or "Adwaita/gtk-contained-dark.css" not in gtk_css:
    raise SystemExit("The original OminX GTK3 theme must be registered and extend the installed dark base")
skeleton_gtk = (config_root / "etc/skel/.config/gtk-3.0/settings.ini").read_text(encoding="utf-8")
if "gtk-theme-name=OminX" not in skeleton_gtk or "gtk-application-prefer-dark-theme=1" not in skeleton_gtk:
    raise SystemExit("New users must receive OminX dark GTK defaults")
lightdm_greeter = (config_root / "etc/lightdm/lightdm-gtk-greeter.conf").read_text(encoding="utf-8")
if "theme-name=OminX" not in lightdm_greeter or "ominx-wallpaper.svg" not in lightdm_greeter:
    raise SystemExit("The login screen must use OminX branding and its original wallpaper")
wallpaper = config_root / "usr/share/backgrounds/ominx/ominx-wallpaper.svg"
wallpaper_text = wallpaper.read_text(encoding="utf-8")
if "OMINX" not in wallpaper_text or "<feGaussianBlur" in wallpaper_text:
    raise SystemExit("The original OminX wallpaper must be branded and lightweight")

# The Store delegates actual package/Flatpak actions to Discover; it does not
# simulate installation. Discover's native launcher is hidden from the menu.
applications = config_root / "usr/share/applications"
store_entry = applications / "ominx-store.desktop"
settings_entry = applications / "ominx-settings.desktop"
setup_entry = applications / "ominx-setup.desktop"
handler_entry = applications / "ominx-windows-app.desktop"
store_text = store_entry.read_text(encoding="utf-8")
settings_text = settings_entry.read_text(encoding="utf-8")
setup_text = setup_entry.read_text(encoding="utf-8")
handler_text = handler_entry.read_text(encoding="utf-8")
for text, app_name, executable, icon in (
    (store_text, "OminX Store", "/usr/local/bin/ominx-store", "ominx-store.svg"),
    (settings_text, "OminX Settings", "/usr/local/bin/ominx-settings", "ominx-settings.svg"),
):
    if app_name not in text or f"TryExec={executable}" not in text or f"Exec={executable}" not in text or icon not in text:
        raise SystemExit(f"{app_name} must have a verifiable launcher and original icon")
if "Exec=/usr/local/bin/ominx-setup" not in setup_text:
    raise SystemExit("OminX Setup must be available from the desktop applications menu")
for launcher in ("ominx-store", "ominx-settings", "ominx-setup"):
    if not os.access(config_root / "usr/local/bin" / launcher, os.X_OK):
        raise SystemExit(f"{launcher} must be executable")

store_source = (config_root / "usr/lib/ominx/store.py").read_text(encoding="utf-8")
settings_source = (config_root / "usr/lib/ominx/settings.py").read_text(encoding="utf-8")
ui_source = (config_root / "usr/lib/ominx/ui.py").read_text(encoding="utf-8")
welcome_source = (config_root / "usr/lib/ominx/welcome.py").read_text(encoding="utf-8")
setup_source = (config_root / "usr/lib/ominx/setup.py").read_text(encoding="utf-8")
if "shutil.which(\"plasma-discover\")" not in store_source or 'command.extend(("--search", search))' not in store_source:
    raise SystemExit("OminX Store must route full-catalog searches to KDE Discover")
for discover_mode in ('"Installed"', '"Update"', '"Sources"'):
    if discover_mode not in store_source:
        raise SystemExit(f"OminX Store is missing the Discover {discover_mode} action")
if "_desktop_app_info(product[\"desktop_id\"])" not in store_source or "except TypeError:" not in store_source:
    raise SystemExit("OminX Store must tolerate catalog apps whose desktop entries are not installed")
if "systemsettings" not in settings_source or "plasma-discover" not in settings_source:
    raise SystemExit("OminX Settings must use Plasma System Settings and Discover")
if any(token in settings_source.lower() + setup_source.lower() for token in ("cinnamon-settings", "gnome-software", "nm-connection-editor")):
    raise SystemExit("OminX Settings and Setup must not depend on retired Cinnamon/GNOME utilities")
if "systemsettings" not in setup_source or "plasma-discover" not in setup_source:
    raise SystemExit("OminX Setup must link to the Plasma network and updates controls")
if "KDE Plasma" not in welcome_source or "ominx launcher" not in welcome_source.lower():
    raise SystemExit("OminX Welcome must explain the Plasma desktop and original Launcher")
for source in (store_source, settings_source):
    if ".set_group(" in source:
        raise SystemExit("GTK3 navigation must not call the unsupported ToggleButton.set_group() API")
    if "GLib.timeout_add(" not in source or "def _cancel_search_refresh" not in source:
        raise SystemExit("OminX Store and Settings search must debounce input and cancel stale refreshes")
    if "set_default_window_size" not in source:
        raise SystemExit("OminX app hubs must use the shared screen-aware opening size")
    if "self.maximize()" in source:
        raise SystemExit("OminX app hubs must not force a second maximize-and-resize pass at startup")
if "Gdk.Screen.get_default()" not in ui_source or "screen.get_width()" not in ui_source or "screen.get_height()" not in ui_source:
    raise SystemExit("OminX window sizing must adapt to the available display size")
if "from gi.repository import Gio, GLib, Gtk" not in setup_source or "except (GLib.Error, TypeError)" not in setup_source:
    raise SystemExit("OminX Setup must handle an unavailable Firefox desktop entry")
for step in ("welcome", "network", "software", "gaming", "finish"):
    if f'("{step}",' not in setup_source:
        raise SystemExit(f"OminX Setup is missing its {step} step")
setup_autostart = config_root / "etc/skel/.config/autostart/ominx-setup.desktop"
if "Exec=ominx-setup --first-run" not in setup_autostart.read_text(encoding="utf-8"):
    raise SystemExit("New users must be offered the OminX first-run setup wizard")
if "ominx-setup" not in welcome_source:
    raise SystemExit("OminX Welcome must provide a way to reopen the setup wizard")

# Verify generated package metadata and MIME associations, including Windows
# app handling, without claiming universal compatibility.
for file in (
    applications / "mimeapps.list",
    config_root / "etc/skel/.config/mimeapps.list",
):
    text = file.read_text(encoding="utf-8")
    if "inode/directory=org.kde.dolphin.desktop;" not in text:
        raise SystemExit(f"Dolphin must be the default file manager in {file}")
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
handler_mimes = set(handler_text.split("MimeType=", 1)[-1].splitlines()[0].rstrip(";").split(";"))
if not registered_mimes.issubset(handler_mimes):
    raise SystemExit("Windows app desktop entry is missing one or more Windows executable MIME types")
for mimeapps in (applications / "mimeapps.list", config_root / "etc/skel/.config/mimeapps.list"):
    contents = mimeapps.read_text(encoding="utf-8")
    sections = contents.split("[Default Applications]", 1)
    if len(sections) != 2:
        raise SystemExit(f"Default application list is missing in {mimeapps}")
    defaults = sections[1].split("[", 1)[0]
    for mime in registered_mimes:
        if f"{mime}=ominx-windows-app.desktop;" not in defaults:
            raise SystemExit(f"No OminX Windows app handler is configured for {mime} in {mimeapps}")

# The chroot hook must validate the real Plasma session and app entries and
# create a hidden native Discover launcher for OminX Store.
for executable in (
    "/usr/local/bin/ominx-store",
    "/usr/local/bin/ominx-settings",
    "/usr/local/bin/ominx-setup",
    "/usr/bin/plasma-discover",
    "/usr/bin/plasmashell",
    "/usr/bin/systemsettings",
):
    if executable not in hook:
        raise SystemExit(f"The image hook must validate {executable}")
for marker in (
    "/usr/share/xsessions/plasmax11.desktop",
    "/usr/share/applications/org.kde.dolphin.desktop",
    "/usr/local/share/applications/org.kde.discover.desktop",
    "desktop-file-edit --set-key=NoDisplay --set-value=true",
    "LookAndFeelPackage=com.ominx.aurora",
    "configparser.ConfigParser(interpolation=None, strict=True)",
    "https://dl.flathub.org/repo/flathub.flatpakrepo",
):
    if marker not in hook:
        raise SystemExit(f"The image finalizer is missing {marker}")
for desktop_id in (
    "ominx-store.desktop",
    "ominx-settings.desktop",
    "ominx-setup.desktop",
    "ominx-windows-app.desktop",
):
    if f"/usr/share/applications/{desktop_id}" not in hook:
        raise SystemExit(f"The image hook must validate {desktop_id}")
if "update-desktop-database --quiet /usr/share/applications" not in hook or "desktop-file-validate" not in hook:
    raise SystemExit("The image hook must validate desktop entries and refresh MIME registrations")

# Check first-run guidance and app UI without relying on a specific shell theme.
smoke_source = (root / "scripts/smoke-gtk-apps.py").read_text(encoding="utf-8")
if "wait_ms=140" not in smoke_source or "floating panel" not in smoke_source:
    raise SystemExit("GTK smoke tests must cover the debounced search and OminX Plasma guidance")
if not any("set_default_window_size" in source for source in (welcome_source, setup_source)):
    raise SystemExit("OminX Welcome and Setup must use the shared screen-aware opening size")

# Preserve the original Windows-app helper behavior; a path with spaces must
# remain one argument and MSI files are handed to Wine's installer frontend.
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

    # First-sign-in background preparation must create the prefix once,
    # record the exact Wine version, and leave later runs as a no-op.
    firstboot = config_root / "usr/local/bin/ominx-wine-firstboot"
    if not os.access(firstboot, os.X_OK):
        raise SystemExit("ominx-wine-firstboot must be executable")
    service = (config_root / "usr/lib/systemd/user/ominx-wine-firstboot.service").read_text(encoding="utf-8")
    if "ExecStart=/usr/local/bin/ominx-wine-firstboot" not in service or "ConditionPathExists=" not in service:
        raise SystemExit("The Wine first-boot user service is incomplete")
    if "systemctl --global enable ominx-wine-firstboot.service" not in hook:
        raise SystemExit("The image hook must enable Wine first-boot preparation for all users")
    gaming_sysctl = (config_root / "etc/sysctl.d/91-ominx-gaming.conf").read_text(encoding="utf-8")
    if "vm.max_map_count = 1048576" not in gaming_sysctl:
        raise SystemExit("Proton requires the raised vm.max_map_count default")
    boot_calls = test_root / "wineboot-calls"
    for mock_name, body in (
        ("wineboot", "mkdir -p \"$WINEPREFIX/drive_c\"\nprintf 'booted\\n' >> \"$OMINX_WINE_TEST_BOOTLOG\"\n"),
        ("wineserver", "exit 0\n"),
        ("wine", "if [ \"$1\" = --version ]; then echo wine-10.0-test; fi\n"),
    ):
        mock_tool = mock_bin / mock_name
        mock_tool.write_text("#!/bin/sh\n" + body, encoding="utf-8")
        mock_tool.chmod(0o755)
    first_env = test_env.copy()
    first_env["HOME"] = str(test_root / "home")
    first_env["XDG_RUNTIME_DIR"] = str(test_root / "run")
    first_env["OMINX_WINE_TEST_BOOTLOG"] = str(boot_calls)
    (test_root / "home").mkdir()
    (test_root / "run").mkdir()
    for attempt in range(2):
        prepared = subprocess.run([str(firstboot), "--wait"], env=first_env,
                                  capture_output=True, text=True, check=False)
        if prepared.returncode != 0:
            raise SystemExit(f"Wine first-boot setup failed: {prepared.stderr.strip()}")
    marker = test_root / "home/.local/share/ominx/wine-setup-v1"
    if marker.read_text(encoding="utf-8").strip() != "wine-10.0-test":
        raise SystemExit("Wine first-boot setup did not record the prepared runtime")
    if boot_calls.read_text(encoding="utf-8").splitlines() != ["booted"]:
        raise SystemExit("Wine prefix preparation must run exactly once")

# Check repository-specific boot menu, installer, splash, provenance, and
# conservative performance expectations.
boot_grub = (root / "config/bootloaders/grub-pc/grub.cfg").read_text(encoding="utf-8")
boot_syslinux = (root / "config/bootloaders/isolinux/live.cfg.in").read_text(encoding="utf-8")
boot_isolinux_cfg = (root / "config/bootloaders/isolinux/isolinux.cfg").read_text(encoding="utf-8")
for boot_marker in ("Try OminX Aurora", "Install OminX", "KERNEL_LIVE", "APPEND_LIVE", "KERNEL_GI", "APPEND_GI"):
    if boot_marker not in boot_grub:
        raise SystemExit(f"OminX GRUB menu is missing {boot_marker}")
for boot_marker in ("Try OminX Aurora", "Install OminX", "@LINUX@", "@INITRD@", "@APPEND_INSTALL@"):
    if boot_marker not in boot_syslinux:
        raise SystemExit(f"OminX ISOLINUX menu is missing {boot_marker}")
if "include menu.cfg" not in boot_isolinux_cfg or "timeout 80" not in boot_isolinux_cfg:
    raise SystemExit("OminX ISOLINUX configuration must load its menu with a short timeout")
boot_verifier = (root / "scripts/verify-boot-menu.sh").read_text(encoding="utf-8")
for marker in ("grub-script-check", "binary/boot/grub/grub.cfg", "binary/install/gtk/vmlinuz", "binary/install/vmlinuz", "Try OminX Aurora"):
    if marker not in boot_verifier:
        raise SystemExit(f"Fresh ISO boot-menu verification is missing {marker}")
for splash, expected_size in (
    (root / "config/bootloaders/grub-pc/splash.png", (1280, 720)),
    (root / "config/bootloaders/isolinux/splash.png", (640, 480)),
    (root / "config/includes.binary/boot/grub/splash.png", (1280, 720)),
    (root / "config/includes.binary/isolinux/splash.png", (640, 480)),
):
    image = splash.read_bytes()
    if image[:8] != bytes((137, 80, 78, 71, 13, 10, 26, 10)) or struct.unpack(">II", image[16:24]) != expected_size:
        raise SystemExit(f"Invalid OminX boot splash image: {splash}")
for source, included in (
    (root / "config/bootloaders/grub-pc/splash.png", root / "config/includes.binary/boot/grub/splash.png"),
    (root / "config/bootloaders/isolinux/splash.png", root / "config/includes.binary/isolinux/splash.png"),
):
    if source.read_bytes() != included.read_bytes():
        raise SystemExit(f"Bootloader and ISO-included splash assets differ: {source}")

release = (config_root / "etc/os-release").read_text(encoding="utf-8")
if 'NAME="OminX"' not in release or "ID=ominx" not in release or "ID_LIKE=debian" not in release:
    raise SystemExit("OminX release identity is incomplete")
zram = (config_root / "etc/systemd/zram-generator.conf").read_text(encoding="utf-8")
if "compression-algorithm = zstd" not in zram or "swap-priority = 100" not in zram:
    raise SystemExit("Compressed zram defaults are incomplete")
performance = (config_root / "usr/share/doc/ominx/performance.md").read_text(encoding="utf-8")
if "does **not** freeze, close, hibernate" not in performance or "promise a 50% latency reduction" not in performance:
    raise SystemExit("Performance documentation must explain the limits and non-pausing memory behavior")

print("OminX Plasma configuration checks passed.")
PY
