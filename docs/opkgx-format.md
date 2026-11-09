# OPKGX format, version 1

`.opkgx` is the native application package for OminXOS. This document is the
specification. The validator and installer in `src/lib/opkgx.c` implement it,
and `tests/test_opkgx.py` checks it.

## Goals

- Installing an application is one double-click, or one `ominx-opkgx install`.
- A package cannot write outside its own application directory, cannot run as
  root, and cannot carry links or devices.
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
| `version` | yes | `MAJOR.MINOR.PATCH`, each a decimal integer |
| `summary` | no | at most 120 bytes, no control characters |
| `arch` | yes | must be `x86_64` |
| `runner` | yes | `native` or `wine` |
| `exec` | yes | path under `app/` of a regular file. For `native` the file must be executable. For `wine` it must end in `.exe` or `.msi`, case-insensitive |
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
  libraries that the package does not bundle.
- **wine**: the executable runs inside the OminX Wine runtime, in that
  application's own prefix at `~/.local/share/ominx/apps/<id>/prefix`. A
  `.msi` exec is run through `msiexec` in that prefix. Version 1 installs
  `.msi` packages but reports `setup-pending` until the first run completes.

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
   install or remove finds `.old-<id>` with no `<id>` and restores it first.
5. Write `~/.local/share/applications/ominx-<id>.desktop`, with `Exec` set to
   `ominx-opkgx run <id>` and `Icon` set to the installed `icon.png` if present.
6. Record the install in `~/.local/share/ominx/apps/registry`, one line per
   app: `id version runner state`. `state` is `ready`, or `setup-pending` for
   a `.msi` package.

Removing an app deletes its directory and its desktop entry, and removes its
registry line. Nothing outside the user's home is touched.

## Errors

The validator reports one short reason per failure, for example
`manifest-missing`, `bad-id`, `link-entry`, `path-escape`, `exec-not-executable`,
`duplicate-key`, `unknown-key`, `too-large`. The installer prints the same
reason and exits non-zero.

## Versioning

A package with `format` other than `1` is refused, with the reason
`format-unsupported`. A new format version is a new document, not a change to
this one.

## Not in version 1

Signatures, a permission model, delta updates, and compression. Each will be
added in a later format version.
