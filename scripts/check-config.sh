#!/bin/sh
# Fast, dependency-light validation of the checked-in image recipe.
set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$ROOT"

shell_files="auto/config build.sh config/hooks/normal/1000-ominx-finalize.hook.chroot config/includes.chroot/usr/local/bin/ominx-welcome config/includes.chroot/usr/local/bin/ominx-protontricks config/includes.chroot/usr/local/bin/ominx-open-windows config/includes.chroot/usr/local/bin/ominx-store config/includes.chroot/usr/local/bin/ominx-settings"
for file in $shell_files; do
    sh -n "$file"
done

python3 - <<'PY'
import ast
import json
import os
import subprocess
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

root = Path.cwd()
config_root = root / "config/includes.chroot"
build_workflow = (root / ".github/workflows/build-iso.yml").read_text(encoding="utf-8")
for marker in ("build-info.txt", "${GITHUB_SHA}", "${GITHUB_RUN_ID}", "date -u"):
    if marker not in build_workflow:
        raise SystemExit(f"ISO build provenance stamp is missing {marker}")

for python_app in ("welcome.py", "store.py", "settings.py", "ui.py"):
    ast.parse((config_root / "usr/lib/ominx" / python_app).read_text(encoding="utf-8"))
ast.parse((root / "scripts/smoke-gtk-apps.py").read_text(encoding="utf-8"))
for svg in config_root.rglob("*.svg"):
    ET.parse(svg)

shell_defaults = (config_root / "etc/dconf/db/local.d/00-ominx").read_text(encoding="utf-8")
for required_setting in (
    "[org/cinnamon/theme]",
    "name='OminX'",
    "gtk-theme='OminX'",
    "panels-enabled=['1:0:top']",
    "panels-height=['1:44']",
    "panel1:left:0:ominx-start@ominx:0",
    "panel1:left:1:expo@cinnamon.org:14",
    "panel1:center:0:grouped-window-list@cinnamon.org:1",
    "favorite-apps=['nemo.desktop', 'firefox-esr.desktop', 'ominx-store.desktop', 'libreoffice-writer.desktop', 'ominx-settings.desktop']",
    "button-layout=':minimize,maximize,close'",
    "command='ominx-settings'",
    "home-icon-visible=true",
    "computer-icon-visible=true",
    "[org/nemo/preferences]",
    "always-use-browser=true",
    "click-policy='double'",
    "default-folder-viewer='list-view'",
    "sort-directories-first=true",
    "show-location-entry=false",
    "show-directory-item-counts='local-only'",
    "show-new-folder-icon-toolbar=true",
    "[org/nemo/window-state]",
    "start-with-sidebar=true",
    "start-with-status-bar=true",
    "start-with-menu-bar=false",
    "side-pane-view='places'",
    "custom-list=['custom0', 'custom1', 'custom2']",
    "[org/cinnamon/desktop/keybindings/custom-keybindings/custom0]",
    "binding=['<Super>e']",
    "command='gnome-system-monitor'",
    "binding=['<Control><Shift>Escape']",
    "panel-run-dialog=['<Alt>F2', '<Super>r']",
    "push-tile-left=['<Super>Left']",
    "area-screenshot=['<Shift>Print', '<Super><Shift>s']",
    "tile-maximize=true",
):
    if required_setting not in shell_defaults:
        raise SystemExit(f"OminX desktop defaults are incomplete: {required_setting}")

start_applet = config_root / "usr/share/cinnamon/applets/ominx-start@ominx"
start_metadata = json.loads((start_applet / "metadata.json").read_text(encoding="utf-8"))
if start_metadata.get("uuid") != "ominx-start@ominx":
    raise SystemExit("OminX Start applet metadata has the wrong UUID")
start_source = (start_applet / "applet.js").read_text(encoding="utf-8")
for behavior in (
    "Gio.AppInfo.get_all()",
    "_onSearchChanged",
    "_toggleAppView",
    "Power options",
    "OminX Store",
    "Super_L",
    "SEARCH_DEBOUNCE_MS = 80",
    "RESULTS_PER_PAGE = 32",
    "this.allApps = null",
    "searchText:",
    "Gio.AppInfoMonitor.get()",
    "Preparing your app list…",
    "_appendMoreResultsButton",
):
    if behavior not in start_source:
        raise SystemExit(f"OminX Launcher is missing {behavior}")
constructor_body = start_source.split("constructor(", 1)[1].split("\n    _buildMenu()", 1)[0]
if "_getAllApps()" in constructor_body:
    raise SystemExit("OminX Start must not scan every installed app during Cinnamon startup")
start_css = (start_applet / "stylesheet.css").read_text(encoding="utf-8")
if start_css.count("{") != start_css.count("}"):
    raise SystemExit("OminX Launcher stylesheet has unbalanced braces")
for selector in (".ominx-start-root", ".ominx-start-search", ".ominx-start-grid", ".ominx-start-recommendations", ".ominx-start-more-button"):
    if selector not in start_css:
        raise SystemExit(f"OminX Launcher styling is missing {selector}")

enabled_applets = next(line for line in shell_defaults.splitlines() if line.startswith("enabled-applets="))
if "panel1:left:0:ominx-start@ominx:0" not in enabled_applets:
    raise SystemExit("The top command bar must use the OminX Launcher applet")

menu_defaults = json.loads(
    (config_root / "usr/share/cinnamon/applets/menu@cinnamon.org/settings-override.json").read_text(encoding="utf-8")
)
if not menu_defaults["menu-custom"]["default"] or menu_defaults["menu-label"]["default"] != "":
    raise SystemExit("The Launcher button must use the custom icon without a text label")
if not menu_defaults["menu-icon"]["default"].endswith("ominx-start.svg"):
    raise SystemExit("The OminX Launcher icon is not configured")
if not menu_defaults["show-favorites"]["default"] or menu_defaults["show-recents"]["default"]:
    raise SystemExit("The Launcher must surface favorite apps instead of recents")

window_list_defaults = json.loads(
    (config_root / "usr/share/cinnamon/applets/grouped-window-list@cinnamon.org/settings-override.json").read_text(encoding="utf-8")
)
expected_pins = [
    "nemo.desktop",
    "firefox-esr.desktop",
    "ominx-store.desktop",
    "libreoffice-writer.desktop",
]
if window_list_defaults["pinned-apps"]["default"] != expected_pins:
    raise SystemExit("The command bar's pinned apps are missing or out of order")
for app_id in expected_pins:
    if f"'{app_id}'" not in shell_defaults:
        raise SystemExit(f"The Launcher favorite list is missing {app_id}")
if "'ominx-settings.desktop'" not in shell_defaults:
    raise SystemExit("The Launcher favorites are missing OminX Settings")

shell_theme = config_root / "usr/share/themes/OminX/cinnamon/cinnamon.css"
theme_css = shell_theme.read_text(encoding="utf-8")
if theme_css.count("{") != theme_css.count("}"):
    raise SystemExit("OminX Cinnamon theme CSS has unbalanced braces")
for selector in ("#panel", ".window-list-item-box", ".appmenu-background .popup-menu-content"):
    if selector not in theme_css:
        raise SystemExit(f"OminX Cinnamon theme is missing {selector}")

ui_css = (config_root / "usr/share/ominx/ui/ominx-ui.css").read_text(encoding="utf-8")
if ui_css.count("{") != ui_css.count("}"):
    raise SystemExit("OminX Store and Settings stylesheet has unbalanced braces")
gtk_css_path = config_root / "usr/share/themes/OminX/gtk-3.0/gtk.css"
gtk_css = gtk_css_path.read_text(encoding="utf-8")
theme_index = (config_root / "usr/share/themes/OminX/index.theme").read_text(encoding="utf-8")
if "GtkTheme=OminX" not in theme_index:
    raise SystemExit("OminX GTK theme is not registered")
if gtk_css.count("{") != gtk_css.count("}") or "Adwaita/gtk-contained-dark.css" not in gtk_css:
    raise SystemExit("OminX GTK3 theme must extend the installed dark base with balanced CSS")
lightdm_greeter = (config_root / "etc/lightdm/lightdm-gtk-greeter.conf").read_text(encoding="utf-8")
if "theme-name=OminX" not in lightdm_greeter or "ominx-wallpaper.svg" not in lightdm_greeter:
    raise SystemExit("The login screen must use OminX branding and its original wallpaper")
wallpaper = config_root / "usr/share/backgrounds/ominx/ominx-wallpaper.svg"
wallpaper_text = wallpaper.read_text(encoding="utf-8")
if "OMINX" not in wallpaper_text:
    raise SystemExit("The desktop wallpaper is missing OminX branding")
if "<feGaussianBlur" in wallpaper_text:
    raise SystemExit("The OminX wallpaper should use lightweight gradients instead of a costly blur filter")
for selector in (".ominx-sidebar", ".ominx-hero", ".ominx-card", ".ominx-primary"):
    if selector not in ui_css:
        raise SystemExit(f"OminX app hub styling is missing {selector}")
if "selection-background-color" in ui_css:
    raise SystemExit("OminX app hub CSS must use GTK3 CSS properties")

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
    "gnome-software",
    "gnome-software-plugin-deb",
    "gnome-software-plugin-flatpak",
    "python3-gi",
    "gir1.2-gtk-3.0",
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
store_entry = applications / "ominx-store.desktop"
settings_entry = applications / "ominx-settings.desktop"
handler_entry = applications / "ominx-windows-app.desktop"
mime_defaults = applications / "mimeapps.list"
store_text = store_entry.read_text(encoding="utf-8")
settings_text = settings_entry.read_text(encoding="utf-8")
backend_override = (config_root / "usr/local/share/applications/org.gnome.Software.desktop").read_text(encoding="utf-8")
handler_text = handler_entry.read_text(encoding="utf-8")
mime_defaults_text = mime_defaults.read_text(encoding="utf-8")
if "TryExec=/usr/local/bin/ominx-store" not in store_text or "Exec=/usr/local/bin/ominx-store" not in store_text or "ominx-store.svg" not in store_text:
    raise SystemExit("OminX Store must have an absolute, verifiable launcher path and original icon")
if "TryExec=/usr/local/bin/ominx-settings" not in settings_text or "Exec=/usr/local/bin/ominx-settings" not in settings_text or "ominx-settings.svg" not in settings_text:
    raise SystemExit("OminX Settings must have an absolute, verifiable launcher path and original icon")
if "NoDisplay=true" not in backend_override or "Exec=gnome-software" not in backend_override:
    raise SystemExit("GNOME Software should remain available as the hidden OminX Store backend")
for launcher in ("ominx-store", "ominx-settings"):
    if not os.access(config_root / "usr/local/bin" / launcher, os.X_OK):
        raise SystemExit(f"{launcher} must be executable")
store_source = (config_root / "usr/lib/ominx/store.py").read_text(encoding="utf-8")
settings_source = (config_root / "usr/lib/ominx/settings.py").read_text(encoding="utf-8")
ui_source = (config_root / "usr/lib/ominx/ui.py").read_text(encoding="utf-8")
welcome_source = (config_root / "usr/lib/ominx/welcome.py").read_text(encoding="utf-8")
smoke_source = (root / "scripts/smoke-gtk-apps.py").read_text(encoding="utf-8")
if any(".set_group(" in source for source in (store_source, settings_source)):
    raise SystemExit("GTK3 navigation must not call the unsupported ToggleButton.set_group() API")
if "_desktop_app_info(product[\"desktop_id\"])" not in store_source or "except TypeError:" not in store_source:
    raise SystemExit("OminX Store must tolerate catalog apps whose desktop entries are not installed")
if any("self.maximize()" in source for source in (store_source, settings_source)):
    raise SystemExit("OminX app hubs must not force a second maximize-and-resize pass at startup")
if any("GLib.timeout_add(" not in source or "def _cancel_search_refresh" not in source for source in (store_source, settings_source)):
    raise SystemExit("OminX Store and Settings search must be debounced and cancel stale refreshes")
if any("set_default_window_size" not in source for source in (store_source, settings_source, welcome_source)):
    raise SystemExit("OminX windows must use the shared screen-aware opening size")
if "Gdk.Screen.get_default()" not in ui_source or "screen.get_width()" not in ui_source or "screen.get_height()" not in ui_source:
    raise SystemExit("OminX window sizing must adapt to the available display size")
if "wait_ms=140" not in smoke_source:
    raise SystemExit("GTK smoke tests must allow the debounced search handler to run")
if any(typelib not in hook for typelib in ("St-1.0.typelib", "Meta-0.typelib", "GI_TYPELIB_PATH=", "LD_LIBRARY_PATH=", "Gio.AppInfoMonitor.get()")):
    raise SystemExit("Cinnamon validation must locate its typelibs, libraries, and installed-app monitor")
if "gnome-software" not in store_source or "--search=" not in store_source or 'mode="updates"' not in store_source:
    raise SystemExit("OminX Store must forward catalog search, library, and update actions to the real backend")
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
for desktop_id in ("ominx-store.desktop", "ominx-settings.desktop", "ominx-windows-app.desktop"):
    if f"/usr/share/applications/{desktop_id}" not in hook:
        raise SystemExit(f"The image hook must validate {desktop_id}")
if "/usr/local/share/applications/org.gnome.Software.desktop" not in hook:
    raise SystemExit("The image hook must validate the OminX Store backend launcher override")
if "desktop-file-edit --set-key=NoDisplay --set-value=true" not in hook:
    raise SystemExit("GNOME Software should be hidden from the app menu behind OminX Store")
if "desktop-file-validate" not in hook:
    raise SystemExit("The image hook must validate desktop entries before packaging")
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
