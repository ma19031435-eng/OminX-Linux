# Source-built Qt Quick and theme integration stage

This stage passed actual guest rendering/input acceptance; see the
[recorded evidence](validation/target-qt-quick.md). It is not a completed display
manager, authentication system, or KDE desktop. The default ISO remains the
original live console until the real desktop/session dependencies are present.

## Build separation

`scripts/build-qt-quick-target.sh` extends the independently compiled target Qt
base with pinned upstream Qt ShaderTools and Qt Declarative/Quick 6.8.3. Exact
commits are in `desktop/qt/quick.env`. No existing distribution root filesystem
or target Qt package is used.

The shader compiler requires **native** Qt Gui, so its build uses a separate
`build/qt-quick-host` tree rather than mutating the accepted Core-only generator
configuration. Native developer-build modules emit their tools and CMake metadata
into that host tree; they are not installed into the musl prefix. Only separately
cross-compiled target libraries enter `build/qt-prefix`. Native Quick tooling
must match the target module features (including `qmltestrunner`); it uses the
separate `qtdeclarative-host-full` configuration. Split native tool metadata is
resolved through Qt's explicit additional host-package prefixes.

The workflow caches dependency build workspaces independently of the original
validation application. A workspace may contain a failed partial build; a cache
hit is **not** acceptance. Source commit/cleanliness checks, CMake configuration,
compilation and installation still run, and test steps cannot run after a build
failure. Restore prefixes include pinned source/toolchain identities.

The first implementation uses static Qt Quick and its software scene graph over
the already-tested Linux framebuffer/evdev backend. This is not the eventual
Wayland/Mesa/KWin deployment stack. Fonts come from the pinned Qt source tree's
DejaVu resource, with its upstream license copied into the provenance artifact.
Original branding does not change third-party licensing obligations.

## Guest validation contract

`desktop/quick-probe` embeds the **same** `desktop/sddm/ominx/Main.qml` used by the
host-tested SDDM theme. It does not maintain a second approximated login layout.
A visible banner says graphics validation only, with no authentication/session.

The application supplies an empty session model and an explicitly disabled context:

- There are no fabricated installed Plasma sessions.
- No passwords are authenticated or stored.
- Power capabilities are disabled in this compatibility test.
- Any attempt to call the disabled authentication/power backend fails the test.
- Test input checks username entry, masked password input, refusal when there is
  no desktop session, and Escape clearing before returning to the console.

The VM harness executes the program as UID 1000 on Bochs/BIOS, virtio/UEFI and
QXL/BIOS media. It checks the actual framebuffer for the theme's accent and the
validation banner, sends real keyboard events, and requires the expected input
results, console return and controlled shutdown. Neither a firmware picture nor
host-only rendering is sufficient.

## Reproduction

After source toolchain/base Qt preparation:

```sh
JOBS=4 scripts/build-qt-target.sh
JOBS=4 scripts/build-qt-quick-target.sh
make build
python3 scripts/make-initramfs.py build/ominx build/initramfs.cpio.gz \
  build/ominx-files build/ominx-control \
  build/graphics-probe/ominx-graphics-probe build/quick-probe/ominx-quick-probe
make media
python3 scripts/test-qt-quick.py
```

The script also supports `--dependencies-only` and `--probe-only`; the latter
requires the former to have completed successfully. The optional packager input
adds `/bin/ominx-quick-probe` without enabling it at boot or changing normal login.

## Remaining work

A real seat/display stack, DBus, authentication/account provisioning, upstream
SDDM and KDE Plasma still need source builds, runtime integration and actual
correct/incorrect-login, logout, relogin and session privilege tests. This stage
cannot substitute for any of those gates. See `graphics-login.md`.
