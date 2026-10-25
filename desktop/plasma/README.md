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

* Checked in the sandbox (`tests/test_plasma_look.py`): every JSON file parses,
  the colour and config files parse, the SVG parses, the layout script passes
  `node --check`, and the package has no sound files and no Microsoft names.
* **Not verified:** on a running Plasma desktop. Plasma is not built in the
  source target and cannot run in the sandbox. The layout's widget options,
  the kwin button and title keys, and the spacer behaviour must be checked on a
  real session before this look is called done. Treat them as unverified.
