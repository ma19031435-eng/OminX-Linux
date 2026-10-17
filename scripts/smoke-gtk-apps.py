#!/usr/bin/python3
"""Exercise the OminX GTK windows and their real launch wrappers under Xvfb."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk  # noqa: E402

sys.path.insert(0, "/usr/lib/ominx")
from settings import SettingsWindow  # noqa: E402
from store import StoreWindow  # noqa: E402


ROOT = Path("/workspace/config/includes.chroot")
CSS_FILES = (
    ROOT / "usr/share/ominx/ui/ominx-ui.css",
    ROOT / "usr/share/themes/OminX/gtk-3.0/gtk.css",
)


def drain_events() -> None:
    while Gtk.events_pending():
        Gtk.main_iteration_do(False)


def check_css() -> None:
    for stylesheet in CSS_FILES:
        errors: list[str] = []
        provider = Gtk.CssProvider()
        provider.connect(
            "parsing-error",
            lambda _provider, _section, error: errors.append(str(error)),
        )
        provider.load_from_path(str(stylesheet))
        if errors:
            raise AssertionError(f"GTK CSS parse errors in {stylesheet}: {'; '.join(errors)}")


def check_store_window() -> None:
    window = StoreWindow()
    drain_events()
    if not window.get_visible() or not window.get_title().startswith("OminX Store"):
        raise AssertionError("OminX Store window did not become visible")
    if not window.page_box.get_children():
        raise AssertionError("OminX Store home page rendered no content")
    if window._desktop_app_info("ominx-smoke-test-missing.desktop") is not None:
        raise AssertionError("Missing desktop entries should fall back to the software catalog")

    window.search_entry.set_text("steam")
    drain_events()
    if not window.page_box.get_children():
        raise AssertionError("OminX Store search rendered no results or empty state")

    window.search_entry.set_text("")
    window.nav_buttons["games"].clicked()
    drain_events()
    if window.active_page != "games" or not window.page_box.get_children():
        raise AssertionError("OminX Store Games navigation did not render correctly")
    if not window.nav_buttons["games"].get_active() or window.nav_buttons["home"].get_active():
        raise AssertionError("OminX Store navigation buttons are not mutually exclusive")
    window.destroy()
    drain_events()


def check_settings_window() -> None:
    window = SettingsWindow()
    drain_events()
    if not window.get_visible() or not window.get_title().startswith("OminX Settings"):
        raise AssertionError("OminX Settings window did not become visible")
    if not window.page_box.get_children():
        raise AssertionError("OminX Settings home page rendered no content")

    window.search_entry.set_text("Bluetooth")
    drain_events()
    if not window.page_box.get_children():
        raise AssertionError("OminX Settings search rendered no results or empty state")

    window.search_entry.set_text("")
    window.nav_buttons["Gaming"].clicked()
    drain_events()
    if not window.page_box.get_children():
        raise AssertionError("OminX Settings Gaming page rendered no content")
    if not window.nav_buttons["Gaming"].get_active() or window.nav_buttons["System"].get_active():
        raise AssertionError("OminX Settings navigation buttons are not mutually exclusive")
    window.destroy()
    drain_events()


def check_launch_wrappers() -> None:
    environment = os.environ.copy()
    environment["OMINX_SMOKE_TEST"] = "1"
    environment.setdefault("PATH", "/usr/local/bin:/usr/bin:/bin")
    for executable in ("/usr/local/bin/ominx-store", "/usr/local/bin/ominx-settings"):
        result = subprocess.run(
            [executable],
            check=False,
            env=environment,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=20,
        )
        if result.returncode != 0:
            raise AssertionError(
                f"{executable} failed with status {result.returncode}:\n"
                f"{result.stdout}\n{result.stderr}"
            )


def main() -> int:
    Gtk.init([])
    check_css()
    check_store_window()
    check_settings_window()
    check_launch_wrappers()
    print("OminX GTK CSS, Store, Settings, search, navigation, and launch wrappers passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
