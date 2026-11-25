# OPKGX format, version 1

`.opkgx` is the native application package for OminXOS. This document is the
specification. `src/lib/opkgx.c` implements it, the `ominx-opkgx` tool
(`src/lib/opkgx-cli.c`) exposes it, and `tests/test_opkgx.py` checks it.

## Goals

- Installing an application is one double-click, or one `ominx-opkgx install`.
- A package cannot write outside its own application directory, cannot run as
  root, and cannot carry links or devices.
- Windows programs install the same way as native ones, and run in their own
  Wine prefix that is built ahead of time, not on first launch.
- The target has no Python and no JSON parser, so the format needs only C and
  a tar reader.

## Container

- A POSIX `ustar` tar archive, uncompressed. Compression is reserved for
  version 2 and will keep the same logical layout.
- Allowed entries: regular files and directories only.
- Refused entries: symbolic links, hard links, character or block devices,
  FIFOs, sparse files, and PAX or GNU long-name extensions.
- Paths are relative, use `/` separators, contain no `..` component, no empty
  component, and are at most 255 bytes long.
- The first entry must be `opkgx.manifest`.
- The archive must end with the two zero blocks of the tar end marker. An
  archive that stops earlier is a truncated download and is refused.

## Layout

```
opkgx.manifest        required, first entry, at most 16 KiB
icon.png              optional, PNG, at most 512 KiB
app/...               payload; required for both runners
```

Limits: at most 10000 entries, and at most 2 GiB of payload in total.

## Manifest

UTF-8 text, `key=value` per line. LF and CRLF line endings are both accepted.
Blank lines and lines starting with `#` are ignored. A key may appear only
once. Unknown keys are an error, so a typo cannot be silently ignored.

| Key | Required | Rule |
|---|---|---|
| `format` | yes | must be `1` |
| `id` | yes | 2 to 64 characters: `a-z`, `0-9`, `.`, `-`; starts with a letter; no `..` |
| `name` | yes | 1 to 64 bytes, no control characters |
| `version` | yes | `MAJOR.MINOR.PATCH`, each a decimal integer of at most 5 digits |
| `summary` | no | at most 120 bytes, no control characters |
| `arch` | yes | must be `x86_64` |
| `runner` | yes | `native`, `wine` or `forge` |
| `exec` | yes | path under `app/` of a regular file. For `native` the file must be executable. For `wine` it must end in `.exe` or `.msi`, case-insensitive. For `forge` it must end in `.fg` (lowercase), and no executable bit is needed |
| `icon` | no | must be `icon.png`, and the file must be present |
| `categories` | no | comma-separated, from: `Games`, `Office`, `Development`, `Graphics`, `Audio`, `Video`, `Utilities`, `Internet`, `Education` |
| `permissions` | no | reserved in version 1, must be empty or absent |

Example:

```
# A small game
format=1
id=org.example.puzzle
name=Puzzle Garden
version=1.2.0
summary=Calm tile puzzles.
arch=x86_64
runner=wine
exec=app/PuzzleGarden.exe
icon=icon.png
categories=Games
```

## Runners

- **native**: the executable runs directly on the host, using the system's
  libraries that the package does not bundle. `run` starts it in its own
  directory, detached from the caller.
- **wine**: the program runs inside the OminX Wine service, in the app's own
  prefix at `~/.local/share/ominx/apps/<id>/prefix`. The service is the
  per-user `ominx-wined` daemon. It keeps one wineserver per prefix, so a
  program starts quickly.
  - `.exe`: `run` starts the program in that prefix.
  - `.msi`: `run` starts `msiexec /i` on the package in that prefix. Its state
    stays `setup-pending` until that installer exits with status 0. Running
    the package again after it is `ready` repeats the installer, which is how
    a user repairs or removes the program.
- **forge**: the program is a Forge source file, run by `ominx-forge`, which
  runs only on OminXOS. `run` starts `ominx-forge exec <app/...fg>` in the
  app's folder, detached from the caller, as the other runners do. Standard
  output and standard error go to `~/.local/state/ominx/forge/<id>.log`. Each run
  replaces the log, and the log is never written through a symbolic link. The
  program's imports resolve inside `app/`. The language and its limits are in
  `docs/forge-language.md`, and the packaging workflow is in
  `docs/opkgx-system.md`.

## Installation

Installs happen under the user's home directory and never need root.

1. Validate the whole archive. Any violation rejects the package, and nothing
   is written.
2. Extract into `~/.local/share/ominx/apps/.staging-<id>-<pid>/`.
3. Set modes: executables `0755`, other files `0644`, directories `0755`.
   Setuid, setgid, and sticky bits are cleared.
4. Swap the staging directory into place. The previous version is first renamed
   to `.old-<id>`, then the staging directory is renamed to `<id>`, then the
   old copy is deleted. If a crash lands between the two renames, the next
   install, remove or run finds `.old-<id>` with no `<id>` and restores it first.
5. Icon. For a `wine` package without `icon.png`, the installer extracts the
   program's largest icon from its resources and writes it as `icon.png` in
   the installed copy. Icons in PNG format are copied as they are. Bitmap icons
   at 24 or 32 bits per pixel are converted to PNG. Other formats leave the app
   with the generic icon. This generated file is never part of the package.
6. Write `~/.local/share/applications/ominx-<id>.desktop`. `Exec` is
   `ominx-opkgx run --notify <id>`. `Icon` is the installed `icon.png` if it
   exists.
7. Record the install in `~/.local/share/ominx/apps/registry`, one line per
   app: `id version runner state`. `state` is `ready`, or `setup-pending` for
   an `.msi` package until its installer finishes. A `forge` package is `ready`
   at install.
8. For a `wine` package, ask the service to build the app's prefix. The
   service does this in the background, and if its worker is busy the request
   is queued. Installing still succeeds if the service is not running. The
   first run then reports `prefix-not-ready`, and the prefix is built when that
   run is requested.

Removing an app deletes its directory and its desktop entry, and removes its
registry line. Nothing outside the user's home is touched.

## Packing

`ominx-opkgx pack <source-dir> <out.opkgx>` builds a package from a folder that
holds `opkgx.manifest`, an optional `icon.png`, and `app/`. The output is
deterministic: the same folder always gives the same bytes. Entries are sorted
with the manifest first, owners are zero, and timestamps are zero. The result is
validated before it is moved into place, so `pack` never produces a package
that `install` would refuse. Symbolic links in the source folder are refused.

## Notifications

With `--notify`, `install` and `run` report their result through `notify-send`
when it is installed. Desktop entries and file associations use it, so a
double-click install or a launch that fails is never silent.

## File association

Installing the `ominx-opkgx` package also registers `application/x-opkgx` for
`*.opkgx`, and adds a desktop entry that runs `ominx-opkgx install --notify`.

## Errors

The validator and installer report one short reason per failure. The main ones:

| Reason | Meaning |
|---|---|
| `manifest-missing`, `manifest-not-first` | the manifest is absent or not the first entry |
| `bad-id`, `bad-version`, `bad-name`, `bad-summary`, `bad-runner`, `bad-category`, `bad-icon-key` | a manifest value is out of range |
| `arch-unsupported`, `format-unsupported`, `permissions-unsupported` | the package asks for something version 1 does not provide |
| `unknown-key`, `duplicate-key`, `bad-line`, `missing-required-key` | the manifest syntax is wrong |
| `exec-outside-app`, `exec-missing`, `exec-not-executable`, `exec-not-windows`, `exec-not-forge` | the program entry is wrong for its runner |
| `link-entry`, `device-entry`, `fifo-entry`, `extension-entry`, `entry-type-unsupported` | an archive entry type is refused |
| `path-escape`, `unexpected-entry`, `duplicate-entry`, `path-too-long`, `bad-size` | an archive path or size is refused |
| `bad-checksum`, `not-ustar`, `truncated` | the archive is damaged or cut short |
| `too-large`, `too-many-entries` | a size or count limit was exceeded |
| `icon-not-png`, `icon-missing`, `icon-undeclared` | the icon is wrong |
| `payload-missing` | the package has no `app/` contents |
| `not-installed`, `bad-id`, `manifest-id-mismatch` | the requested app is not installed as named |
| `wined-unavailable` | the Wine service is not running |
| `prefix-not-ready` | the app's prefix is still being built; the request was queued |
| `program-missing`, `not-a-windows-program`, `not-an-msi`, `unsupported-architecture` | the Windows program is not usable |
| `fork-failed` | the program could not be started |
| `too-many-programs` | the service is already running its maximum number of programs |
| `swap-failed`, `registry-failed`, `desktop-entry-failed` | the installer could not finish a step |
| `source-unreadable`, `output-unwritable`, `too-deep` | `pack` could not read the folder or write the output |

## Versioning

A package with `format` other than `1` is refused, with the reason
`format-unsupported`. A new format version is a new document, not a change to
this one.

## Not in version 1

Signatures, a permission model, delta updates, compression, icon extraction from
non-Windows binaries, 8-bit and 4-bit program icons, and package signing
for the update channel. Each will be added in a later format version.
