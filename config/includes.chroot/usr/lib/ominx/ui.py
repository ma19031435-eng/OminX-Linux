#!/usr/bin/python3
"""Shared original OminX styling and comfortable native window sizing."""

from pathlib import Path

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gdk, Gtk  # noqa: E402

STYLE_PATH = Path("/usr/share/ominx/ui/ominx-ui.css")


def apply_style() -> None:
    provider = Gtk.CssProvider()
    if not provider.load_from_path(str(STYLE_PATH)):
        raise RuntimeError(f"Unable to load OminX style from {STYLE_PATH}")
    screen = Gdk.Screen.get_default()
    if screen is not None:
        Gtk.StyleContext.add_provider_for_screen(
            screen, provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )


def set_default_window_size(window: Gtk.Window, preferred_width: int, preferred_height: int) -> None:
    """Open app hubs at a useful, screen-aware size without a maximize redraw."""
    screen = Gdk.Screen.get_default()
    if screen is None:
        window.set_default_size(preferred_width, preferred_height)
        return

    available_width = max(560, screen.get_width() - 72)
    available_height = max(420, screen.get_height() - 108)
    window.set_default_size(
        min(preferred_width, available_width),
        min(preferred_height, available_height),
    )
