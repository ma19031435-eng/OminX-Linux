// OminX Aurora's Plasma layout: a floating command bar with native widgets.
// The panel scripting API and widget IDs are provided by Plasma Workspace.

var desktops = desktopsForActivity(currentActivity());
for (var desktopIndex = 0; desktopIndex < desktops.length; desktopIndex++) {
    var desktop = desktops[desktopIndex];
    desktop.wallpaperPlugin = "org.kde.image";
    desktop.currentConfigGroup = ["Wallpaper", "org.kde.image", "General"];
    desktop.writeConfig(
        "Image",
        "file:///usr/share/backgrounds/ominx/ominx-wallpaper.svg"
    );
}

var panel = new Panel;
var geometry = screenGeometry(panel.screen);
var panelWidth = Math.min(1480, Math.max(560, geometry.width - 36));

panel.location = "top";
panel.alignment = "center";
panel.lengthMode = "custom";
panel.length = panelWidth;
panel.minimumLength = Math.min(560, panelWidth);
panel.maximumLength = panelWidth;
panel.height = 46;
panel.offset = 10;
panel.hiding = "none";
panel.floating = true;
panel.opacity = "translucent";

var launcher = panel.addWidget("org.kde.plasma.kickoff");
launcher.currentConfigGroup = ["General"];
launcher.writeConfig("icon", "ominx-start");
launcher.writeConfig("menuLabel", "OminX");
launcher.writeConfig("appNameFormat", 0);
launcher.writeConfig("favorites", [
    "org.kde.dolphin.desktop",
    "firefox-esr.desktop",
    "ominx-store.desktop",
    "libreoffice-writer.desktop",
    "steam.desktop",
    "net.lutris.Lutris.desktop",
    "systemsettings.desktop"
]);
launcher.writeConfig("systemApplications", [
    "systemsettings.desktop",
    "org.kde.kinfocenter.desktop"
]);
launcher.writeConfig("systemFavorites", ["suspend", "reboot", "shutdown"]);
launcher.writeConfig("primaryActions", 3);
launcher.writeConfig("favoritesPortedToKAstats", false);
launcher.writeConfig("favoritesDisplay", 0);
launcher.writeConfig("applicationsDisplay", 1);
launcher.writeConfig("alphaSort", true);
launcher.writeConfig("showActionButtonCaptions", false);
launcher.writeConfig("compactMode", true);
launcher.writeConfig("switchCategoryOnHover", true);

panel.addWidget("org.kde.plasma.pager");

var tasks = panel.addWidget("org.kde.plasma.icontasks");
tasks.currentConfigGroup = ["General"];
tasks.writeConfig("launchers", [
    "applications:org.kde.dolphin.desktop",
    "applications:firefox-esr.desktop",
    "applications:ominx-store.desktop",
    "applications:libreoffice-writer.desktop",
    "applications:steam.desktop",
    "applications:ominx-settings.desktop"
]);
tasks.writeConfig("groupingStrategy", 1);
tasks.writeConfig("groupPopups", true);
tasks.writeConfig("onlyGroupWhenFull", true);
tasks.writeConfig("separateLaunchers", true);
tasks.writeConfig("hideLauncherOnStart", false);
tasks.writeConfig("showOnlyCurrentDesktop", true);
tasks.writeConfig("maxStripes", 1);
tasks.writeConfig("showToolTips", true);
tasks.writeConfig("interactiveMute", true);
tasks.writeConfig("fill", true);
tasks.writeConfig("iconSpacing", 1);

panel.addWidget("org.kde.plasma.marginsseparator");
panel.addWidget("org.kde.plasma.systemtray");
panel.addWidget("org.kde.plasma.digitalclock");
panel.addWidget("org.kde.plasma.showdesktop");
