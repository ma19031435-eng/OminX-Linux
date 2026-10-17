#!/usr/bin/python3
"""Shared original OminX styling for the GTK desktop hubs."""

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
