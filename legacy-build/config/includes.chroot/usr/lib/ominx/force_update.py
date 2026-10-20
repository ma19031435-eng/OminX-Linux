#!/usr/bin/python3
"""Mandatory legacy-build update prompt shown on desktop startup."""

from __future__ import annotations

import os
import shutil
import subprocess

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk  # noqa: E402


REPO_URL = "https://github.com/ma19031435-eng/OminX-Linux"


class ForceUpdateWindow(Gtk.Window):
    def __init__(self) -> None:
        super().__init__(title="OminX legacy build")
        self.set_position(Gtk.WindowPosition.CENTER_ALWAYS)
        self.set_border_width(28)
        self.set_resizable(False)
        self.set_decorated(False)
        self.fullscreen()
        self.set_modal(True)
        self.set_icon_name("software-update-available")
        self.set_keep_above(True)
        self.connect("delete-event", self._block_close)
        self.connect("key-press-event", self._block_keys)

        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        self.add(root)

        title = Gtk.Label(label="UPDATE REQUIRED")
        title.set_xalign(0)
        title.get_style_context().add_class("title")
        root.pack_start(title, False, False, 0)

        message = Gtk.Label(
            label=(
                "This image is blocked from normal use. You must update to the latest "
                "OminX ISO from this repository. Press the button below to open the "
                "repository page, then this session will sign out."
            )
        )
        message.set_xalign(0)
        message.set_line_wrap(True)
        root.pack_start(message, False, False, 0)

        repo = Gtk.Label(label=REPO_URL)
        repo.set_xalign(0)
        repo.set_selectable(True)
        root.pack_start(repo, False, False, 0)

        button = Gtk.Button(label="Open repository and sign out")
        button.connect("clicked", self._open_and_logout)
        root.pack_start(button, False, False, 0)

    @staticmethod
    def _block_close(*_args) -> bool:
        return True

    @staticmethod
    def _block_keys(*_args) -> bool:
        return True

    def _open_and_logout(self, _button) -> None:
        opener = shutil.which("xdg-open")
        if opener is not None:
            subprocess.Popen(
                [opener, REPO_URL],
                start_new_session=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        self._logout()

    @staticmethod
    def _run(command: list[str]) -> bool:
        try:
            result = subprocess.run(
                command,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
            )
        except OSError:
            return False
        return result.returncode == 0

    def _logout(self) -> None:
        if self._run(["qdbus", "org.kde.Shutdown", "/Shutdown", "org.kde.Shutdown.logout"]):
            return

        user = os.environ.get("USER")
        if user and self._run(["loginctl", "terminate-user", user]):
            return

        Gtk.main_quit()


def main() -> int:
    window = ForceUpdateWindow()
    window.show_all()
    Gtk.main()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
