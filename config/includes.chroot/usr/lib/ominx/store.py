#!/usr/bin/python3
"""Original OminX storefront UI backed by Debian and Flatpak software sources."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gio", "2.0")
from gi.repository import GLib, Gio, Gtk, Pango  # noqa: E402

sys.path.insert(0, "/usr/lib/ominx")
from ui import apply_style, set_default_window_size  # noqa: E402


PRODUCTS = [
    {
        "name": "Files",
        "description": "Browse folders, devices, and network locations.",
        "category": "Productivity",
        "icon": "system-file-manager",
        "desktop_id": "nemo.desktop",
    },
    {
        "name": "Firefox ESR",
        "description": "A fast, privacy-minded browser for everyday use.",
        "category": "Internet",
        "icon": "firefox-esr",
        "desktop_id": "firefox-esr.desktop",
    },
    {
        "name": "LibreOffice Writer",
        "description": "Create letters, reports, and other documents.",
        "category": "Productivity",
        "icon": "libreoffice-writer",
        "desktop_id": "libreoffice-writer.desktop",
    },
    {
        "name": "VLC Media Player",
        "description": "Play a wide range of audio and video formats.",
        "category": "Media",
        "icon": "vlc",
        "desktop_id": "vlc.desktop",
    },
    {
        "name": "GIMP",
        "description": "Edit photos and create original artwork.",
        "category": "Creativity",
        "icon": "org.gimp.GIMP",
        "desktop_id": "org.gimp.GIMP.desktop",
    },
    {
        "name": "Inkscape",
        "description": "Draw and edit scalable vector graphics.",
        "category": "Creativity",
        "icon": "org.inkscape.Inkscape",
        "desktop_id": "org.inkscape.Inkscape.desktop",
    },
    {
        "name": "Steam",
        "description": "Open your PC game library; Proton is managed by Steam.",
        "category": "Games",
        "icon": "steam",
        "desktop_id": "steam.desktop",
    },
    {
        "name": "Lutris",
        "description": "Organize game libraries and compatibility runners.",
        "category": "Games",
        "icon": "net.lutris.Lutris",
        "desktop_id": "net.lutris.Lutris.desktop",
    },
]

CATEGORY_SEARCHES = {
    "Productivity": "office productivity",
    "Internet": "web browser internet",
    "Creativity": "graphics drawing photo editor",
    "Media": "audio video media player",
    "Games": "games",
}

NAVIGATION = [
    ("home", "Home", "go-home-symbolic"),
    ("apps", "Apps", "view-grid-symbolic"),
    ("games", "Games", "applications-games-symbolic"),
    ("library", "Library", "folder-symbolic"),
    ("updates", "Updates", "software-update-available-symbolic"),
]


class StoreWindow(Gtk.Window):
    def __init__(self) -> None:
        super().__init__(title="OminX Store")
        set_default_window_size(self, 1120, 760)
        self.set_position(Gtk.WindowPosition.CENTER)
        self.set_icon_from_file("/usr/share/icons/hicolor/scalable/apps/ominx-store.svg")
        self.active_page = "home"
        self.category_filter = "All"
        self.nav_buttons: dict[str, Gtk.ToggleButton] = {}
        self._search_timeout_id = 0

        apply_style()
        self._build_shell()
        self.connect("destroy", self._on_destroy)
        self._render_page()
        self.show_all()

    def _build_shell(self) -> None:
        shell = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        shell.get_style_context().add_class("ominx-shell")
        self.add(shell)

        sidebar = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        sidebar.set_size_request(220, -1)
        sidebar.get_style_context().add_class("ominx-sidebar")
        shell.pack_start(sidebar, False, False, 0)

        brand = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        brand.set_margin_bottom(22)
        logo = Gtk.Image.new_from_file(
            "/usr/share/icons/hicolor/scalable/apps/ominx-store.svg"
        )
        logo.set_pixel_size(34)
        brand.pack_start(logo, False, False, 0)
        brand_text = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=1)
        title = Gtk.Label(label="OminX Store")
        title.set_xalign(0)
        title.get_style_context().add_class("ominx-brand")
        caption = Gtk.Label(label="Apps · games · tools")
        caption.set_xalign(0)
        caption.get_style_context().add_class("ominx-brand-caption")
        brand_text.pack_start(title, False, False, 0)
        brand_text.pack_start(caption, False, False, 0)
        brand.pack_start(brand_text, True, True, 0)
        sidebar.pack_start(brand, False, False, 0)

        nav_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        nav_box.get_style_context().add_class("ominx-navigation")
        for page, label, icon_name in NAVIGATION:
            button = Gtk.ToggleButton()
            row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
            icon = Gtk.Image.new_from_icon_name(icon_name, Gtk.IconSize.MENU)
            row.pack_start(icon, False, False, 0)
            text = Gtk.Label(label=label)
            text.set_xalign(0)
            row.pack_start(text, True, True, 0)
            button.add(row)
            button.set_halign(Gtk.Align.FILL)
            button.set_relief(Gtk.ReliefStyle.NONE)
            button.connect("clicked", self._on_navigation, page)
            self.nav_buttons[page] = button
            nav_box.pack_start(button, False, False, 0)
        self.nav_buttons["home"].set_active(True)
        sidebar.pack_start(nav_box, False, False, 0)
        sidebar.pack_start(Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL), False, False, 5)

        source_note = Gtk.Label(label="Debian packages\nFlathub catalog")
        source_note.set_xalign(0)
        source_note.set_line_wrap(True)
        source_note.get_style_context().add_class("ominx-muted")
        sidebar.pack_start(source_note, False, False, 2)
        sidebar.pack_end(Gtk.Box(), True, True, 0)

        settings_button = Gtk.Button()
        settings_button.set_relief(Gtk.ReliefStyle.NONE)
        settings_button.get_style_context().add_class("ominx-flat-button")
        settings_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        settings_row.pack_start(
            Gtk.Image.new_from_icon_name("preferences-system-symbolic", Gtk.IconSize.MENU),
            False,
            False,
            0,
        )
        settings_row.pack_start(Gtk.Label(label="OminX Settings"), True, True, 0)
        settings_button.add(settings_row)
        settings_button.connect("clicked", lambda _button: self._launch_command(["ominx-settings"]))
        sidebar.pack_end(settings_button, False, False, 0)

        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        content.set_hexpand(True)
        content.get_style_context().add_class("ominx-content")
        shell.pack_start(content, True, True, 0)

        toolbar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        self.search_entry = Gtk.SearchEntry()
        self.search_entry.set_placeholder_text("Search apps, games, and tools")
        self.search_entry.set_hexpand(True)
        self.search_entry.get_style_context().add_class("ominx-search")
        self.search_entry.connect("changed", self._on_search_changed)
        self.search_entry.connect("activate", self._on_search_activate)
        toolbar.pack_start(self.search_entry, True, True, 0)

        updates_button = Gtk.Button(label="Updates")
        updates_button.get_style_context().add_class("ominx-secondary")
        updates_button.connect("clicked", lambda _button: self._show_page("updates"))
        toolbar.pack_start(updates_button, False, False, 0)

        content.pack_start(toolbar, False, False, 0)
        separator = Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL)
        separator.get_style_context().add_class("ominx-divider")
        content.pack_start(separator, False, False, 0)

        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroll.set_vexpand(True)
        content.pack_start(scroll, True, True, 0)
        self.page_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        self.page_box.set_margin_bottom(18)
        scroll.add(self.page_box)

    def _on_navigation(self, _button: Gtk.ToggleButton, page: str) -> None:
        self.active_page = page
        self.category_filter = "All"
        self._set_active_navigation(page)
        self._clear_search()
        self._render_page()

    def _set_active_navigation(self, page: str) -> None:
        for nav_page, button in self.nav_buttons.items():
            button.set_active(nav_page == page)

    def _show_page(self, page: str) -> None:
        self.active_page = page
        self.category_filter = "All"
        self._clear_search()
        if page in self.nav_buttons:
            self._set_active_navigation(page)
        self._render_page()

    def _on_search_changed(self, _entry: Gtk.SearchEntry) -> None:
        self._cancel_search_refresh()
        self._search_timeout_id = GLib.timeout_add(
            85,
            self._apply_search,
        )

    def _apply_search(self) -> bool:
        self._search_timeout_id = 0
        query = self.search_entry.get_text().strip()
        if query:
            self._render_search(query)
        else:
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

    def _on_search_activate(self, entry: Gtk.SearchEntry) -> None:
        self._cancel_search_refresh()
        query = entry.get_text().strip()
        if query:
            self._launch_software(search=query)
        else:
            self._show_page("apps")

    def _clear_page(self) -> None:
        for child in self.page_box.get_children():
            self.page_box.remove(child)

    def _render_page(self) -> None:
        self._clear_page()
        page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=18)
        page.set_margin_end(16)
        page.get_style_context().add_class("ominx-page")

        if self.active_page == "home":
            self._render_home(page)
        elif self.active_page == "apps":
            self._render_apps(page)
        elif self.active_page == "games":
            self._render_games(page)
        elif self.active_page == "library":
            self._render_library(page)
        elif self.active_page == "updates":
            self._render_updates(page)

        self.page_box.pack_start(page, True, True, 0)
        self.page_box.show_all()

    def _render_search(self, query: str) -> None:
        self._clear_page()
        page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=18)
        page.set_margin_end(16)
        self._add_heading(page, f"Results for ‘{query}’", "Search the included picks or press Enter to search the full Debian and Flathub catalog.")
        matches = [
            product
            for product in PRODUCTS
            if query.casefold()
            in " ".join(
                (product["name"], product["description"], product["category"])
            ).casefold()
        ]
        if matches:
            page.pack_start(self._build_product_grid(matches), False, False, 0)
        else:
            self._add_empty_state(
                page,
                "No matching featured apps",
                "Press Enter or choose Browse the full catalog to search the connected software sources.",
                "Browse the full catalog",
                lambda: self._launch_software(search=query),
            )
        if matches:
            self._add_action_row(
                page,
                "Looking for something else?",
                "Search the complete software catalog from Debian and Flathub.",
                "Browse full catalog",
                lambda: self._launch_software(search=query),
            )
        self.page_box.pack_start(page, True, True, 0)
        self.page_box.show_all()

    def _render_home(self, page: Gtk.Box) -> None:
        self._add_heading(page, "Discover apps for OminX", "Find tools for work, creativity, everyday tasks, and play.")

        hero = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=24)
        hero.get_style_context().add_class("ominx-hero")
        hero_left = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        hero_left.set_hexpand(True)
        headline = Gtk.Label(label="Make your desktop yours")
        headline.set_xalign(0)
        headline.get_style_context().add_class("ominx-hero-title")
        copy = Gtk.Label(
            label="Browse a curated starting point, then search the full Debian and Flathub catalog when you want more."
        )
        copy.set_xalign(0)
        copy.set_line_wrap(True)
        copy.set_max_width_chars(66)
        copy.get_style_context().add_class("ominx-hero-copy")
        hero_left.pack_start(headline, False, False, 0)
        hero_left.pack_start(copy, False, False, 0)
        browse = Gtk.Button(label="Browse all apps")
        browse.get_style_context().add_class("ominx-primary")
        browse.set_halign(Gtk.Align.START)
        browse.connect("clicked", lambda _button: self._launch_software())
        hero_left.pack_start(browse, False, False, 4)
        hero.pack_start(hero_left, True, True, 0)

        emblem = Gtk.Image.new_from_file(
            "/usr/share/icons/hicolor/scalable/apps/ominx-store.svg"
        )
        emblem.set_pixel_size(96)
        hero.pack_end(emblem, False, False, 8)
        page.pack_start(hero, False, False, 0)

        self._add_section_title(page, "Explore a category")
        chips = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        for category in ("Productivity", "Internet", "Creativity", "Media", "Games"):
            chip = Gtk.Button(label=category)
            chip.get_style_context().add_class("ominx-chip")
            chip.connect("clicked", self._open_category, category)
            chips.pack_start(chip, False, False, 0)
        page.pack_start(chips, False, False, 0)

        self._add_section_title(page, "Popular on OminX")
        page.pack_start(
            self._build_product_grid(
                [
                    self._get_product("Firefox ESR"),
                    self._get_product("LibreOffice Writer"),
                    self._get_product("Steam"),
                ]
            ),
            False,
            False,
            0,
        )
        self._add_action_row(
            page,
            "Your apps and updates",
            "Review installed software, check updates, or manage software sources.",
            "Open library",
            lambda: self._show_page("library"),
        )

    def _render_apps(self, page: Gtk.Box) -> None:
        self._add_heading(page, "Apps", "Useful apps included with OminX, plus a path to the full catalog.")
        chip_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        categories = ["All", "Productivity", "Internet", "Creativity", "Media", "Games"]
        for category in categories:
            chip = Gtk.ToggleButton(label=category)
            chip.get_style_context().add_class("ominx-chip")
            chip.set_active(category == self.category_filter)
            chip.connect("clicked", self._set_category, category)
            chip_row.pack_start(chip, False, False, 0)
        page.pack_start(chip_row, False, False, 0)

        products = PRODUCTS
        if self.category_filter != "All":
            products = [item for item in PRODUCTS if item["category"] == self.category_filter]
        page.pack_start(self._build_product_grid(products), False, False, 0)
        self._add_action_row(
            page,
            "Need another app?",
            "Search software from Debian and the configured Flathub catalog.",
            "Search catalog",
            lambda: self._launch_software(
                search=CATEGORY_SEARCHES.get(self.category_filter)
            ),
        )

    def _render_games(self, page: Gtk.Box) -> None:
        self._add_heading(page, "Games", "Game launchers and tools ready for your library.")
        game_apps = [item for item in PRODUCTS if item["category"] == "Games"]
        page.pack_start(self._build_product_grid(game_apps), False, False, 0)
        self._add_action_row(
            page,
            "Compatibility tools",
            "OminX includes Wine, Lutris, Winetricks, Proton support through Steam, and per-game GameMode.",
            "Read gaming guide",
            lambda: self._open_document("/usr/share/doc/ominx/compatibility.md"),
        )
        self._add_action_row(
            page,
            "Explore more games",
            "Browse available game tools and launchers from the connected software sources.",
            "Browse catalog",
            lambda: self._launch_software(search="games"),
        )

    def _render_library(self, page: Gtk.Box) -> None:
        self._add_heading(page, "Library", "Manage installed apps, available updates, and software sources.")
        self._add_action_row(
            page,
            "Installed apps",
            "View software installed from Debian packages and Flatpak.",
            "View installed apps",
            lambda: self._launch_software(mode="installed"),
        )
        self._add_action_row(
            page,
            "Software updates",
            "Check for updates from your configured software sources.",
            "Check for updates",
            lambda: self._launch_software(mode="updates"),
        )
        self._add_action_row(
            page,
            "Software sources",
            "Review available repositories and application sources.",
            "Manage sources",
            lambda: self._launch_software(prefs=True),
        )
        self._add_section_title(page, "Included with OminX")
        page.pack_start(self._build_product_grid(PRODUCTS), False, False, 0)

    def _render_updates(self, page: Gtk.Box) -> None:
        self._add_heading(page, "Updates", "Keep installed software current through its trusted source.")
        self._add_empty_state(
            page,
            "Review available updates",
            "The software manager checks package and Flatpak updates and shows their origin before installation.",
            "Open update center",
            lambda: self._launch_software(mode="updates"),
        )
        self._add_action_row(
            page,
            "Update settings",
            "Review application sources and update preferences.",
            "Manage sources",
            lambda: self._launch_software(prefs=True),
        )

    def _add_heading(self, parent: Gtk.Box, title: str, subtitle: str) -> None:
        heading = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
        label = Gtk.Label(label=title)
        label.set_xalign(0)
        label.get_style_context().add_class("ominx-page-title")
        copy = Gtk.Label(label=subtitle)
        copy.set_xalign(0)
        copy.set_line_wrap(True)
        copy.get_style_context().add_class("ominx-copy")
        heading.pack_start(label, False, False, 0)
        heading.pack_start(copy, False, False, 0)
        parent.pack_start(heading, False, False, 0)

    def _add_section_title(self, parent: Gtk.Box, text: str) -> None:
        title = Gtk.Label(label=text)
        title.set_xalign(0)
        title.get_style_context().add_class("ominx-section-title")
        parent.pack_start(title, False, False, 0)

    def _build_product_grid(self, products: list[dict[str, str]]) -> Gtk.FlowBox:
        grid = Gtk.FlowBox()
        grid.set_selection_mode(Gtk.SelectionMode.NONE)
        grid.set_row_spacing(12)
        grid.set_column_spacing(12)
        grid.set_min_children_per_line(1)
        grid.set_max_children_per_line(3)
        grid.set_homogeneous(True)
        for product in products:
            child = Gtk.FlowBoxChild()
            child.set_valign(Gtk.Align.FILL)
            child.add(self._build_product_card(product))
            grid.add(child)
        return grid

    def _build_product_card(self, product: dict[str, str]) -> Gtk.Frame:
        frame = Gtk.Frame()
        frame.set_shadow_type(Gtk.ShadowType.NONE)
        frame.set_size_request(240, 180)
        frame.get_style_context().add_class("ominx-card")

        body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        body.set_margin_top(13)
        body.set_margin_bottom(13)
        body.set_margin_start(13)
        body.set_margin_end(13)
        frame.add(body)

        top = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=11)
        icon_name = product["icon"]
        if not Gtk.IconTheme.get_default().has_icon(icon_name):
            icon_name = "application-x-executable"
        icon = Gtk.Image.new_from_icon_name(icon_name, Gtk.IconSize.DIALOG)
        icon.set_pixel_size(44)
        top.pack_start(icon, False, False, 0)
        text_column = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3)
        title = Gtk.Label(label=product["name"])
        title.set_xalign(0)
        title.set_ellipsize(Pango.EllipsizeMode.END)
        title.get_style_context().add_class("ominx-card-title")
        category = Gtk.Label(label=product["category"])
        category.set_xalign(0)
        category.get_style_context().add_class("ominx-muted")
        text_column.pack_start(title, False, False, 0)
        text_column.pack_start(category, False, False, 0)
        top.pack_start(text_column, True, True, 0)
        body.pack_start(top, False, False, 0)

        description = Gtk.Label(label=product["description"])
        description.set_xalign(0)
        description.set_yalign(0)
        description.set_line_wrap(True)
        description.set_max_width_chars(38)
        description.get_style_context().add_class("ominx-card-copy")
        body.pack_start(description, True, True, 0)

        footer = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        badge = Gtk.Label(label="Included")
        badge.get_style_context().add_class("ominx-pill")
        footer.pack_start(badge, False, False, 0)
        footer.pack_end(Gtk.Box(), True, True, 0)
        desktop_info = self._desktop_app_info(product["desktop_id"])
        button = Gtk.Button(label="Open" if desktop_info is not None else "Find")
        button.get_style_context().add_class("ominx-primary")
        button.connect("clicked", self._open_product, product)
        footer.pack_end(button, False, False, 0)
        body.pack_end(footer, False, False, 0)
        return frame

    def _add_action_row(
        self,
        parent: Gtk.Box,
        title_text: str,
        copy_text: str,
        button_text: str,
        callback,
    ) -> None:
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=16)
        row.get_style_context().add_class("ominx-card")
        copy_column = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        copy_column.set_hexpand(True)
        title = Gtk.Label(label=title_text)
        title.set_xalign(0)
        title.get_style_context().add_class("ominx-card-title")
        copy = Gtk.Label(label=copy_text)
        copy.set_xalign(0)
        copy.set_line_wrap(True)
        copy.get_style_context().add_class("ominx-card-copy")
        copy_column.pack_start(title, False, False, 0)
        copy_column.pack_start(copy, False, False, 0)
        row.pack_start(copy_column, True, True, 0)
        button = Gtk.Button(label=button_text)
        button.get_style_context().add_class("ominx-secondary")
        button.connect("clicked", lambda _button: callback())
        row.pack_end(button, False, False, 0)
        parent.pack_start(row, False, False, 0)

    def _add_empty_state(
        self,
        parent: Gtk.Box,
        title_text: str,
        copy_text: str,
        button_text: str,
        callback,
    ) -> None:
        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        card.get_style_context().add_class("ominx-card")
        title = Gtk.Label(label=title_text)
        title.set_xalign(0)
        title.get_style_context().add_class("ominx-card-title")
        copy = Gtk.Label(label=copy_text)
        copy.set_xalign(0)
        copy.set_line_wrap(True)
        copy.get_style_context().add_class("ominx-card-copy")
        button = Gtk.Button(label=button_text)
        button.set_halign(Gtk.Align.START)
        button.get_style_context().add_class("ominx-primary")
        button.connect("clicked", lambda _button: callback())
        card.pack_start(title, False, False, 0)
        card.pack_start(copy, False, False, 0)
        card.pack_start(button, False, False, 2)
        parent.pack_start(card, False, False, 0)

    @staticmethod
    def _get_product(name: str) -> dict[str, str]:
        return next(product for product in PRODUCTS if product["name"] == name)

    @staticmethod
    def _desktop_app_info(desktop_id: str):
        try:
            return Gio.DesktopAppInfo.new(desktop_id)
        except TypeError:
            return None

    def _open_category(self, _button: Gtk.Button, category: str) -> None:
        self._show_page("apps")
        self.category_filter = category
        self._render_page()

    def _set_category(self, _button: Gtk.ToggleButton, category: str) -> None:
        self.category_filter = category
        self._render_page()

    def _open_product(self, _button: Gtk.Button, product: dict[str, str]) -> None:
        desktop_info = self._desktop_app_info(product["desktop_id"])
        if desktop_info is None:
            self._launch_software(search=product["name"])
            return
        try:
            desktop_info.launch([], None)
        except GLib.Error as error:
            self._show_message("Could not open app", str(error))

    def _launch_software(self, search: str | None = None, mode: str | None = None, prefs: bool = False) -> None:
        executable = shutil.which("gnome-software")
        if executable is None:
            self._show_message(
                "Software manager not found",
                "GNOME Software is the package and Flatpak installation backend for OminX Store.",
            )
            return
        command = [executable]
        if search:
            command.append(f"--search={search}")
        elif mode:
            command.append(f"--mode={mode}")
        elif prefs:
            command.append("--prefs")
        try:
            subprocess.Popen(
                command,
                env=os.environ.copy(),
                start_new_session=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except OSError as error:
            self._show_message("Could not open software manager", str(error))

    def _launch_command(self, command: list[str]) -> None:
        executable = shutil.which(command[0])
        if executable is None:
            self._show_message("App not found", f"{command[0]} is not available in this OminX installation.")
            return
        try:
            subprocess.Popen(
                [executable, *command[1:]],
                env=os.environ.copy(),
                start_new_session=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except OSError as error:
            self._show_message("Could not open app", str(error))

    def _open_document(self, path: str) -> None:
        try:
            subprocess.Popen(
                ["xdg-open", path],
                start_new_session=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except OSError as error:
            self._show_message("Could not open guide", str(error))

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
    window = StoreWindow()
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
