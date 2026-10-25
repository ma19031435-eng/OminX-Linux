# Windows compatibility layer: validation (host)

This record covers the service layer that ships in default images. It
does **not** claim a Windows program ran under real Wine: daemon tests
use a stub runtime that logs every invoked "Wine" command, proving the
OminX contract (commands, prefixes, environment, ordering, refusals)
that the real runtime artifact will satisfy.

## What was run

- `make check`: **94 host tests, OK** (67 pre-existing + 27 new):
  - `tests/test_pe.py` (9): PE32/PE32+ classification, GUI/console/.NET,
    DLL and ARM64 refusal classes, MSI magic/truncation, malformed
    header corpus, bounded header-window behavior, suffix hints.
  - `tests/test_wined.py` (8): automatic first-login setup against the
    stub runtime (silent `wineboot --init`, DXVK DLL copied into the
    prefix and registered native, `~/.wine` symlink, version marker),
    persistent wineserver reported `running`, default Proton prefix
    precreated in the background, second login instantly `ready`,
    `RUN`/`MSI`/`PROTON` argv, working directory, `SteamAppId`, wrong
    kind/architecture/path/argument refusals, `APPS` + `PROBE`, setup
    failure surfaces as `state=failed error=setup-step-11`,
    `runtime-missing` honesty, single-instance socket protection, the
    root winsetup service (`STATUS`/`RECHECK`, marker contents,
    binfmt stays off without a runtime) and CLI `probe --json`.
  - `tests/test_win_packaging.py` (4): default images unchanged without
    `--win-dir`; service image contents/modes/binfmt symlink/desktop +
    MIME entries; determinism; `--wine-runtime-dir` refuses to ship
    without services; CLI refuses non-static inputs.
  - `tests/test_wine_runtime_stage.py` (6): a genuinely self-contained
    mini glibc tree (real loader + libc + a binary linked against the
    OminX prefix) audits clean; a host-interpreter binary, absolute
    symlink, setuid file, executable script and missing components are
    rejected; an executable PE module is accepted as data.
  - `tests/test_kernel_config.py` now covers 60 required built-ins,
    including the 43-symbol windows-compatibility group.
- `scripts/check-config.sh`: **passed**, including new mock-Wine
  exercises proving the legacy desktop's `ominx-wine-firstboot` creates
  the prefix exactly once, records the runtime version, and no-ops
  afterwards.
- Desktop shell UI test (`tests/ui/test_desktop_shell.py`, PySide6
  offscreen with a mocked context): **passed**, including opening the
  Windows panel, firing setup, and launching a listed `demo.exe`
  through `session.launchWinApp(0)`. Screenshots render the new
  “Windows apps” start-menu entry.
- Combined packaging spot-check: `archive(login=..., win=...,
  wine_runtime=<audited mini runtime>)` produces one image containing
  the greeter/desktop, all three Windows services and the staged
  runtime + DXVK DLL with no path collisions.
- `sh -n` clean for every shell script; all GitHub workflows parse as
  YAML after the branch/pin repairs.

## Evidence shape (stub runtime log, abridged)

```
ARGS=wineboot --init                    PREFIX=~/.local/share/ominx/wine/prefix
ARGS=wineserver -w
ARGS=reg add HKCU\Software\Wine\DllOverrides /v d3d11 /d native /f
ARGS=wineserver -f -p                   (persistent, supervised)
ARGS=wineboot --init                    PREFIX=.../proton/compatdata/default/pfx
ARGS=/…/Game Setup.exe --fullscreen     CWD=<exe folder>
ARGS=msiexec /i /…/app.msi
STATUS -> state=ready percent=100 wineserver=running proton-default=ready
```

## Remaining acceptance (not covered here)

1. ~~First `wine-runtime.yml` artifact (glibc + Wine + DXVK from source)~~ done:
   run 40111487744 on 6db0b81, audit passed;
2. guest runs of real CUI PE programs with that artifact,
3. GUI programs after the Wayland compositor milestone,
4. glibc Vulkan ICD (llvmpipe first) for hardware/software rendering.
