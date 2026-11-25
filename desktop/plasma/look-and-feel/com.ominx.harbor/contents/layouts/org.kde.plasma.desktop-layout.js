// OminX Harbor's Plasma layout: a full-width bottom bar with centred pinned
// apps, an OminX menu on the left, and the tray and clock on the right.
// The panel scripting API and widget IDs are provided by Plasma Workspace.

var desktops = desktopsForActivity(currentActivity());
for (var desktopIndex = 0; desktopIndex < desktops.length; desktopIndex++) {
    var desktop = desktops[desktopIndex];
    desktop.wallpaperPlugin = "org.kde.image";
    desktop.currentConfigGroup = ["Wallpaper", "org.kde.image", "General"];
    desktop.writeConfig(
        "Image",
        "file:///usr/share/plasma/look-and-feel/com.ominx.harbor/contents/images/harbor-wallpaper.svg"
    );
}

var panel = new Panel;

panel.location = "bottom";
panel.alignment = "center";
panel.lengthMode = "fill";
panel.height = 44;
panel.hiding = "none";
panel.floating = false;
panel.opacity = "opaque";

var menu = panel.addWidget("org.kde.plasma.kickoff");
menu.currentConfigGroup = ["General"];
menu.writeConfig("icon", "ominx-start");
menu.writeConfig("menuLabel", "OminX");
menu.writeConfig("appNameFormat", 0);
menu.writeConfig("favorites", [
    "ominx-store.desktop",
    "org.kde.dolphin.desktop",
    "firefox-esr.desktop",
    "libreoffice-writer.desktop",
    "ominx-programs.desktop",
    "ominx-settings.desktop"
]);
menu.writeConfig("favoritesPortedToKAstats", false);
menu.writeConfig("favoritesDisplay", 1);
menu.writeConfig("applicationsDisplay", 1);
menu.writeConfig("alphaSort", true);
menu.writeConfig("showActionButtonCaptions", false);
menu.writeConfig("compactMode", true);
menu.writeConfig("switchCategoryOnHover", false);

// Two expanding spacers push the pinned row to the middle of the bar.
function addSpacer(bar) {
    var spacer = bar.addWidget("org.kde.plasma.panelspacer");
    spacer.currentConfigGroup = ["General"];
    spacer.writeConfig("expanding", true);
    return spacer;
}

addSpacer(panel);

var tasks = panel.addWidget("org.kde.plasma.icontasks");
tasks.currentConfigGroup = ["General"];
tasks.writeConfig("launchers", [
    "applications:ominx-store.desktop",
    "applications:org.kde.dolphin.desktop",
    "applications:firefox-esr.desktop",
    "applications:ominx-programs.desktop",
    "applications:ominx-settings.desktop"
]);
// Only the launcher list is written: the other icon-task options are left at
// their Plasma defaults until they are checked against the running release.

addSpacer(panel);

panel.addWidget("org.kde.plasma.systemtray");
var clock = panel.addWidget("org.kde.plasma.digitalclock");
clock.currentConfigGroup = ["Appearance"];
clock.writeConfig("showDate", true);
clock.writeConfig("dateFormat", "shortDate");
clock.writeConfig("showSeconds", false);

panel.addWidget("org.kde.plasma.showdesktop");
