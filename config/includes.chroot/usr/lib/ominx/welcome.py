#!/usr/bin/python3
"""Small GTK welcome screen for the OminX live/installed desktop."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk  # noqa: E402

sys.path.insert(0, "/usr/lib/ominx")
from ui import apply_style, set_default_window_size  # noqa: E402


class WelcomeWindow(Gtk.Window):
    def __init__(self) -> None:
        super().__init__(title="Welcome to OminX")
        set_default_window_size(self, 960, 680)
        self.set_border_width(26)
        self.set_position(Gtk.WindowPosition.CENTER)
        self.set_icon_name("ominx")
        apply_style()

        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=19)
        self.add(root)

        brand = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=16)
        brand.set_valign(Gtk.Align.CENTER)
        logo = Gtk.Image.new_from_file(
            "/usr/share/icons/hicolor/scalable/apps/ominx.svg"
        )
        logo.set_pixel_size(58)
        brand.pack_start(logo, False, False, 0)

        brand_text = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        title = Gtk.Label(label="Welcome to OminX")
        title.set_xalign(0)
        title.get_style_context().add_class("ominx-title")
        subtitle = Gtk.Label(label="A luminous KDE Plasma workspace for work, creativity, and play. Open the OminX Launcher from the floating panel to find apps and controls.")
        subtitle.set_xalign(0)
        subtitle.get_style_context().add_class("ominx-subtitle")
        brand_text.pack_start(title, False, False, 0)
        brand_text.pack_start(subtitle, False, False, 0)
        brand.pack_start(brand_text, True, True, 0)

        version = Gtk.Label(label="BETA  ·  DEBIAN 13")
        version.get_style_context().add_class("ominx-version")
        brand.pack_end(version, False, False, 4)
        root.pack_start(brand, False, False, 0)

        divider = Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL)
        root.pack_start(divider, False, False, 0)

        section = Gtk.Label(label="Find your way around OminX")
        section.set_xalign(0)
        section.get_style_context().add_class("ominx-section")
        root.pack_start(section, False, False, 0)

        grid = Gtk.Grid()
        grid.set_row_spacing(14)
        grid.set_column_spacing(14)
        grid.set_column_homogeneous(True)
        grid.set_row_homogeneous(True)
        root.pack_start(grid, True, True, 0)

        grid.attach(
            self._card(
                "Everyday apps",
                "Open files, explore the web, create documents, and find new tools in the OminX Store.",
                "Browse apps",
                self._open_store,
            ),
            0,
            0,
            1,
            1,
        )
        grid.attach(
            self._card(
                "Your game library",
                "Steam is included. Enable Proton in Steam for supported games; Feral GameMode can request tuning while a game runs.",
                "Open Steam",
                lambda: self._launch("steam"),
            ),
            1,
            0,
            1,
            1,
        )
        grid.attach(
            self._card(
                "Windows app support",
                "Wine with 32-bit support, Winetricks, and Lutris are ready. Compatibility varies by program.",
                "Read compatibility guide",
                self._show_compatibility,
                secondary=True,
            ),
            0,
            1,
            1,
            1,
        )
        grid.attach(
            self._card(
                "Make it yours",
                "Shape your display, sound, network, devices, accounts, privacy, and more in OminX Settings.",
                "Open OminX Settings",
                lambda: self._launch("ominx-settings"),
                secondary=True,
            ),
            1,
            1,
            1,
            1,
        )

        bottom = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        note = Gtk.Label(
            label="Quick keys: Meta opens the Plasma launcher, and Alt+Space searches apps and commands with KRunner. Review or change the rest in KDE System Settings. Zstd zram compresses less-active pages; apps stay running. Game Mode works per game, with results that vary by hardware."
        )
        note.set_xalign(0)
        note.set_line_wrap(True)
        note.get_style_context().add_class("ominx-note")
        bottom.pack_start(note, True, True, 0)

        actions = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=7)
        setup = Gtk.Button(label="Run OminX Setup")
        setup.get_style_context().add_class("ominx-secondary")
        setup.connect("clicked", lambda _button: self._launch("ominx-setup"))
        actions.pack_start(setup, False, False, 0)

        game_mode = Gtk.Button(label="Game Mode setup")
        game_mode.get_style_context().add_class("ominx-secondary")
        game_mode.connect("clicked", lambda _button: self._show_game_mode())
        actions.pack_start(game_mode, False, False, 0)

        memory = Gtk.Button(label="Memory details")
        memory.get_style_context().add_class("ominx-secondary")
        memory.connect("clicked", lambda _button: self._show_memory())
        actions.pack_start(memory, False, False, 0)

        protontricks = Gtk.Button(label="Protontricks")
        protontricks.get_style_context().add_class("ominx-secondary")
        protontricks.set_tooltip_text(
            "Installs Protontricks in your user account from PyPI on first use."
        )
        protontricks.connect("clicked", self._open_protontricks)
        actions.pack_start(protontricks, False, False, 0)
        bottom.pack_end(actions, False, False, 0)
        root.pack_start(bottom, False, False, 0)

    @staticmethod
    def _card(title_text: str, copy_text: str, button_text: str, callback, secondary=False):
        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        card.get_style_context().add_class("ominx-card")

        title = Gtk.Label(label=title_text)
        title.set_xalign(0)
        title.get_style_context().add_class("ominx-card-title")
        card.pack_start(title, False, False, 0)

        copy = Gtk.Label(label=copy_text)
        copy.set_xalign(0)
        copy.set_yalign(0)
        copy.set_line_wrap(True)
        copy.set_max_width_chars(43)
        copy.get_style_context().add_class("ominx-card-copy")
        card.pack_start(copy, True, True, 0)

        button = Gtk.Button(label=button_text)
        button.get_style_context().add_class(
            "ominx-secondary" if secondary else "ominx-primary"
        )
        button.set_halign(Gtk.Align.START)
        button.connect("clicked", lambda _button: callback())
        card.pack_end(button, False, False, 0)
        return card

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

    def _show_compatibility(self) -> None:
        self._show_message(
            "Windows app and game compatibility",
            "Steam games: open Steam → Settings → Compatibility, then enable Steam Play. Steam installs its Proton runtime when needed.\n\n"
            "Standalone apps: double-click a trusted .exe or .msi installer. OminX Windows App Support runs it through Wine; use Open With → OminX Windows App Support if asked. The first launch creates your Wine environment, and an installed app may add a shortcut to the Applications menu. Winetricks and Lutris are included for apps that need extra setup.\n\n"
            "Not every program works. Windows kernel drivers, most Windows Store/UWP apps, some DRM, and games whose anti-cheat blocks Linux are not supported. Wine apps can access your user files, so only run software you trust. Check ProtonDB or Wine AppDB first.",
        )

    def _show_game_mode(self) -> None:
        self._show_message(
            "OminX Game Mode",
            "Steam: open a game's Properties → General → Launch Options and add:\n\n"
            "/usr/games/gamemoderun %command%\n\n"
            "Lutris can enable Feral GameMode in each game's options. GameMode requests supported performance settings only while the game runs. It may help scheduling or power-policy overhead on some machines, but it cannot guarantee a 50% latency reduction or improve network routing. Measure the same game and scene before and after.",
        )

    def _show_memory(self) -> None:
        self._show_message(
            "Compressed memory, not paused apps",
            "OminX uses zstd zram for less-active memory pages. Under pressure, Linux compresses those pages into RAM and restores them when needed; applications are not intentionally frozen, hibernated, or closed.\n\n"
            "This is page-level memory compression, not compression of installed app files. It uses some CPU time, so results depend on the workload. See /usr/share/doc/ominx/performance.md for details.",
        )

    def _launch(self, command: str) -> None:
        search_path = os.environ.get("PATH", "") + os.pathsep + "/usr/games:/usr/local/games"
        executable = shutil.which(command, path=search_path)
        if executable is None:
            self._show_message(
                "App not found",
                f"{command} is not currently available. Check your network connection and installed applications in Software.",
            )
            return
        try:
            subprocess.Popen(
                [executable],
                env={**os.environ, "PATH": search_path},
                start_new_session=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except OSError as error:
            self._show_message("Could not open app", str(error))

    def _open_store(self) -> None:
        self._launch("ominx-store")

    def _open_protontricks(self, _button) -> None:
        search_path = os.environ.get("PATH", "") + os.pathsep + "/usr/games:/usr/local/games"
        terminal = shutil.which("x-terminal-emulator", path=search_path)
        if terminal is None:
            self._show_message(
                "Terminal not found",
                "Open a terminal and run: ominx-protontricks",
            )
            return
        try:
            subprocess.Popen(
                [terminal, "-e", "ominx-protontricks"],
                env={**os.environ, "PATH": search_path},
                start_new_session=True,
            )
        except OSError as error:
            self._show_message("Could not start Protontricks", str(error))


def main() -> int:
    first_run = "--first-run" in sys.argv[1:]
    marker = Path.home() / ".config" / "ominx" / "welcome-complete"
    if first_run and marker.exists():
        return 0

    window = WelcomeWindow()

    def on_destroy(_window) -> None:
        if first_run:
            marker.parent.mkdir(parents=True, exist_ok=True)
            marker.touch(exist_ok=True)
        Gtk.main_quit()

    window.connect("destroy", on_destroy)
    window.show_all()
    if "--game-mode" in sys.argv[1:]:
        window._show_game_mode()
    elif "--memory" in sys.argv[1:]:
        window._show_memory()
    Gtk.main()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
