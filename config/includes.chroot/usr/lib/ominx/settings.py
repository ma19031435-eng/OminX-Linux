#!/usr/bin/python3
"""OminX settings studio for native Cinnamon and Linux controls."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import GLib, Gtk  # noqa: E402

sys.path.insert(0, "/usr/lib/ominx")
from ui import apply_style, set_default_window_size  # noqa: E402


SETTINGS = {
    "Workspace": {
        "description": "Display, sound, notifications, power, and information about this system.",
        "items": [
            ("Display", "Resolution, scale, and connected monitors.", "video-display-symbolic", ["cinnamon-settings", "display"]),
            ("Sound", "Output, input, and audio devices.", "audio-volume-high-symbolic", ["cinnamon-settings", "sound"]),
            ("Notifications", "Choose which apps can send notifications.", "preferences-system-notifications-symbolic", ["cinnamon-settings", "notifications"]),
            ("Power", "Screen timeout and power behavior.", "system-shutdown-symbolic", ["cinnamon-settings", "power"]),
            ("About OminX", "View desktop and hardware information.", "computer-symbolic", ["cinnamon-settings", "info"]),
        ],
    },
    "Devices": {
        "description": "Connect accessories and manage input and print devices.",
        "items": [
            ("Bluetooth", "Pair headphones, keyboards, and other devices.", "bluetooth-symbolic", ["blueman-manager"]),
            ("Printers & scanners", "Add printers and configure scanning.", "printer-symbolic", ["system-config-printer"]),
            ("Mouse & touchpad", "Pointer speed, buttons, and touchpad behavior.", "input-mouse-symbolic", ["cinnamon-settings", "mouse"]),
            ("Keyboard", "Shortcuts, layouts, and typing options.", "input-keyboard-symbolic", ["cinnamon-settings", "keyboard"]),
        ],
    },
    "Connectivity": {
        "description": "Manage wired, wireless, VPN, and remote connections.",
        "items": [
            ("Network connections", "Edit Wi-Fi, Ethernet, VPN, and saved connections.", "network-wireless-symbolic", ["nm-connection-editor"]),
            ("Remote desktop", "Connect to another computer with Remmina.", "network-server-symbolic", ["remmina"]),
            ("Firewall", "Review incoming network access rules.", "security-high-symbolic", ["gufw"]),
        ],
    },
    "Appearance": {
        "description": "Shape the visual character of your workspace, panels, and lock screen.",
        "items": [
            ("Background", "Choose a desktop wallpaper and background style.", "preferences-desktop-wallpaper-symbolic", ["cinnamon-settings", "backgrounds"]),
            ("Themes & appearance", "Adjust colors, window borders, and desktop themes.", "preferences-desktop-theme-symbolic", ["cinnamon-settings", "themes"]),
            ("Panels & launcher", "Arrange desktop panels, applets, and the OminX launcher.", "view-grid-symbolic", ["cinnamon-settings", "panel"]),
            ("Lock screen", "Set screen locking and idle behavior.", "system-lock-screen-symbolic", ["cinnamon-settings", "screensaver"]),
        ],
    },
    "Applications": {
        "description": "Install software, manage startup apps, and review your library.",
        "items": [
            ("OminX Store", "Discover included apps and browse the full catalog.", "/usr/share/icons/hicolor/scalable/apps/ominx-store.svg", ["ominx-store"]),
            ("Installed apps", "Review installed Debian and Flatpak applications.", "applications-other-symbolic", ["gnome-software", "--mode=installed"]),
            ("Startup apps", "Choose which applications start with your session.", "system-run-symbolic", ["cinnamon-settings", "startup"]),
            ("Software updates", "Check for app and system package updates.", "software-update-available-symbolic", ["gnome-software", "--mode=updates"]),
        ],
    },
    "Accounts": {
        "description": "Manage local user accounts and session preferences.",
        "items": [
            ("Users & groups", "Open account and group settings.", "preferences-system-users-symbolic", ["cinnamon-settings", "user"]),
        ],
    },
    "Time & input": {
        "description": "Adjust date display, calendar preferences, and keyboard layouts.",
        "items": [
            ("Keyboard layouts", "Add or change input layouts and shortcuts.", "input-keyboard-symbolic", ["cinnamon-settings", "keyboard"]),
            ("Calendar & time display", "Set calendar and panel clock preferences.", "x-office-calendar-symbolic", ["cinnamon-settings", "calendar"]),
        ],
    },
    "Gaming": {
        "description": "Open your game library and per-game compatibility tools.",
        "items": [
            ("Steam", "Launch Steam; it downloads Proton after sign-in when needed.", "steam", ["steam"]),
            ("Lutris", "Organize game libraries and compatibility runners.", "lutris", ["lutris"]),
            ("Game Mode setup", "Read how to enable per-game tuning on supported hardware.", "applications-games-symbolic", ["ominx-welcome", "--game-mode"]),
        ],
    },
    "Accessibility": {
        "description": "Configure assistive features for vision, input, and navigation.",
        "items": [
            ("Accessibility", "Open keyboard, visual, and pointer assistance settings.", "preferences-desktop-accessibility-symbolic", ["cinnamon-settings", "accessibility"]),
            ("Screen reader", "Start Orca screen reading support.", "orca", ["orca"]),
        ],
    },
    "Privacy & security": {
        "description": "Review privacy controls and firewall protections.",
        "items": [
            ("Privacy", "Review desktop privacy and recent-file behavior.", "changes-prevent-symbolic", ["cinnamon-settings", "privacy"]),
            ("Firewall", "Configure the included uncomplicated firewall interface.", "security-high-symbolic", ["gufw"]),
            ("Security guidance", "Read the OminX compatibility and safety notes.", "dialog-information-symbolic", ["xdg-open", "/usr/share/doc/ominx/compatibility.md"]),
        ],
    },
    "Updates": {
        "description": "Keep applications and system packages current from their sources.",
        "items": [
            ("Check for updates", "Review available Debian and Flatpak updates.", "software-update-available-symbolic", ["gnome-software", "--mode=updates"]),
            ("Software sources", "Review application catalogs and repositories.", "network-server-symbolic", ["gnome-software", "--prefs"]),
        ],
    },
}

NAVIGATION = [
    ("Workspace", "computer-symbolic"),
    ("Devices", "bluetooth-symbolic"),
    ("Connectivity", "network-wireless-symbolic"),
    ("Appearance", "preferences-desktop-theme-symbolic"),
    ("Applications", "applications-other-symbolic"),
    ("Accounts", "preferences-system-users-symbolic"),
    ("Time & input", "x-office-calendar-symbolic"),
    ("Gaming", "applications-games-symbolic"),
    ("Accessibility", "preferences-desktop-accessibility-symbolic"),
    ("Privacy & security", "security-high-symbolic"),
    ("Updates", "software-update-available-symbolic"),
]


class SettingsWindow(Gtk.Window):
    def __init__(self) -> None:
        super().__init__(title="OminX Settings")
        set_default_window_size(self, 1080, 740)
        self.set_position(Gtk.WindowPosition.CENTER)
        self.set_icon_from_file("/usr/share/icons/hicolor/scalable/apps/ominx-settings.svg")
        self.active_category = "Workspace"
        self.nav_buttons: dict[str, Gtk.ToggleButton] = {}
        self._search_timeout_id = 0
        self._search_records = [
            (
                category,
                item,
                " ".join((category, item[0], item[1])).casefold(),
            )
            for category, group in SETTINGS.items()
            for item in group["items"]
        ]

        apply_style()
        self._build_shell()
        self.connect("destroy", self._on_destroy)
        self._render_page()
        self.show_all()

    def _build_shell(self) -> None:
        shell = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        shell.get_style_context().add_class("ominx-shell")
        self.add(shell)

        sidebar = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=7)
        sidebar.set_size_request(255, -1)
        sidebar.get_style_context().add_class("ominx-sidebar")
        shell.pack_start(sidebar, False, False, 0)

        brand = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        brand.set_margin_bottom(16)
        logo = Gtk.Image.new_from_file(
            "/usr/share/icons/hicolor/scalable/apps/ominx-settings.svg"
        )
        logo.set_pixel_size(36)
        brand.pack_start(logo, False, False, 0)
        brand_text = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=1)
        title = Gtk.Label(label="OminX Settings")
        title.set_xalign(0)
        title.get_style_context().add_class("ominx-brand")
        subtitle = Gtk.Label(label="Tune your workspace")
        subtitle.set_xalign(0)
        subtitle.get_style_context().add_class("ominx-brand-caption")
        brand_text.pack_start(title, False, False, 0)
        brand_text.pack_start(subtitle, False, False, 0)
        brand.pack_start(brand_text, True, True, 0)
        sidebar.pack_start(brand, False, False, 0)

        self.search_entry = Gtk.SearchEntry()
        self.search_entry.set_placeholder_text("Find a setting")
        self.search_entry.get_style_context().add_class("ominx-search")
        self.search_entry.connect("changed", self._on_search_changed)
        sidebar.pack_start(self.search_entry, False, False, 6)

        nav_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3)
        nav_box.get_style_context().add_class("ominx-navigation")
        for category, icon_name in NAVIGATION:
            button = Gtk.ToggleButton()
            row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
            icon = self._icon(icon_name, 18)
            row.pack_start(icon, False, False, 0)
            label = Gtk.Label(label=category)
            label.set_xalign(0)
            row.pack_start(label, True, True, 0)
            button.add(row)
            button.set_relief(Gtk.ReliefStyle.NONE)
            button.set_halign(Gtk.Align.FILL)
            button.connect("clicked", self._on_navigation, category)
            self.nav_buttons[category] = button
            nav_box.pack_start(button, False, False, 0)
        self.nav_buttons["Workspace"].set_active(True)
        sidebar.pack_start(nav_box, False, False, 0)

        sidebar_footer = Gtk.Label(label="OminX  ·  Desktop settings")
        sidebar_footer.set_xalign(0)
        sidebar_footer.get_style_context().add_class("ominx-muted")
        sidebar.pack_end(sidebar_footer, False, False, 8)

        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        content.set_hexpand(True)
        content.get_style_context().add_class("ominx-content")
        shell.pack_start(content, True, True, 0)

        header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        self.breadcrumb = Gtk.Label(label="Workspace")
        self.breadcrumb.set_xalign(0)
        self.breadcrumb.get_style_context().add_class("ominx-muted")
        header.pack_start(self.breadcrumb, True, True, 0)
        classic = Gtk.Button(label="Open Cinnamon settings")
        classic.get_style_context().add_class("ominx-secondary")
        classic.connect("clicked", lambda _button: self._launch(["cinnamon-settings"]))
        header.pack_end(classic, False, False, 0)
        content.pack_start(header, False, False, 0)

        separator = Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL)
        separator.get_style_context().add_class("ominx-divider")
        content.pack_start(separator, False, False, 0)

        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroll.set_vexpand(True)
        content.pack_start(scroll, True, True, 0)
        self.page_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=18)
        self.page_box.set_margin_end(16)
        self.page_box.set_margin_bottom(16)
        scroll.add(self.page_box)

    @staticmethod
    def _icon(icon_name: str, size: int = 42) -> Gtk.Image:
        if icon_name.startswith("/"):
            image = Gtk.Image.new_from_file(icon_name)
            image.set_pixel_size(size)
            return image
        theme = Gtk.IconTheme.get_default()
        if not theme.has_icon(icon_name):
            icon_name = "preferences-system-symbolic"
        image = Gtk.Image.new_from_icon_name(icon_name, Gtk.IconSize.DIALOG)
        image.set_pixel_size(size)
        return image

    def _on_navigation(self, _button: Gtk.ToggleButton, category: str) -> None:
        self.active_category = category
        self._set_active_navigation(category)
        self._clear_search()
        self._render_page()

    def _set_active_navigation(self, category: str) -> None:
        for nav_category, button in self.nav_buttons.items():
            button.set_active(nav_category == category)

    def _on_search_changed(self, _entry: Gtk.SearchEntry) -> None:
        self._cancel_search_refresh()
        self._search_timeout_id = GLib.timeout_add(
            85,
            self._apply_search,
        )

    def _apply_search(self) -> bool:
        self._search_timeout_id = 0
        self._render_page()
        return False

    def _cancel_search_refresh(self) -> None:
        if self._search_timeout_id:
            GLib.source_remove(self._search_timeout_id)
            self._search_timeout_id = 0

    def _clear_search(self) -> None:
        self._cancel_search_refresh()
        if self.search_entry.get_text():
            self.search_entry.set_text("")
        self._cancel_search_refresh()

    def _on_destroy(self, _window: Gtk.Window) -> None:
        self._cancel_search_refresh()

    def _render_page(self) -> None:
        for child in self.page_box.get_children():
            self.page_box.remove(child)

        query = self.search_entry.get_text().strip().casefold()
        if query:
            candidates = [
                (category, item)
                for category, item, search_text in self._search_records
                if query in search_text
            ]
            title = "Search results"
            subtitle = f"Settings matching ‘{self.search_entry.get_text().strip()}’."
            self.breadcrumb.set_text("Search")
        else:
            group = SETTINGS[self.active_category]
            candidates = [(self.active_category, item) for item in group["items"]]
            title = self.active_category
            subtitle = group["description"]
            self.breadcrumb.set_text(self.active_category)

        page_title = Gtk.Label(label=title)
        page_title.set_xalign(0)
        page_title.get_style_context().add_class("ominx-page-title")
        page_subtitle = Gtk.Label(label=subtitle)
        page_subtitle.set_xalign(0)
        page_subtitle.set_line_wrap(True)
        page_subtitle.get_style_context().add_class("ominx-copy")
        self.page_box.pack_start(page_title, False, False, 0)
        self.page_box.pack_start(page_subtitle, False, False, 0)

        if not query and self.active_category == "Workspace":
            self.page_box.pack_start(self._build_workspace_hero(), False, False, 4)

        if candidates:
            grid = Gtk.FlowBox()
            grid.set_selection_mode(Gtk.SelectionMode.NONE)
            grid.set_row_spacing(12)
            grid.set_column_spacing(12)
            grid.set_min_children_per_line(1)
            grid.set_max_children_per_line(2)
            grid.set_homogeneous(True)
            for category, item in candidates:
                grid.add(self._build_card(category, item))
            self.page_box.pack_start(grid, False, False, 8)
        else:
            self._show_no_results(query)

        if not query:
            note = Gtk.Label(
                label="Each page opens a native Cinnamon or Linux control. OminX gathers the essentials while preserving each component's own settings and behavior."
            )
            note.set_xalign(0)
            note.set_line_wrap(True)
            note.get_style_context().add_class("ominx-muted")
            self.page_box.pack_end(note, False, False, 8)

        self.page_box.show_all()

    def _build_workspace_hero(self) -> Gtk.Box:
        hero = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=18)
        hero.get_style_context().add_class("ominx-hero")

        copy = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=9)
        copy.set_hexpand(True)
        title = Gtk.Label(label="A workspace shaped around you")
        title.set_xalign(0)
        title.get_style_context().add_class("ominx-hero-title")
        description = Gtk.Label(
            label="Fine-tune the light, sound, and rhythm of your OminX desktop."
        )
        description.set_xalign(0)
        description.set_line_wrap(True)
        description.set_max_width_chars(54)
        description.get_style_context().add_class("ominx-hero-copy")
        copy.pack_start(title, False, False, 0)
        copy.pack_start(description, False, False, 0)

        appearance = Gtk.Button(label="Explore appearance")
        appearance.get_style_context().add_class("ominx-primary")
        appearance.set_halign(Gtk.Align.START)
        appearance.connect(
            "clicked",
            lambda _button: self.nav_buttons["Appearance"].clicked(),
        )
        copy.pack_start(appearance, False, False, 3)
        hero.pack_start(copy, True, True, 0)

        emblem = Gtk.Image.new_from_file(
            "/usr/share/icons/hicolor/scalable/apps/ominx.svg"
        )
        emblem.set_pixel_size(72)
        hero.pack_end(emblem, False, False, 4)
        return hero

    def _build_card(self, category: str, item: tuple) -> Gtk.Button:
        title, description, icon_name, command = item
        card = Gtk.Button()
        card.set_relief(Gtk.ReliefStyle.NONE)
        card.set_hexpand(True)
        card.set_size_request(300, 104)
        card.get_style_context().add_class("ominx-card")
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=14)
        icon = self._icon(icon_name)
        row.pack_start(icon, False, False, 0)

        copy_column = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
        copy_column.set_valign(Gtk.Align.CENTER)
        heading = Gtk.Label(label=title)
        heading.set_xalign(0)
        heading.get_style_context().add_class("ominx-card-title")
        text = Gtk.Label(label=description)
        text.set_xalign(0)
        text.set_line_wrap(True)
        text.set_max_width_chars(45)
        text.get_style_context().add_class("ominx-card-copy")
        copy_column.pack_start(heading, False, False, 0)
        copy_column.pack_start(text, False, False, 0)
        if self.search_entry.get_text().strip():
            context = Gtk.Label(label=category)
            context.set_xalign(0)
            context.get_style_context().add_class("ominx-muted")
            copy_column.pack_start(context, False, False, 0)
        row.pack_start(copy_column, True, True, 0)
        card.add(row)
        card.connect("clicked", self._on_card_clicked, command)
        return card

    def _show_no_results(self, query: str) -> None:
        message = Gtk.Label(label=f"No settings matched ‘{query}’. Open Cinnamon settings to browse the full control center.")
        message.set_xalign(0)
        message.set_line_wrap(True)
        message.get_style_context().add_class("ominx-copy")
        button = Gtk.Button(label="Open Cinnamon settings")
        button.set_halign(Gtk.Align.START)
        button.get_style_context().add_class("ominx-primary")
        button.connect("clicked", lambda _button: self._launch(["cinnamon-settings"]))
        self.page_box.pack_start(message, False, False, 8)
        self.page_box.pack_start(button, False, False, 0)

    def _on_card_clicked(self, _button: Gtk.Button, command: list[str]) -> None:
        self._launch(command)

    def _launch(self, command: list[str]) -> None:
        search_path = os.pathsep.join(
            filter(None, (os.environ.get("PATH", ""), "/usr/games", "/usr/local/games"))
        )
        executable = shutil.which(command[0], path=search_path)
        if executable is None:
            self._show_message(
                "Settings tool not found",
                f"{command[0]} is not available. Open the OminX Store to install additional software.",
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
            self._show_message("Could not open settings", str(error))

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


def main() -> int:
    Gtk.init(sys.argv)
    window = SettingsWindow()
    window.connect("destroy", lambda _window: Gtk.main_quit())
    if os.environ.get("OMINX_SMOKE_TEST") == "1":
        def close_smoke_window() -> bool:
            window.destroy()
            return False

        GLib.idle_add(close_smoke_window)
    Gtk.main()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
