#!/usr/bin/python3
"""Exercise the OminX GTK windows and their real launch wrappers under Xvfb."""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import GLib, Gtk  # noqa: E402

sys.path.insert(0, "/usr/lib/ominx")
from settings import SettingsWindow  # noqa: E402
from setup import SetupWindow  # noqa: E402
from store import StoreWindow  # noqa: E402
from welcome import WelcomeWindow  # noqa: E402


ROOT = Path("/workspace/config/includes.chroot")
CSS_FILES = (
    ROOT / "usr/share/ominx/ui/ominx-ui.css",
    ROOT / "usr/share/themes/OminX/gtk-3.0/gtk.css",
)


def drain_events(wait_ms: int = 0) -> None:
    deadline = time.monotonic() + wait_ms / 1000
    context = GLib.MainContext.default()
    while True:
        while context.pending():
            context.iteration(False)
        if time.monotonic() >= deadline:
            return
        time.sleep(0.005)


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


def visible_label_text(widget: Gtk.Widget) -> str:
    labels: list[str] = []
    if isinstance(widget, Gtk.Label):
        labels.append(widget.get_text())
    if isinstance(widget, Gtk.Container):
        for child in widget.get_children():
            labels.append(visible_label_text(child))
    return " ".join(labels)


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
    drain_events(wait_ms=140)
    search_text = visible_label_text(window.page_box).casefold()
    if "results for" not in search_text or "steam" not in search_text:
        raise AssertionError("OminX Store did not apply its debounced Steam search")

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
    if "workspace shaped around you" not in visible_label_text(window.page_box).casefold():
        raise AssertionError("OminX Settings did not render its Aurora workspace hero")

    window.search_entry.set_text("Bluetooth")
    drain_events(wait_ms=140)
    search_text = visible_label_text(window.page_box).casefold()
    if "search results" not in search_text or "bluetooth" not in search_text:
        raise AssertionError("OminX Settings did not apply its debounced Bluetooth search")

    window.search_entry.set_text("")
    window.nav_buttons["Gaming"].clicked()
    drain_events()
    if not window.page_box.get_children():
        raise AssertionError("OminX Settings Gaming page rendered no content")
    if not window.nav_buttons["Gaming"].get_active() or window.nav_buttons["Workspace"].get_active():
        raise AssertionError("OminX Settings navigation buttons are not mutually exclusive")
    window.destroy()
    drain_events()


def check_welcome_window() -> None:
    window = WelcomeWindow()
    window.show_all()
    drain_events()
    if not window.get_visible() or not window.get_title().startswith("Welcome to OminX"):
        raise AssertionError("OminX Welcome window did not become visible")
    welcome_text = visible_label_text(window).casefold()
    if "top bar" not in welcome_text or "ominx settings" not in welcome_text:
        raise AssertionError("OminX Welcome did not render its Aurora desktop guidance")
    window.destroy()
    drain_events()


def check_setup_window() -> None:
    with tempfile.TemporaryDirectory(prefix="ominx-setup-smoke-") as temporary:
        window = SetupWindow(first_run=True)
        window.setup_directory = Path(temporary) / ".config" / "ominx"
        window.complete_marker = window.setup_directory / "setup-complete"
        window.dismissed_marker = window.setup_directory / "setup-dismissed"
        drain_events()
        if not window.get_visible() or window.get_title() != "OminX Setup":
            raise AssertionError("OminX Setup window did not become visible")

        expected_steps = ("welcome", "network", "software", "gaming", "finish")
        for index, step in enumerate(expected_steps):
            if window.stack.get_visible_child_name() != step:
                raise AssertionError(f"OminX Setup did not show its {step} step")
            page_text = visible_label_text(window.stack.get_visible_child()).casefold()
            if not page_text:
                raise AssertionError(f"OminX Setup {step} step rendered no content")
            if step == "network" and "connection" not in page_text:
                raise AssertionError("OminX Setup network status did not render")
            if step == "gaming" and "proton" not in page_text:
                raise AssertionError("OminX Setup gaming guidance did not render")
            if index < len(expected_steps) - 1:
                window.next_button.clicked()
                drain_events(wait_ms=200)

        if window.next_button.get_label() != "Finish OminX":
            raise AssertionError("OminX Setup did not offer a final completion action")
        window.back_button.clicked()
        drain_events(wait_ms=200)
        if window.stack.get_visible_child_name() != "gaming":
            raise AssertionError("OminX Setup Back navigation did not return to Gaming")
        window.next_button.clicked()
        drain_events(wait_ms=200)
        window.next_button.clicked()
        drain_events()
        if not window.complete_marker.is_file() or window.dismissed_marker.exists():
            raise AssertionError("OminX Setup did not persist its first-run completion state")


def check_launch_wrappers() -> None:
    environment = os.environ.copy()
    environment["OMINX_SMOKE_TEST"] = "1"
    environment.setdefault("PATH", "/usr/local/bin:/usr/bin:/bin")
    for executable in (
        "/usr/local/bin/ominx-store",
        "/usr/local/bin/ominx-settings",
        "/usr/local/bin/ominx-setup",
    ):
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
    check_welcome_window()
    check_setup_window()
    check_launch_wrappers()
    print("OminX GTK CSS, Store, Settings, Welcome, Setup, search, navigation, and launch wrappers passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
