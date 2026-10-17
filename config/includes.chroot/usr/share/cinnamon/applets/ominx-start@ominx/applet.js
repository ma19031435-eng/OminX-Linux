const Applet = imports.ui.applet;
const Clutter = imports.gi.Clutter;
const Gio = imports.gi.Gio;
const GLib = imports.gi.GLib;
const Lang = imports.lang;
const Main = imports.ui.main;
const PopupMenu = imports.ui.popupMenu;
const St = imports.gi.St;
const Util = imports.misc.util;

const START_ICON = "/usr/share/icons/hicolor/scalable/apps/ominx-start.svg";
const PINNED_APPS = [
    { id: "nemo.desktop", name: "Files", icon: "system-file-manager" },
    { id: "firefox-esr.desktop", name: "Firefox ESR", icon: "firefox-esr" },
    { id: "ominx-store.desktop", name: "OminX Store", icon: "ominx-store" },
    { id: "libreoffice-writer.desktop", name: "Writer", icon: "libreoffice-writer" },
    { id: "ominx-settings.desktop", name: "Settings", icon: "ominx-settings" },
    { id: "vlc.desktop", name: "VLC media player", icon: "vlc" },
    { id: "steam.desktop", name: "Steam", icon: "steam" },
    { id: "net.lutris.Lutris.desktop", name: "Lutris", icon: "lutris" }
];

class OminXStartApplet extends Applet.IconApplet {
    constructor(orientation, panelHeight, instanceId) {
        super(orientation, panelHeight, instanceId);

        this.setAllowedLayout(Applet.AllowedLayout.BOTH);
        this.set_applet_icon_path(START_ICON);
        this.set_applet_tooltip("OminX Start");

        this.menuManager = new PopupMenu.PopupMenuManager(this);
        this.menu = new Applet.AppletPopupMenu(this, orientation);
        this.menu.setCustomStyleClass("ominx-start-menu");
        this.menuManager.addMenu(this.menu);

        this.pinnedApps = PINNED_APPS.map(item => ({
            id: item.id,
            name: item.name,
            icon: item.icon,
            appInfo: Gio.DesktopAppInfo.new(item.id)
        }));
        this.allApps = this._getAllApps();
        this.showAllApps = false;
        this.currentResults = [];

        this._buildMenu();
        this.menu.connect("open-state-changed", Lang.bind(this, this._onOpenStateChanged));
        this.keybindingName = "ominx-start-open-" + instanceId;
        Main.keybindingManager.addHotKey(this.keybindingName, "Super_L", Lang.bind(this, this._openMenu));
    }

    _buildMenu() {
        this.root = new St.BoxLayout({
            vertical: true,
            style_class: "ominx-start-root"
        });
        this.menu.addActor(this.root);

        const header = new St.BoxLayout({
            vertical: false,
            style_class: "ominx-start-header",
            x_expand: true
        });
        const brand = new St.BoxLayout({ vertical: true, style_class: "ominx-start-brand-block", x_expand: true });
        const brandName = new St.Label({ text: "OminX", style_class: "ominx-start-brand" });
        const brandCaption = new St.Label({
            text: "Your desktop, your way",
            style_class: "ominx-start-subtitle"
        });
        brand.add_actor(brandName);
        brand.add_actor(brandCaption);
        header.add_actor(brand);

        this.viewButton = new St.Button({
            style_class: "ominx-start-link",
            can_focus: true
        });
        this.viewButtonText = new St.Label({ text: "All apps  ›" });
        this.viewButton.set_child(this.viewButtonText);
        this.viewButton.connect("clicked", Lang.bind(this, this._toggleAppView));
        header.add_actor(this.viewButton);
        this.root.add_actor(header);

        this.searchEntry = new St.Entry({
            name: "ominx-start-search",
            hint_text: "Search apps",
            style_class: "ominx-start-search",
            can_focus: true
        });
        this.searchEntry.clutter_text.connect("text-changed", Lang.bind(this, this._onSearchChanged));
        this.searchEntry.clutter_text.connect("activate", Lang.bind(this, this._onSearchActivated));
        this.root.add_actor(this.searchEntry);

        this.homeBox = new St.BoxLayout({ vertical: true, style_class: "ominx-start-home" });
        this._buildHome();
        this.root.add_actor(this.homeBox);

        this.resultsScroll = new St.ScrollView({ style_class: "ominx-start-results-scroll" });
        this.resultsScroll.set_policy(St.PolicyType.NEVER, St.PolicyType.AUTOMATIC);
        this.resultsScroll.set_height(352);
        this.resultsBox = new St.BoxLayout({ vertical: true, style_class: "ominx-start-results" });
        this.resultsScroll.add_actor(this.resultsBox);
        this.resultsScroll.hide();
        this.root.add_actor(this.resultsScroll);

        const footer = new St.BoxLayout({
            vertical: false,
            style_class: "ominx-start-footer",
            x_expand: true
        });
        const profile = new St.BoxLayout({
            vertical: false,
            style_class: "ominx-start-profile",
            y_align: Clutter.ActorAlign.CENTER
        });
        const initial = new St.Label({ text: "O", style_class: "ominx-start-avatar" });
        const userName = GLib.get_real_name() || GLib.get_user_name() || "OminX user";
        const userLabel = new St.Label({ text: userName, style_class: "ominx-start-user" });
        profile.add_actor(initial);
        profile.add_actor(userLabel);
        footer.add_actor(profile);
        this.root.add_actor(footer);

        const power = new PopupMenu.PopupSubMenuMenuItem("Power options");
        const lockItem = new PopupMenu.PopupMenuItem("Lock screen");
        lockItem.connect("activate", Lang.bind(this, this._runSessionCommand, "cinnamon-screensaver-command --lock"));
        power.menu.addMenuItem(lockItem);
        const signOutItem = new PopupMenu.PopupMenuItem("Sign out");
        signOutItem.connect("activate", Lang.bind(this, this._runSessionCommand, "cinnamon-session-quit --logout"));
        power.menu.addMenuItem(signOutItem);
        const shutdownItem = new PopupMenu.PopupMenuItem("Shut down or restart…");
        shutdownItem.connect("activate", Lang.bind(this, this._runSessionCommand, "cinnamon-session-quit --power-off"));
        power.menu.addMenuItem(shutdownItem);
        this.menu.addMenuItem(power);
    }

    _buildHome() {
        const pinnedHeading = new St.BoxLayout({
            vertical: false,
            style_class: "ominx-start-section-heading",
            x_expand: true
        });
        pinnedHeading.add_actor(new St.Label({ text: "Pinned", style_class: "ominx-start-section-title" }));
        pinnedHeading.add_actor(new St.Label({ text: "Your everyday apps", style_class: "ominx-start-section-note" }));
        this.homeBox.add_actor(pinnedHeading);

        const grid = new St.BoxLayout({ vertical: true, style_class: "ominx-start-grid" });
        for (let rowIndex = 0; rowIndex < 2; rowIndex++) {
            const row = new St.BoxLayout({ vertical: false, style_class: "ominx-start-grid-row" });
            for (let columnIndex = 0; columnIndex < 4; columnIndex++) {
                const app = this.pinnedApps[rowIndex * 4 + columnIndex];
                row.add_actor(this._createPinnedButton(app));
            }
            grid.add_actor(row);
        }
        this.homeBox.add_actor(grid);

        const recommendedHeading = new St.Label({
            text: "Recommended",
            style_class: "ominx-start-section-title ominx-start-recommended-heading"
        });
        this.homeBox.add_actor(recommendedHeading);

        const recommendations = new St.BoxLayout({ vertical: true, style_class: "ominx-start-recommendations" });
        recommendations.add_actor(this._createRecommendation(
            "ominx-settings.desktop",
            "OminX Settings",
            "Personalize your desktop and devices",
            "ominx-settings"
        ));
        recommendations.add_actor(this._createRecommendation(
            "ominx-store.desktop",
            "Discover more apps",
            "Browse the OminX software catalog",
            "ominx-store"
        ));
        this.homeBox.add_actor(recommendations);
    }

    _createPinnedButton(app) {
        const button = new St.Button({
            style_class: "ominx-start-app-button",
            can_focus: true,
            reactive: true,
            x_expand: true,
            y_expand: true
        });
        const contents = new St.BoxLayout({
            vertical: true,
            style_class: "ominx-start-app-contents",
            x_align: Clutter.ActorAlign.CENTER,
            y_align: Clutter.ActorAlign.CENTER
        });
        contents.add_actor(this._createIcon(app.appInfo, app.icon, 34));
        contents.add_actor(new St.Label({
            text: app.name,
            style_class: "ominx-start-app-label"
        }));
        button.set_child(contents);
        button.connect("clicked", Lang.bind(this, this._launchApp, app));
        return button;
    }

    _createRecommendation(appId, title, description, iconName) {
        const appInfo = Gio.DesktopAppInfo.new(appId);
        const row = new St.Button({
            style_class: "ominx-start-recommendation",
            can_focus: true,
            reactive: true,
            x_expand: true
        });
        const contents = new St.BoxLayout({ vertical: false, style_class: "ominx-start-recommendation-content" });
        contents.add_actor(this._createIcon(appInfo, iconName, 28));
        const text = new St.BoxLayout({ vertical: true, style_class: "ominx-start-recommendation-copy" });
        text.add_actor(new St.Label({ text: title, style_class: "ominx-start-recommendation-title" }));
        text.add_actor(new St.Label({ text: description, style_class: "ominx-start-recommendation-description" }));
        contents.add_actor(text);
        row.set_child(contents);
        row.connect("clicked", Lang.bind(this, this._launchApp, {
            id: appId,
            name: title,
            appInfo: appInfo
        }));
        return row;
    }

    _createIcon(appInfo, fallbackIcon, size) {
        const icon = appInfo ? appInfo.get_icon() : null;
        if (icon) {
            return new St.Icon({
                gicon: icon,
                icon_size: size,
                icon_type: St.IconType.FULLCOLOR,
                style_class: "ominx-start-app-icon"
            });
        }
        return new St.Icon({
            icon_name: fallbackIcon || "application-x-executable-symbolic",
            icon_size: size,
            icon_type: St.IconType.FULLCOLOR,
            style_class: "ominx-start-app-icon"
        });
    }

    _getAllApps() {
        let applications = [];
        try {
            applications = Gio.AppInfo.get_all()
                .filter(appInfo => appInfo.should_show() && appInfo.get_name())
                .sort((left, right) => left.get_name().localeCompare(right.get_name()));
        } catch (error) {
            global.logError("OminX Start could not enumerate installed applications: " + error);
        }
        return applications;
    }

    _onOpenStateChanged(_menu, isOpen) {
        if (isOpen) {
            this.searchEntry.grab_key_focus();
            return;
        }
        this.showAllApps = false;
        this.searchEntry.set_text("");
        this._refreshView();
    }

    _toggleAppView() {
        this.showAllApps = !this.showAllApps;
        this.searchEntry.set_text("");
        this._refreshView();
        this._setViewButtonLabel(this.showAllApps ? "Pinned  ›" : "All apps  ›");
        if (this.showAllApps) {
            this.searchEntry.grab_key_focus();
        }
    }

    _setViewButtonLabel(label) {
        this.viewButtonText.set_text(label);
    }

    _onSearchChanged(textActor) {
        this._refreshView(textActor.get_text());
    }

    _onSearchActivated(textActor) {
        const query = textActor.get_text().trim().toLocaleLowerCase();
        if (!query) {
            return;
        }
        const matches = this._findApps(query);
        if (matches.length > 0) {
            this._launchApp(null, matches[0]);
        }
    }

    _refreshView(queryText) {
        const query = (queryText || "").trim().toLocaleLowerCase();
        const showResults = this.showAllApps || query.length > 0;
        if (!showResults) {
            this.resultsScroll.hide();
            this.homeBox.show();
            this._setViewButtonLabel("All apps  ›");
            return;
        }

        this.homeBox.hide();
        this.resultsScroll.show();
        this._setViewButtonLabel(this.showAllApps ? "Pinned  ›" : "All apps  ›");
        this._renderResults(query);
    }

    _findApps(query) {
        if (!query) {
            return this.allApps;
        }
        return this.allApps.filter(appInfo => {
            const name = (appInfo.get_name() || "").toLocaleLowerCase();
            const description = (appInfo.get_description() || "").toLocaleLowerCase();
            const id = (appInfo.get_id() || "").toLocaleLowerCase();
            return name.includes(query) || description.includes(query) || id.includes(query);
        });
    }

    _renderResults(query) {
        this.resultsBox.get_children().forEach(child => child.destroy());
        const matches = this._findApps(query);
        this.currentResults = matches;

        const heading = query ? "Search results" : "All apps";
        const subtitle = query
            ? matches.length + (matches.length === 1 ? " app found" : " apps found")
            : "Installed applications, sorted by name";
        this.resultsBox.add_actor(new St.Label({
            text: heading,
            style_class: "ominx-start-section-title ominx-start-results-title"
        }));
        this.resultsBox.add_actor(new St.Label({
            text: subtitle,
            style_class: "ominx-start-results-note"
        }));

        if (matches.length === 0) {
            this.resultsBox.add_actor(new St.Label({
                text: "No matching apps. Try another name or keyword.",
                style_class: "ominx-start-empty-state"
            }));
            return;
        }

        matches.forEach(appInfo => {
            const app = {
                id: appInfo.get_id(),
                name: appInfo.get_name(),
                appInfo: appInfo,
                icon: "application-x-executable-symbolic"
            };
            const button = new St.Button({
                style_class: "ominx-start-result-button",
                can_focus: true,
                reactive: true,
                x_expand: true
            });
            const row = new St.BoxLayout({ vertical: false, style_class: "ominx-start-result-row" });
            row.add_actor(this._createIcon(appInfo, app.icon, 28));
            row.add_actor(new St.Label({ text: app.name, style_class: "ominx-start-result-label" }));
            button.set_child(row);
            button.connect("clicked", Lang.bind(this, this._launchApp, app));
            this.resultsBox.add_actor(button);
        });
    }

    _launchApp(_button, app) {
        this.menu.close();
        if (!app || !app.appInfo) {
            this._openStore();
            return;
        }
        try {
            app.appInfo.launch([], global.create_app_launch_context(0, -1));
        } catch (error) {
            global.logError("OminX Start could not launch " + app.name + ": " + error);
            Main.notifyError("Could not open " + app.name, error.message || String(error));
        }
    }

    _openStore() {
        const store = Gio.DesktopAppInfo.new("ominx-store.desktop");
        if (store) {
            try {
                store.launch([], global.create_app_launch_context(0, -1));
                return;
            } catch (error) {
                global.logError("OminX Start could not open OminX Store: " + error);
            }
        }
        Util.spawnCommandLine("gnome-software");
    }

    _runSessionCommand(_item, command) {
        this.menu.close();
        Util.spawnCommandLine(command);
    }

    _openMenu() {
        if (!Main.overview.visible && !Main.expo.visible) {
            this.menu.toggle();
        }
    }

    on_applet_clicked() {
        this._openMenu();
    }

    on_applet_middle_clicked() {
        this._openMenu();
    }

    on_applet_removed_from_panel() {
        Main.keybindingManager.removeHotKey(this.keybindingName);
    }

    on_orientation_changed(orientation) {
        this.menu.setOrientation(orientation);
    }
}

function main(metadata, orientation, panelHeight, instanceId) {
    return new OminXStartApplet(orientation, panelHeight, instanceId);
}
