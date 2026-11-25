# OminX Harbor: Plasma look

KDE Plasma stays the desktop base. OminX Harbor is an original OminX look for
it. The layout is familiar (a bottom bar, a menu, a tray and a clock), but the
design is OminX's own: a sea-glass palette, a centred pinned row, an OminX menu
label, a window-button order with a centred title, and no sounds.

It does not use Windows names, logos, icons, wallpapers or sounds.

## Files

| path | purpose |
| --- | --- |
| `look-and-feel/com.ominx.harbor/` | Plasma look-and-feel package: metadata, defaults, bottom-bar layout script and wallpaper |
| `color-schemes/OminXHarbor.colors` | colour scheme, installed to `/usr/share/color-schemes/` |
| `xdg/kwinrc`, `xdg/plasmarc`, `xdg/kdeglobals` | system defaults, installed to `/etc/xdg/` |

The paths are install targets. Nothing installs them yet. The source-built image
does not ship a Plasma session.

## Verification status

Checked against upstream KDE sources (plasma-workspace, plasma-desktop and
breeze, cloned read-only):

* Panel scripting: `alignment`, `lengthMode` (`fill`), `height`, `hiding`,
  `floating`, `opacity` (`opaque`) are real properties.
* Kickoff: `icon`, `menuLabel`, `appNameFormat`, `favorites`,
  `favoritesPortedToKAstats`, `favoritesDisplay`, `applicationsDisplay`,
  `alphaSort`, `showActionButtonCaptions`, `compactMode`,
  `switchCategoryOnHover` exist in its config schema.
* Panel spacer: `expanding` is a real General option (used to centre the row).
* Digital clock: group `Appearance` with `showDate`, `dateFormat` (`shortDate`).
* Breeze decoration: `TitleAlignment` is an enum stored as an index; `1` is
  `AlignCenter`.

Not verified:

* KWin's `ButtonsOnLeft` / `ButtonsOnRight` keys live in KDecoration, which was
  not cloned. They follow the usual `[org.kde.kdecoration2]` schema.
* The icon-task options were removed from the layout. Only `launchers` is set,
  because the icon-tasks code was not in the cloned sources.
* The `ominx-start` icon, and the `.desktop` names in the favourites, depend on
  packages that do not exist yet. Plasma falls back to a default when they are
  missing.
* **Runtime behaviour is unverified.** Plasma is not built in the source target
  and cannot run in the sandbox. The look must be checked on a real session.
