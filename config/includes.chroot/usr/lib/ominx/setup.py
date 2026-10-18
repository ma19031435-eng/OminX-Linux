#!/usr/bin/python3
"""Interactive, resumable first-run setup for the OminX desktop."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gio", "2.0")
from gi.repository import Gio, GLib, Gtk  # noqa: E402

sys.path.insert(0, "/usr/lib/ominx")
from ui import apply_style, set_default_window_size  # noqa: E402


STEPS = (
    ("welcome", "Welcome"),
    ("network", "Network"),
    ("software", "Software"),
    ("gaming", "Gaming"),
    ("finish", "Finish"),
)


class SetupWindow(Gtk.Window):
    def __init__(self, *, first_run: bool = False) -> None:
        super().__init__(title="OminX Setup")
        set_default_window_size(self, 1000, 740)
        self.set_position(Gtk.WindowPosition.CENTER)
        self.set_icon_name("ominx")
        self.first_run = first_run
        self.current_step = 0
        self._finished = False
        self.setup_directory = Path.home() / ".config" / "ominx"
        self.complete_marker = self.setup_directory / "setup-complete"
        self.dismissed_marker = self.setup_directory / "setup-dismissed"
        self.firefox_app = Gio.DesktopAppInfo.new("firefox-esr.desktop")
        self.network_monitor = Gio.NetworkMonitor.get_default()
        self.network_monitor_handler = 0
        if self.network_monitor is not None:
            self.network_monitor_handler = self.network_monitor.connect(
                "network-changed", self._on_network_changed
            )

        apply_style()
        self._build_ui()
        self._show_step(0)
        self.connect("destroy", self._on_destroy)
        self.show_all()

    def _build_ui(self) -> None:
        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        root.set_margin_top(24)
        root.set_margin_bottom(20)
        root.set_margin_start(26)
        root.set_margin_end(26)
        root.get_style_context().add_class("ominx-shell")
        self.add(root)

        header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=15)
        logo = Gtk.Image.new_from_file(
            "/usr/share/icons/hicolor/scalable/apps/ominx.svg"
        )
        logo.set_pixel_size(52)
        header.pack_start(logo, False, False, 0)

        title_column = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3)
        title = Gtk.Label(label="Set up OminX")
        title.set_xalign(0)
        title.get_style_context().add_class("ominx-title")
        subtitle = Gtk.Label(label="A few useful choices. Everything can be changed later.")
        subtitle.set_xalign(0)
        subtitle.get_style_context().add_class("ominx-subtitle")
        title_column.pack_start(title, False, False, 0)
        title_column.pack_start(subtitle, False, False, 0)
        header.pack_start(title_column, True, True, 0)

        badge = Gtk.Label(label="FIRST-RUN SETUP")
        badge.get_style_context().add_class("ominx-version")
        header.pack_end(badge, False, False, 0)
        root.pack_start(header, False, False, 0)

        self.progress = Gtk.ProgressBar()
        self.progress.set_fraction(0.2)
        self.progress.set_no_show_all(False)
        root.pack_start(self.progress, False, False, 0)

        divider = Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL)
        divider.get_style_context().add_class("ominx-divider")
        root.pack_start(divider, False, False, 0)

        self.stack = Gtk.Stack()
        self.stack.set_transition_type(Gtk.StackTransitionType.SLIDE_LEFT_RIGHT)
        self.stack.set_transition_duration(180)
        self.stack.set_hexpand(True)
        self.stack.set_vexpand(True)
        for name, _label in STEPS:
            page = getattr(self, f"_build_{name}_page")()
            self.stack.add_named(page, name)
        root.pack_start(self.stack, True, True, 0)

        footer = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        footer.get_style_context().add_class("ominx-setup-footer")
        self.skip_button = Gtk.Button(label="Skip setup")
        self.skip_button.get_style_context().add_class("ominx-flat-button")
        self.skip_button.connect("clicked", self._skip_setup)
        footer.pack_start(self.skip_button, False, False, 0)

        footer.pack_start(Gtk.Box(), True, True, 0)
        self.step_label = Gtk.Label()
        self.step_label.get_style_context().add_class("ominx-muted")
        footer.pack_start(self.step_label, False, False, 6)

        footer.pack_start(Gtk.Box(), True, True, 0)
        self.back_button = Gtk.Button(label="Back")
        self.back_button.get_style_context().add_class("ominx-secondary")
        self.back_button.connect("clicked", self._go_back)
        footer.pack_start(self.back_button, False, False, 0)

        self.next_button = Gtk.Button(label="Continue")
        self.next_button.get_style_context().add_class("ominx-primary")
        self.next_button.connect("clicked", self._go_forward)
        footer.pack_start(self.next_button, False, False, 0)
        root.pack_start(footer, False, False, 0)

    @staticmethod
    def _new_page(title: str, description: str) -> Gtk.Box:
        page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        page.set_margin_top(5)
        page.set_margin_bottom(8)
        page.get_style_context().add_class("ominx-setup-page")

        heading = Gtk.Label(label=title)
        heading.set_xalign(0)
        heading.get_style_context().add_class("ominx-page-title")
        page.pack_start(heading, False, False, 0)

        copy = Gtk.Label(label=description)
        copy.set_xalign(0)
        copy.set_line_wrap(True)
        copy.get_style_context().add_class("ominx-copy")
        page.pack_start(copy, False, False, 0)
        return page

    @staticmethod
    def _card_copy(title: str, description: str, icon_name: str) -> Gtk.Box:
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=13)
        icon = Gtk.Image.new_from_icon_name(icon_name, Gtk.IconSize.DIALOG)
        icon.set_pixel_size(30)
        row.pack_start(icon, False, False, 0)

        text = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        heading = Gtk.Label(label=title)
        heading.set_xalign(0)
        heading.get_style_context().add_class("ominx-card-title")
        body = Gtk.Label(label=description)
        body.set_xalign(0)
        body.set_line_wrap(True)
        body.set_max_width_chars(48)
        body.get_style_context().add_class("ominx-card-copy")
        text.pack_start(heading, False, False, 0)
        text.pack_start(body, False, False, 0)
        row.pack_start(text, True, True, 0)
        return row

    @staticmethod
    def _info_card(title: str, description: str, icon_name: str) -> Gtk.Box:
        card = SetupWindow._card_copy(title, description, icon_name)
        card.get_style_context().add_class("ominx-card")
        return card

    def _build_welcome_page(self) -> Gtk.Box:
        page = self._new_page(
            "A workspace shaped around you",
            "OminX is ready. Take a moment to connect, review a few useful defaults, and find your way around.",
        )

        hero = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=22)
        hero.get_style_context().add_class("ominx-hero")
        text = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        text.set_hexpand(True)
        name = Gtk.Label(label="OminX Aurora")
        name.set_xalign(0)
        name.get_style_context().add_class("ominx-hero-title")
        description = Gtk.Label(
            label="Midnight surfaces, sea-glass light, and a quiet command bar. Your files, apps, and settings are only a step away."
        )
        description.set_xalign(0)
        description.set_line_wrap(True)
        description.set_max_width_chars(68)
        description.get_style_context().add_class("ominx-hero-copy")
        text.pack_start(name, False, False, 0)
        text.pack_start(description, False, False, 0)
        emblem = Gtk.Image.new_from_file(
            "/usr/share/icons/hicolor/scalable/apps/ominx.svg"
        )
        emblem.set_pixel_size(82)
        hero.pack_start(text, True, True, 0)
        hero.pack_end(emblem, False, False, 4)
        page.pack_start(hero, False, False, 4)

        cards = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        cards.pack_start(
            self._info_card(
                "Find your apps",
                "Open the OminX Launcher from the top bar, or discover more in OminX Store.",
                "view-grid-symbolic",
            ),
            True,
            True,
            0,
        )
        cards.pack_start(
            self._info_card(
                "Tune your space",
                "OminX Settings brings display, devices, privacy, and other controls together.",
                "preferences-system-symbolic",
            ),
            True,
            True,
            0,
        )
        page.pack_start(cards, False, False, 0)
        page.pack_start(Gtk.Box(), True, True, 0)
        return page

    def _build_network_page(self) -> Gtk.Box:
        page = self._new_page(
            "Connect when you are ready",
            "Wi-Fi and Ethernet settings are available now. You can also finish setup offline and connect later.",
        )

        status_card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        status_card.get_style_context().add_class("ominx-card")
        status_heading = Gtk.Label(label="Connection status")
        status_heading.set_xalign(0)
        status_heading.get_style_context().add_class("ominx-card-title")
        self.network_status = Gtk.Label()
        self.network_status.set_xalign(0)
        self.network_status.set_line_wrap(True)
        self.network_status.get_style_context().add_class("ominx-card-copy")
        status_card.pack_start(status_heading, False, False, 0)
        status_card.pack_start(self.network_status, False, False, 0)
        page.pack_start(status_card, False, False, 4)

        note = Gtk.Label(
            label="This status comes from the desktop network monitor; it does not guarantee access to the internet."
        )
        note.set_xalign(0)
        note.set_line_wrap(True)
        note.get_style_context().add_class("ominx-note")
        page.pack_start(note, False, False, 0)

        self.network_button = Gtk.Button(label="Open network settings")
        self.network_button.get_style_context().add_class("ominx-secondary")
        self.network_button.set_halign(Gtk.Align.START)
        self.network_button.connect(
            "clicked", self._launch_command, ["nm-connection-editor"]
        )
        page.pack_start(self.network_button, False, False, 0)
        page.pack_start(Gtk.Box(), True, True, 0)
        return page

    def _build_software_page(self) -> Gtk.Box:
        page = self._new_page(
            "Choose your everyday tools",
            "Review software after setup, and choose whether Firefox ESR should open web links by default.",
        )

        browser_card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=9)
        browser_card.get_style_context().add_class("ominx-card")
        browser_heading = Gtk.Label(label="Browser preference")
        browser_heading.set_xalign(0)
        browser_heading.get_style_context().add_class("ominx-card-title")
        browser_copy = Gtk.Label(
            label="This is a user-level preference. You can change it later in your desktop settings."
        )
        browser_copy.set_xalign(0)
        browser_copy.set_line_wrap(True)
        browser_copy.get_style_context().add_class("ominx-card-copy")
        self.browser_check = Gtk.CheckButton(
            label="Make Firefox ESR my default browser"
        )
        self.browser_check.set_active(self.firefox_app is not None)
        self.browser_check.set_sensitive(self.firefox_app is not None)
        if self.firefox_app is None:
            self.browser_check.set_label("Firefox ESR is not installed")
        browser_card.pack_start(browser_heading, False, False, 0)
        browser_card.pack_start(browser_copy, False, False, 0)
        browser_card.pack_start(self.browser_check, False, False, 4)
        page.pack_start(browser_card, False, False, 4)

        actions = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        store_button = Gtk.Button(label="Explore OminX Store")
        store_button.get_style_context().add_class("ominx-primary")
        store_button.connect(
            "clicked", self._launch_command, ["ominx-store"]
        )
        updates_button = Gtk.Button(label="Review software updates")
        updates_button.get_style_context().add_class("ominx-secondary")
        updates_button.connect(
            "clicked",
            self._launch_command,
            ["gnome-software", "--mode=updates"],
        )
        actions.pack_start(store_button, False, False, 0)
        actions.pack_start(updates_button, False, False, 0)
        page.pack_start(actions, False, False, 0)

        footnote = Gtk.Label(
            label="OminX Store uses the configured Debian and Flatpak software sources. Installing optional apps requires an internet connection."
        )
        footnote.set_xalign(0)
        footnote.set_line_wrap(True)
        footnote.get_style_context().add_class("ominx-note")
        page.pack_start(footnote, False, False, 0)
        page.pack_start(Gtk.Box(), True, True, 0)
        return page

    def _build_gaming_page(self) -> Gtk.Box:
        page = self._new_page(
            "Ready for games, without the guesswork",
            "Steam and Lutris are available. Compatibility depends on each game, drivers, and hardware.",
        )

        steam_card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=11)
        steam_card.get_style_context().add_class("ominx-card")
        steam_card.pack_start(
            self._card_copy(
                "Steam and Proton",
                "Sign in to Steam, then enable Steam Play for supported titles. Steam downloads Proton when it is needed.",
                "applications-games-symbolic",
            ),
            False,
            False,
            0,
        )
        steam_button = Gtk.Button(label="Open Steam")
        steam_button.get_style_context().add_class("ominx-secondary")
        steam_button.set_halign(Gtk.Align.START)
        steam_button.connect("clicked", self._launch_command, ["steam"])
        steam_card.pack_start(steam_button, False, False, 0)

        lutris_card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=11)
        lutris_card.get_style_context().add_class("ominx-card")
        lutris_card.pack_start(
            self._card_copy(
                "Compatibility tools",
                "Wine, Winetricks, and Lutris support many Windows apps and games, but no compatibility layer runs everything.",
                "applications-system-symbolic",
            ),
            False,
            False,
            0,
        )
        lutris_button = Gtk.Button(label="Open Lutris")
        lutris_button.get_style_context().add_class("ominx-secondary")
        lutris_button.set_halign(Gtk.Align.START)
        lutris_button.connect("clicked", self._launch_command, ["lutris"])
        lutris_card.pack_start(lutris_button, False, False, 0)

        columns = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        columns.pack_start(steam_card, True, True, 0)
        columns.pack_start(lutris_card, True, True, 0)
        page.pack_start(columns, False, False, 4)

        note = Gtk.Label(
            label="Feral GameMode is available per game. It can request supported performance settings; results vary and no fixed latency reduction is promised."
        )
        note.set_xalign(0)
        note.set_line_wrap(True)
        note.get_style_context().add_class("ominx-note")
        page.pack_start(note, False, False, 0)
        page.pack_start(Gtk.Box(), True, True, 0)
        return page

    def _build_finish_page(self) -> Gtk.Box:
        page = self._new_page(
            "Your OminX desktop is ready",
            "Nothing installs in the background. You are in control of optional apps and system changes.",
        )

        hero = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=18)
        hero.get_style_context().add_class("ominx-hero")
        text = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        title = Gtk.Label(label="Make it your own")
        title.set_xalign(0)
        title.get_style_context().add_class("ominx-hero-title")
        self.finish_summary = Gtk.Label(
            label="Open OminX Settings, explore the Store, or start with the apps already on your desktop."
        )
        self.finish_summary.set_xalign(0)
        self.finish_summary.set_line_wrap(True)
        self.finish_summary.set_max_width_chars(64)
        self.finish_summary.get_style_context().add_class("ominx-hero-copy")
        text.pack_start(title, False, False, 0)
        text.pack_start(self.finish_summary, False, False, 0)
        emblem = Gtk.Image.new_from_file(
            "/usr/share/icons/hicolor/scalable/apps/ominx.svg"
        )
        emblem.set_pixel_size(72)
        hero.pack_start(text, True, True, 0)
        hero.pack_end(emblem, False, False, 4)
        page.pack_start(hero, False, False, 4)

        shortcuts = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        shortcuts.pack_start(
            self._info_card("Files", "Super+E", "system-file-manager-symbolic"),
            True,
            True,
            0,
        )
        shortcuts.pack_start(
            self._info_card("Settings", "Super+I", "preferences-system-symbolic"),
            True,
            True,
            0,
        )
        page.pack_start(shortcuts, False, False, 0)
        page.pack_start(Gtk.Box(), True, True, 0)
        return page

    def _show_step(self, index: int) -> None:
        self.current_step = index
        name, _label = STEPS[index]
        self.stack.set_visible_child_name(name)
        self.progress.set_fraction((index + 1) / len(STEPS))
        self.step_label.set_text(f"Step {index + 1} of {len(STEPS)}")
        self.back_button.set_sensitive(index > 0)
        self.next_button.set_label(
            "Finish OminX" if index == len(STEPS) - 1 else "Continue"
        )
        if name == "network":
            self._refresh_network_status()
        elif name == "finish":
            browser_choice = (
                "Firefox ESR will be your default browser."
                if self.browser_check.get_active() and self.firefox_app is not None
                else "Your current browser preference will be left unchanged."
            )
            self.finish_summary.set_text(
                f"{browser_choice} Open OminX Settings, explore the Store, or start with the apps already on your desktop."
            )

    def _go_back(self, _button: Gtk.Button) -> None:
        if self.current_step > 0:
            self._show_step(self.current_step - 1)

    def _go_forward(self, _button: Gtk.Button) -> None:
        if self.current_step < len(STEPS) - 1:
            self._show_step(self.current_step + 1)
            return
        self._complete_setup(apply_preferences=True)

    def _skip_setup(self, _button: Gtk.Button) -> None:
        self._complete_setup(apply_preferences=False)

    def _complete_setup(self, *, apply_preferences: bool) -> None:
        if apply_preferences:
            self._apply_browser_preference()
        self.setup_directory.mkdir(parents=True, exist_ok=True)
        self.complete_marker.write_text("completed\n", encoding="utf-8")
        self.dismissed_marker.unlink(missing_ok=True)
        self._finished = True
        self.destroy()

    def _apply_browser_preference(self) -> None:
        if not self.browser_check.get_active() or self.firefox_app is None:
            return
        failures = []
        for content_type in (
            "text/html",
            "x-scheme-handler/http",
            "x-scheme-handler/https",
        ):
            try:
                if not self.firefox_app.set_as_default_for_type(content_type):
                    failures.append(content_type)
            except (GLib.Error, RuntimeError) as error:
                failures.append(f"{content_type}: {error}")
        if failures:
            self._show_message(
                "Browser preference not changed",
                "OminX could not set every web-link association. You can choose a default browser later in desktop settings.",
            )

    def _refresh_network_status(self) -> None:
        if self.network_monitor is None:
            message = "Network status is not available right now. You can continue setup offline."
        elif self.network_monitor.get_network_available():
            message = "A network connection appears to be available. You can continue setup or review your connection."
        else:
            message = "No network connection is detected. Connect Wi-Fi or Ethernet now, or continue setup offline."
        self.network_status.set_text(message)

    def _on_network_changed(self, _monitor: Gio.NetworkMonitor, _available: bool) -> None:
        self._refresh_network_status()

    def _launch_command(self, _button: Gtk.Button, command: list[str]) -> None:
        search_path = os.pathsep.join(
            filter(None, (os.environ.get("PATH", ""), "/usr/games", "/usr/local/games"))
        )
        executable = shutil.which(command[0], path=search_path)
        if executable is None:
            self._show_message(
                "Application not found",
                f"{command[0]} is not available right now. You can continue setup and try again later.",
            )
            return
        try:
            subprocess.Popen(
                [executable, *command[1:]],
                env={**os.environ, "PATH": search_path},
                start_new_session=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except OSError as error:
            self._show_message("Could not open application", str(error))

    def _show_message(self, title: str, message: str) -> None:
        dialog = Gtk.MessageDialog(
            transient_for=self,
            modal=True,
            message_type=Gtk.MessageType.INFO,
            buttons=Gtk.ButtonsType.CLOSE,
            text=title,
        )
        dialog.format_secondary_text(message)
        dialog.run()
        dialog.destroy()

    def _on_destroy(self, _window: Gtk.Window) -> None:
        if self.network_monitor is not None and self.network_monitor_handler:
            self.network_monitor.disconnect(self.network_monitor_handler)
            self.network_monitor_handler = 0
        if self.first_run and not self._finished and not self.complete_marker.exists():
            try:
                self.setup_directory.mkdir(parents=True, exist_ok=True)
                self.dismissed_marker.touch(exist_ok=True)
            except OSError:
                pass


def main() -> int:
    if os.environ.get("OMINX_SMOKE_TEST") == "1":
        return 0
    first_run = "--first-run" in sys.argv[1:]
    setup_directory = Path.home() / ".config" / "ominx"
    if first_run and (
        (setup_directory / "setup-complete").exists()
        or (setup_directory / "setup-dismissed").exists()
    ):
        return 0

    Gtk.init([])
    window = SetupWindow(first_run=first_run)
    window.connect("destroy", lambda _window: Gtk.main_quit())
    Gtk.main()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
