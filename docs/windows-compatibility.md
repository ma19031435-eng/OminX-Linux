# Windows application compatibility (Wine + Proton)

OminX runs Windows `.exe` and `.msi` programs through a source-built Wine
runtime, with Proton-style per-game prefixes and DXVK/vkd3d-proton for
Direct3D. There is no copy of Windows, and no compatibility layer runs
every Windows program — see *Limits* below. What this layer guarantees is
the **lifecycle**: everything is already prepared, in the background,
during first install and first boot, so opening a program never starts
with minutes of setup dialogs.

## Why there is a second runtime at all

The OminX target userland is musl-based. Wine requires glibc, so — like
Steam's own runtime — Windows programs run from an isolated glibc
prefix at `/usr/lib/ominx/wine-runtime`, built entirely from pinned
upstream source by `scripts/build-wine-runtime.sh` in LFS order:

```
kernel headers -> glibc 2.41 -> zlib/expat/libffi -> Wayland ->
FreeType/fontconfig/libpng -> ALSA -> Vulkan loader ->
Wine 10.0 (new WoW64: 32-bit and 64-bit programs, one build) ->
DXVK 2.6.1 + vkd3d-proton 2.14.1 (Direct3D 8-12 over Vulkan)
```

Exact commits are in `compat/sources.env`; tarballs with SHA-256 sums in
`compat/sources.json`. `scripts/stage-wine-runtime.py` audits the built
tree before packaging: every executable must use the prefix's own
dynamic linker, every `DT_NEEDED` must resolve inside the prefix, and
setuid files, scripts and escaping symlinks are rejected. A distribution
Wine copy cannot pass that gate. The musl system services below are
small static binaries and are in every default image
(`make-initramfs.py --win-dir`); the runtime is packaged separately with
`--wine-runtime-dir`, so until a runtime artifact is included the
services honestly report `runtime-missing` instead of pretending.

## The services (what runs, and when)

| Process | User | Started | Role |
|---|---|---|---|
| `/sbin/ominx-winsetup` | root | every boot by PID 1, before login | Verifies the runtime, registers the MZ **binfmt** handler (so `./program.exe` works), raises `vm.max_map_count` to the Proton-recommended value, writes `/run/ominx/wine-runtime.conf` and the first-install marker `/var/lib/ominx/wine/system-setup-v1`, then answers `STATUS`/`RECHECK` on `/run/ominx/winsetup.sock`. **Never executes Windows code.** |
| `/bin/ominx-wined` | the signed-in user | background at graphical login by the seat; on demand for console sessions by `ominx-win` | Owns everything user-visible (below). Refuses to run as root. |
| `/bin/ominx-win` | the user | console, file association, binfmt (`ominx-win-binfmt`), desktop | Thin validated client: `run`, `install`, `msi`, `proton`, `probe`, `apps`, `status`, `setup`, `doctor`. |
| persistent `wineserver -f -p` | the user | by `ominx-wined` once the prefix is ready | Keeps the Windows environment warm; later launches are native-speed. |

### First install / first boot sequence

1. **First boot (root):** `ominx-winsetup` confirms the runtime files,
   registers binfmt (`:OminXWine:M::MZ::/bin/ominx-win-binfmt:`), sets
   `vm.max_map_count=1048576`, and records the machine setup. A services-
   only image skips binfmt/sysctls so it never intercepts files it
   cannot run.
2. **First login (user, background):** `ominx-wined` creates
   `~/.local/share/ominx/wine/prefix` (plus the traditional `~/.wine`
   symlink) with a silent `wineboot --init` — Mono/Gecko prompts are
   disabled via DLL overrides, so nothing blocks on a dialog. DXVK and
   vkd3d-proton DLLs from the runtime are installed into
   `system32`/`syswow64` and registered as native overrides. Progress
   (`step`, `percent`) is visible in `win status` and the desktop panel.
3. **Proton prewarm:** as soon as the main prefix is ready, the default
   Proton prefix at `~/.local/share/ominx/proton/compatdata/default/pfx`
   is built the same way, then the persistent wineserver starts.
4. **Every later login:** the prefix marker (`.ominx-setup-v1`, tied to
   the runtime version) makes startup immediate; a runtime upgrade
   re-runs the same silent setup before anything launches.

On the legacy Debian desktop the equivalent is
`ominx-wine-firstboot` (systemd user service enabled for all users in
the image hook, `vm.max_map_count` in
`/etc/sysctl.d/91-ominx-gaming.conf`); `ominx-open-windows` waits for it
when a program is opened before preparation finished.

## Launching programs

Every path funnels through the PE inspector (`src/lib/pe.c`) in *both*
the client and the daemon before Wine ever sees the file:

- Console: `win run setup.exe`, `win install app.msi`,
  `win proton --appid 1234 game.exe`, or just `./program.exe`
  (console routing and binfmt both reach the same validation).
- Desktop: Start → **Windows apps** shows live setup state, installed
  programs, and launches them; the packaged
  `ominx-windows.desktop` + MIME definitions give the file manager the
  same association (`application/x-ms-dos-executable`, `application/x-msi`).
- Steam (full desktops): `compat/proton-tool/` is a ready
  `compatibilitytools.d` tool whose `proton` verbs delegate to
  `ominx-win proton`, so Steam games land in the same per-app prefixes.

Refusals are explicit: DLLs are not programs, ARM/IA-64 binaries,
malformed/truncated headers, non-PE files, relative paths, control
characters in arguments, running as root, and more than 8 concurrent
programs. `.NET` (CLR) binaries are reported (`dotnet=1`): they need
Wine Mono, which is an explicit opt-in follow-up, not a silent download.

`win probe [--json] FILE` classifies without running anything, and
`win doctor` checks the runtime, binfmt registration, `max_map_count`
and `/dev/ntsync` (kernel ≥ 6.14; until then esync/fsync are used).

## Proton behaviour

`PROTON` launches use Steam's layout conventions so tools and user
habits transfer: one prefix per title under
`compatdata/<appid>/pfx`, `STEAM_COMPAT_DATA_PATH`, `SteamAppId`,
esync/fsync enabled, DXVK/vkd3d-proton DLLs pre-installed, and the
working directory set to the executable's folder (installers expect
their companion files there). Prefixes are created in the background on
first request for a new appid; the client waits with progress.

## Kernel support

`scripts/check-kernel-graphics.py` now asserts a
`windows-compatibility` group built into the kernel (no modules are
packaged): `binfmt_misc`/`binfmt_script`, IA32 emulation,
namespaces/cgroups/seccomp (Steam-style containers), SysV/POSIX IPC,
inotify/fanotify, userfaultfd, tmpfs ACLs/xattrs, FUSE + overlayfs,
udmabuf, gamepad/uinput/UHID, ALSA/HDMI+USB audio, THP, and the
FAT/exFAT/NTFS/ISO/UDF filesystems Windows media arrives on. If Kconfig
silently drops one, the build stops before compiling.

## Security model

Wine is **not a sandbox**. A Windows program runs with its owner's full
file access — the same warning upstream Wine gives. The OminX services
still narrow the attack surface where they honestly can:

- The root service never loads Windows code; the per-user daemon
  refuses root, checks peer credentials on its `0600` socket, and the
  control channel is a fixed-verb, tab-delimited protocol with length
  caps — there is no root command execution.
- Files are classified from bounded header reads only (never by
  executing or mapping sections), twice, before launch.
- Data mounted from Windows volumes stays `noexec,nosuid,nodev`;
  running a program from such a volume goes through `win run`, which
  reads it as data under the user's identity.
- Setup never downloads anything: Mono/Gecko are disabled during
  `wineboot`, and all DLLs come from the audited runtime tree.

Only run executables from sources you trust. Anti-cheat, anti-tamper
and DRM that require Windows kernel drivers will not work, and titles
can still fail for per-application reasons: check
[Wine AppDB](https://appdb.winehq.org/) and
[ProtonDB](https://www.protondb.com/).

## Status and remaining gates

Implemented and host-tested (`tests/test_pe.py`, `tests/test_wined.py`,
`tests/test_win_packaging.py`, `tests/test_wine_runtime_stage.py`, the
desktop-shell UI test and `scripts/check-config.sh`; CI workflow
`wine-compat.yml`): services, first-boot/first-login setup state
machines, persistent wineserver supervision, binfmt registration,
PE/MSI classification and refusals, Proton prefix lifecycle, packaging
audits, kernel configuration, console + desktop frontend. Daemon tests
drive a **stub runtime** that logs every Wine invocation — they prove
the OminX behavior contract, not Wine itself.

Still required before claiming Windows programs run on the target:

1. First green `wine-runtime.yml` build producing the audited runtime
   artifact (manually dispatched; multi-hour, cached by source pins).
2. Guest acceptance with that artifact: console (CUI) PE programs
   end-to-end, then GUI programs once the Wayland compositor milestone
   (graphics-runtime track) lands — the current framebuffer desktop
   cannot host arbitrary Wine windows yet.
3. A glibc Mesa/Vulkan ICD stage for hardware rendering (llvmpipe
   first) so DXVK has a driver; until then Direct3D over Vulkan has no
   ICD on the target.
4. Wine Mono/Gecko as explicitly installed optional components for
   .NET/HTML-embedding programs, and per-title result recording.
