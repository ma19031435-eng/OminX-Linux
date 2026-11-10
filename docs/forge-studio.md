# Forge Studio and the Forge toolchain

Forge Studio is the IDE for Forge apps on OminXOS. It works like an Xcode
project window: a project navigator, an editor with line numbers, a Problems
list that jumps to the error, an output panel, and the actions to check, test,
run and build. Forge Studio and the `ominx-forge` CLI run only on OminXOS.

The language is described in `docs/forge-language.md`, and packaging in
`docs/opkgx-system.md`.

## The toolchain

`ominx-forge` is the one program behind everything: the CLI, the checker, the
interpreter and the project tools. Forge Studio does not run any other program.

| Command | What it does | Exit status |
|---|---|---|
| `ominx-forge new <dir> --id <id> --name <name> [--version V] [--summary S]` | creates a project. The folder must not exist | 0 done, 1 refused, 2 usage |
| `ominx-forge check <dir\|file.fg> [--json]` | checks every file and prints problems as `file:line:col` (or JSON) | 0 clean, 1 problems |
| `ominx-forge run <dir\|file.fg>` | checks, then runs `main()` | the program's exit status |
| `ominx-forge test <dir\|file.fg>` | runs every `test_*` function | 0 all passed, 1 failures |
| `ominx-forge build <dir> [--out file.opkgx]` | checks, tests and packs the project into an `.opkgx` | 0 built, 1 refused |
| `ominx-forge exec <file.fg>` | runs a program without a project. This is what an installed app uses | the program's exit status |
| `ominx-forge tree <dir> [--json]` | lists the editable files | 0 |
| `ominx-forge read <dir> <rel>` | prints one editable file | 0 read, 1 refused |
| `ominx-forge write <dir> <rel>` | replaces one editable file with stdin. The write is atomic | 0 saved, 1 refused |
| `ominx-forge version` | prints the version | 0 |
| `ominx-forge help` | prints usage | 0 |

On any other system every command except `version` and `help` exits with status
3 and prints `Forge runs only on OminXOS.` The shipped build reads
`/etc/os-release`, which must be a regular file owned by root and not writable
by group or others, and it must contain `ID=ominx`. The test build reads an
identity file from `OMINX_FORGE_OS_RELEASE` with no ownership check, and that
override exists only in the test build.

## Project layout

```
PuzzleGarden/
  forge.project        key=value settings
  src/main.fg          the entry point (main=main.fg)
  src/...              more .fg files, imported by relative path
  assets/...           files the program reads with read_asset()
  icon.png             optional app icon
  build/               build output; not edited by hand
```

`forge.project` keys:

| Key | Required | Rule |
|---|---|---|
| `format` | yes | must be `1` |
| `id` | yes | reverse-DNS app ID, the same rules as the package ID |
| `name` | yes | the app name shown to users |
| `version` | yes | `MAJOR.MINOR.PATCH` |
| `summary` | no | one line |
| `categories` | no | the package categories |
| `main` | no | a `.fg` file inside `src/`, default `main.fg` |
| `icon` | no | `icon.png` when present |

Unknown keys and overlong values are errors. Nothing is cut short silently.

Only these paths are editable from Studio and from `read` and `write`: the
`src/` and `assets/` folders, and `forge.project`. Hidden files, paths with
`..`, symbolic links, and anything under `build/` are refused.

`build` produces `build/<id>-<version>.opkgx`. It is deterministic: the same
project always gives the same bytes. Symbolic links and files other than `.fg`
in `src/` stop the build.

## Forge Studio

### Window

- **Toolbar.** A project folder field with Open, New project…, and the actions
  Check, Test, Build .opkgx and Run.
- **Navigator (left).** The project tree. The open file is highlighted, and every
  file with problems is marked.
- **Editor (centre).** A monospace editor with line numbers. The gutter follows
  the text as you scroll. Wrapping is off, so each number is one line.
- **Panel (bottom).** Problems lists every diagnostic. Clicking one opens the
  file at that line and column. Output shows the last run, test or build.
- **Status line (bottom edge).** The last result, or "Working…" while a request
  runs.

Shortcuts: Ctrl+S checks, Ctrl+R runs, Ctrl+T tests, Ctrl+B builds.

### Saving

Studio never loses an edit. Before it opens another file, checks, runs, tests or
builds, it saves the open file if it has changes. The tools always see what the
editor shows.

### New project

The New project dialog takes a folder (absolute, not yet existing), an app ID,
and a name. It runs `ominx-forge new`, then opens the new project with its
`src/main.fg`.

## How Studio talks to the toolchain

Studio's QML never builds a command. It asks for one of these operations:

| Operation | Runs | Arguments from the UI |
|---|---|---|
| `tree` | `ominx-forge tree <dir> --json` | project folder |
| `check` | `ominx-forge check <dir> --json` | project folder |
| `run`, `test`, `build` | `ominx-forge <op> <dir>` | project folder |
| `read` | `ominx-forge read <dir> <rel>` | a file in the editable set |
| `write` | `ominx-forge write <dir> <rel>` with the text on stdin | a file in the editable set, at most 1 MiB |
| `new` | `ominx-forge new <dir> --id <id> --name <name>` | folder, app ID, name |

The arguments go to the program as a list, never through a shell. The host
checks paths before it runs anything, and the CLI checks them again.

### The bridge contract

QML sees one object, `forge`:

- `request(requestId, op, projectDir, rel, content)` starts an operation. The
  call returns at once.
- `finished(requestId, op, ok, exitCode, stdout, stderr, dataJson)` is emitted
  once per request. `dataJson` holds the parsed JSON for `tree` and `check`.

Every request gets exactly one `finished`, including refused requests, which
report exit `-1` and the reason in `stderr`.

## Files

| Path | What it is |
|---|---|
| `desktop/forge-studio/qml/Main.qml` | the window, the request handling, the save and run flow |
| `desktop/forge-studio/qml/Navigator.qml` | the project tree |
| `desktop/forge-studio/qml/Editor.qml` | the editor and the line-number gutter |
| `desktop/forge-studio/qml/OutputPanel.qml` | Problems and Output |
| `desktop/forge-studio/qml/NewProjectDialog.qml` | the New project dialog |
| `desktop/forge-studio/qml/Theme.qml` | the OminX palette and sizes |
| `desktop/forge-studio/host/forge_bridge.py` | the operation table and checks (the reference) |
| `desktop/forge-studio/host/forge_studio_dev.py` | a PySide6 host for development and tests |
| `desktop/forge-studio/host/forge_bridge.h`, `forge_bridge.cpp`, `forge_studio.cpp` | the native Qt host, the same contract with `QProcess` |
| `desktop/forge-studio/CMakeLists.txt` | the Qt build of the native host |
| `scripts/build-forge-studio.sh` | builds the native host against the Qt target prefix |
| `scripts/make-initramfs.py` | packages `ominx-forge`, the desktop entry and the `.fg` MIME type |

The palette is the OminX brand palette: `#101d32`, `#74e0c7`, `#123d46`,
`#244767` and `#eff9f7`.

## Verification

What has been run:

- **Toolchain.** `tests/test_forge.py` (88 tests), run normally and under
  ASan and UBSan, plus mutation fuzzing of the parser and interpreter with no
  crashes or sanitizer reports.
- **Bridge.** `tests/test_forge_studio.py` drives the real `ominx-forge` through
  the bridge for a full project cycle, checks the argument rules, checks that
  shell syntax in names stays literal, and checks the platform gate.
- **QML.** `pyside6-qmllint` reports no warnings for the QML files.
- **Contract.** The QML, the Python host and the C++ host are checked to use the
  same operations and the same signal shape.
- **Dev host signal path.** The Python host's `finished` signal is exercised
  without a window.
- **Headless QML load.** `Main.qml` loads under PySide6 with the offscreen
  platform and produces no QML warnings (`QmlLoads` in `tests/test_forge_studio.py`,
  run with `OMINX_UI_PYTHON`).

Verified in the build sandbox:

- **The rendered window.** `Main.qml` was rendered to an image with Qt 6.8 and
  checked by eye. Layout, palette, toolbar, editor, and the Problems and Output
  tabs all draw. Captures used a scaled offscreen screen, since the offscreen
  platform has a fixed 800x800 surface.
- **The native bridge.** `desktop/forge-studio/host/forge_bridge.cpp` builds with
  `-Wall -Wextra -Werror` against Qt 6.8.1 headers built from source. Its runtime
  test, `scripts/test-forge-studio-native.sh`, drives real `QProcess` calls through
  the Forge test binary: new, tree, check, read, write, round-trip, path refusal,
  unknown operations and missing folders. All 13 checks pass.
- **The native Studio host.** `host/forge_studio.cpp` also builds with `-Werror`
  against the Qt 6.8.1 QML headers. The linked binary passes the OminX platform
  gate (exit 3 off OminX), and with the gate passed it loads the same QML and runs
  its event loop for 12 seconds with no QML errors. The QML module was loaded from
  file, not from the CMake QML registration.

What has not been run in the build sandbox:

- **The CMake project.** `desktop/forge-studio/CMakeLists.txt` lists every QML file
  and the singleton, and a test enforces that. It was not configured, because the
  sandbox only has a partial Qt install (a full `cmake --install` of qtbase fails on
  unbuilt third-party modules). The first CMake configure is on the Qt target.
- **The static musl build and the full Qt-based Studio binary.** Studio needs a
  static musl Qt prefix (`scripts/build-qt-quick-target.sh`). That prefix needs the
  GNU toolchain, which cannot be fetched here. So `--forge-studio` in the initramfs
  is not exercised. The initramfs itself builds (`make initramfs CC=$PWD/scripts/musl-cc-zig.sh`)
  with the static Forge CLI and its MIME entry, and the Studio desktop entry is left out
  without the Studio binary.
- **Real display and input.** Mouse and keyboard use on a real display is not tested.

## Limits in Forge 1.0

- The editor is plain text. It has no syntax colouring or completion yet.
- Forge programs are console programs. Their output goes to the Output panel in
  Studio, and to the app log for desktop launches. A graphical toolkit for Forge
  apps is not part of 1.0.
- A project is one folder. Studio opens one project at a time.
