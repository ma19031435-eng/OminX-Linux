# OPKGX: the application system of OminXOS

An OPKGX package is how an application is delivered to OminXOS. A package
holds one application, its metadata, and its files. The `.opkgx` file is
checked in full before anything is installed, installs without root, and
appears in the desktop like any other app: a menu entry, an icon, a file
association, and notifications when it installs or runs.

This document describes the whole system. The byte-level rules are in
`docs/opkgx-format.md`. The language and IDE for writing apps are in
`docs/forge-language.md` and `docs/forge-studio.md`.

## The pieces

| Piece | Where | What it does |
|---|---|---|
| Package format | `docs/opkgx-format.md` | the archive layout and the manifest |
| Library | `src/lib/opkgx.c`, `src/lib/opkgx.h` | validation, install, remove, list, run, pack |
| CLI | `src/lib/opkgx-cli.c` → `ominx-opkgx` | the command line and the desktop entry point |
| Icon extraction | `src/lib/peicon.c` | takes an icon from a Windows program when the package has none |
| Wine service | `ominx-wined` | runs Windows apps in their own prefixes |
| Forge runtime | `src/forge/` → `ominx-forge` | runs Forge apps |
| Forge Studio | `desktop/forge-studio/` | the IDE that builds Forge packages |
| Tests | `tests/test_opkgx.py`, `tests/test_forge.py`, `tests/test_forge_studio.py` | the checks behind each claim here |

## Runners

Every app names the runner that starts it. The runner is part of the manifest,
so the installer and the desktop know what to do without guessing.

| Runner | The app is | Started by | Needs |
|---|---|---|---|
| `native` | a program that runs on OminXOS | the program itself, directly | an executable file in `app/` |
| `wine` | a Windows `.exe`, or a `.msi` installer | `ominx-wined`, in the app's own prefix | the Wine service and its runtime |
| `forge` | a Forge program (`.fg`) | `ominx-forge exec`, which runs only on OminXOS | the Forge runtime, shipped with OminXOS |

Windows apps run through the Wine service. The service keeps one wineserver per
prefix, so a program starts quickly, and it builds each app's prefix during
install. The Wine runtime itself is a separate package, and until it is present
the service reports `runtime-missing`. Anti-cheat status is a per-title gate in
the game library, not part of this runner.

## Lifecycle

```
pack ──► validate ──► install ──► run ──► remove
```

1. **Pack.** `ominx-opkgx pack <dir> <out.opkgx>` builds a deterministic archive
   from a folder. The same folder always gives the same bytes. The result is
   validated before it is moved into place. Forge projects are packed by
   `ominx-forge build`, which runs the same checks first.
2. **Validate.** `ominx-opkgx validate <file>` checks the whole archive: the
   manifest, every entry, the sizes, the checksums, and the program entry. Any
   violation rejects the package, and nothing is written.
3. **Install.** Files are extracted into a staging folder, the modes are set,
   and the staging folder is swapped into place. An interrupted swap is repaired
   by the next command that touches the app. The desktop entry is written, the
   registry line is recorded, and, for Windows apps, the prefix is built in the
   background.
4. **Run.** `ominx-opkgx run <id>` starts the app detached from the caller. The
   desktop entry calls it, with `--notify` so the result is shown.
5. **Remove.** `ominx-opkgx remove <id>` deletes the app's folder, its desktop
   entry, and its registry line. Nothing outside the user's home is touched.

`ominx-opkgx list` shows each installed app as `id version runner state`.
`state` is `ready`, or `setup-pending` while a Windows installer is still
running.

## Installing and updating are the user's choice

Nothing installs, updates or restarts by itself. A package is installed when the
user opens it or runs the install command. A new version replaces the old one
only when the user installs it. OminXOS never forces a reboot for an app.

## Where things live

All app state is in the user's home directory:

| Path | Contents |
|---|---|
| `~/.local/share/ominx/apps/<id>/` | the installed app (`opkgx.manifest`, `app/`, `icon.png`) |
| `~/.local/share/ominx/apps/registry` | one line per app: `id version runner state` |
| `~/.local/share/ominx/apps/<id>/prefix` | a Windows app's own prefix |
| `~/.local/share/applications/ominx-<id>.desktop` | the menu entry |
| `~/.local/state/ominx/forge/<id>.log` | output of the last run of a Forge app |

A Forge app's output is written to its log, because a desktop launch has no
terminal. Each run replaces the previous log. The log is created with mode
`0644` and is never followed through a symbolic link.

## Desktop integration

- **Menu and icon.** The desktop entry shows the app's name, categories and
  `icon.png`. Windows apps without an icon get one extracted from the program.
  Forge apps are marked with `X-OminX-Runner=forge`.
- **File association.** `application/x-opkgx` for `*.opkgx` opens the install
  flow. `application/x-forge` for `*.fg` opens Forge Studio. The Windows formats
  (`.exe`, `.msi`) open the Windows support app.
- **Notifications.** `--notify` reports install and run results through
  `notify-send`. A missing `notify-send` is not an error.

## Security model

- **Validation before writes.** The archive is checked in full first. Path
  escapes, links, device nodes, FIFOs, oversized entries, bad checksums and
  truncated archives are refused. Symbolic links in a source folder are refused
  when packing.
- **No root.** Install, run and remove work inside the user's home. Setuid,
  setgid and sticky bits are cleared on extraction.
- **Limited programs.** Forge programs run inside a language with fixed limits
  on memory, output, call depth and file access. The language cannot run shell
  commands. See `docs/forge-language.md`.
- **Platform gate.** `ominx-forge` refuses to run unless the system identifies
  as `ID=ominx`. This is a product gate, not a security boundary.
- **Windows apps.** Each runs in its own prefix. Anti-cheat status is shown as a
  gate, and there is no bypass.

## Errors

The validator and installer report one short reason per failure, such as
`bad-id`, `exec-not-forge` or `path-escape`. The full table is in
`docs/opkgx-format.md`. A failed install leaves the previous version in place.

## Verification

- `tests/test_opkgx.py`: 100 tests for the format, install, remove, run,
  registry, desktop entries, icons and the Wine service interface. They run under
  ASan and UBSan, and the archive and PE parsers have fuzzing with no failures.
- `tests/test_forge.py`: 88 tests for the language, the checker, the project
  tools, the platform gate and the OPKGX forge runner end to end. They also run
  under ASan and UBSan, and the parser and interpreter have mutation fuzzing
  with no failures.
- `tests/test_forge_studio.py`: the Studio bridge against the real `ominx-forge`,
  the contract between the QML and its hosts, and a clean `pyside6-qmllint` run.

Not yet verified on the target: a real Wine runtime running a real installer, and
the packages on real hardware.
