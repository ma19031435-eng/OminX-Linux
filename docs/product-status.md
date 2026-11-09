# OminXOS product brief: status against the repository

This file maps each claim in the OminXOS product brief to what the repository
does today. Status values:

- **Built**: implemented and covered by a test or CI run.
- **Partial**: some of it exists; the rest is named below.
- **Not started**: no code in the repository yet.
- **Target**: a goal, not a measured result. Not claimed as achieved.

Nothing here is a claim of compatibility or performance that has not been measured.

## Desktop and experience

| Brief claim | Status | Notes |
|---|---|---|
| Modern desktop, brand palette (navy, teal, cyan, slate, soft white) | Partial | Game library uses the brand palette and the supplied logo (`desktop/branding/`). The Plasma look (`desktop/plasma/`) still uses the earlier Harbor palette. The Harbor package uses a vector trace of the logo (`contents/images/ominx-logo.svg`) on its splash screen (`contents/splash/Splash.qml`). The splash loads under Qt; it has not been seen in a real session. Login screen and app icons still need the logo. |
| Consistent window controls for OminX apps | Partial | Game library draws its own minimize, maximize and close (`TitleBar.qml`). A KWin rule to suppress the compositor's duplicate frame is not written or tested. |
| No terminal required; graphical install, printers, network, users, updates | Not started | No graphical settings, printer, network, or user-management UI exists yet. |
| User-controlled updates; no forced reboots | Partial | Decision library built and tested (`src/lib/updatepolicy.*`): downloads, installs and restarts are separate user choices; no install or restart by default; nothing installs or restarts during a game. No update client, download backend, or scheduler daemon yet. |
| Designed to disappear, fast startup | Target | Not measured. |

## Applications and compatibility

| Brief claim | Status | Notes |
|---|---|---|
| `.exe` compatibility | Partial | Wine and Proton runtime built in CI (`wine-runtime.yml`); acceptance boots and runs the Windows services. Per-title results are not yet recorded. |
| `.msi` compatibility | Partial | `.msi` handling is routed through the Wine runtime. Not verified with real installers. |
| "89% Windows application compatibility" | Target | Not measured. No test suite of real applications exists yet. This figure must not be used as a claim until measured. |
| Shortcuts, install and launch from the desktop | Partial | The game library lists titles and launches them through `ominx-win`. Shortcut creation and general app install are not built. |
| Native `.opkgx` applications | Partial | Format v1 is specified in `docs/opkgx-format.md`. `ominx-opkgx` validates, packs, installs, lists, removes and runs packages (`src/lib/opkgx.c`, `src/lib/opkgx-cli.c`). Native apps run directly. Windows `.exe` apps run in their own prefix through the Wine service (`APPRUN`); `.msi` installers run through `APPMSI`, and the app is `ready` once they exit 0. Each app prefix is built at install time. Icons are extracted from the program when no `icon.png` is shipped (`src/lib/peicon.c`). Double-clicking a package installs it, with notifications. Tests: `tests/test_opkgx.py` (100 tests), run under ASan/UBSan, plus archive and PE fuzzing with no failures. Not yet verified: a real Wine runtime running a real installer, and the packages on the real target. |
| Forge language (`ominx-forge`) | Partial | Forge 1.0 is specified in `docs/forge-language.md`: dynamic types, closures, modules, a static checker with `file:line:col` diagnostics, and fixed limits. Source is in `src/forge/`. Runs only on OminXOS (product gate). Tests: `tests/test_forge.py` (88 tests), run normally and under ASan/UBSan, with mutation fuzzing and no crashes. Not yet verified: the same binary on the target system. |
| Forge Studio (IDE) | Partial | The QML front end and a native Qt host are in `desktop/forge-studio/`, documented in `docs/forge-studio.md`. The bridge runs fixed operations through the real CLI (`tests/test_forge_studio.py`, 24 tests), `Main.qml` loads headless with zero warnings, the QML lints clean, and the bridge contract matches across QML, the Python and C++ hosts. Not yet verified: the window rendered and used on a display, and the native host compiled with Qt (no Qt C++ headers in the build sandbox). |
| OPKGX runner `forge` | Partial | Forge packages install and run through `ominx-opkgx`. Program output goes to a per-app log for desktop launches. Covered by `tests/test_opkgx.py` and `tests/test_forge.py`. |
| LibreOffice Writer, Calc, Impress, Draw, Base, Math | Not started | Not in the build. |
| Linux applications | Partial | The base system is source-built; a Wayland compositor and GUI apps are listed as remaining gates in `docs/windows-compatibility.md`. |

## Gaming

| Brief claim | Status | Notes |
|---|---|---|
| Vulkan integration | Partial | Vulkan loader and ICD work is listed as a remaining gate (llvmpipe first). |
| DirectX compatibility | Partial | Through DXVK and vkd3d-proton in the Wine runtime build. Not verified in-game. |
| Multi-monitor support | Not started | Not in the build. |
| Game scheduling (CPU, GPU, I/O boost) with up-front compatibility status | Partial | Implemented in `src/lib/gamesched.*` and surfaced in the game library. Real-hardware cgroup and BFQ behaviour is unverified. |
| Anti-cheat: Valorant blocked, Fortnite pending vendor support | Built | Modelled as a per-title gate. Nothing bypasses anti-cheat. |

## Storage and creators

| Brief claim | Status | Notes |
|---|---|---|
| NTFS, exFAT, FAT32 | Built in config | Enabled in `build.sh` (`NTFS3_FS`, `EXFAT_FS`, `VFAT_FS`). Read-only Windows filesystem import is a CI check; read/write is not claimed. |
| EXT2, EXT3, EXT4 | Built in config | `EXT2_FS`, `EXT3_FS` and `EXT4_FS` are enabled in `build.sh`. |
| BTRFS, XFS | Built in config | Enabled in `build.sh`. Not yet exercised by a boot test. |
| ISO images | Built in config | `ISO9660_FS` and `UDF_FS` are enabled. |
| Creator workloads (3D, video, audio, dev tools) | Not started | No creator application set is shipped. |

## Security and privacy

| Brief claim | Status | Notes |
|---|---|---|
| Controlled application environments | Partial | The Wine service is per-user, refuses root, uses a fixed command set, and has no command-exec API. Wine is not a sandbox, and this file does not claim otherwise. |
| Secure software management | Not started | No package or application signing model exists yet. |

## Next steps, in order

1. Brand pass on the Plasma look and KWin rule for frameless OminX apps.
2. Extract icons from installed `.exe` files for real titles.
3. C++ on-target launch bridge for the game library.
4. Per-title Windows application results on a booted target.
5. `.opkgx` v1 is designed and implemented (`docs/opkgx-format.md`, system overview in `docs/opkgx-system.md`). Still to verify on a real target: a real Wine runtime running a real installer, and double-click install from the file manager.
6. Forge 1.0 and Forge Studio are implemented (`docs/forge-language.md`, `docs/forge-studio.md`). Still to verify on a target: Studio rendered on a display, and the native Qt host built with the Qt target toolchain (`scripts/build-forge-studio.sh`).
