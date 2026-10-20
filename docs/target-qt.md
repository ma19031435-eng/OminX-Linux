# Source-built target Qt bootstrap (experimental)

This is an **in-progress dependency stage**, not a KDE desktop, a login manager,
or proof that the graphics request is complete. Its CI outcome must be checked;
adding a recipe does not establish that its output builds or boots.

`scripts/build-qt-target.sh` uses the existing source-built GCC/musl C++ toolchain
and pinned upstream Qt 6.8.3 source. It first builds native host code generators,
then separately cross-compiles target Qt Core/Gui/Widgets and the original raster
acceptance application. Host libraries/tools are not copied into target media.
Target library/package lookup is restricted to the source toolchain/Qt prefix,
pkg-config host lookup is disabled, and packaging rejects a dynamic interpreter
or a non-x86-64 executable. Qt's bundled upstream dependencies retain their licenses.

The initial backend is static Qt software rendering through Linux framebuffer
and evdev. It deliberately does not claim OpenGL, Vulkan, acceleration, compositor
support, Qt Quick, SDDM authentication, or Plasma. Static linking is a small first
bootstrap step, not the final desktop packaging design or a proprietary Qt license.
All licensing/source/relinking obligations must be met before distributing releases.

## Reproduction

On a Linux build host with CMake, Ninja and the normal source toolchain prerequisites:

```sh
make toolchain
JOBS=4 scripts/build-qt-target.sh
make build
python3 scripts/make-initramfs.py build/ominx build/initramfs.cpio.gz \
  build/ominx-files build/ominx-control build/graphics-probe/ominx-graphics-probe
make media
python3 scripts/test-qt-target.py
```

The optional fifth input to the packager adds only `/bin/ominx-graphics-probe`.
Without it, the default image remains unchanged. This application paints known
colours, responds to Space and Return, and exits unsuccessfully after a timeout.
It has no username/password inputs or authentication implementation.

The separate `qt-target.yml` workflow reuses a **pinned, acceptance-passed,
source-built kernel artifact**, verifies its commit and SHA256 sums, then rebuilds
original target userspace and media. It never downloads a distribution rootfs.
The artifact dependency is intentional: an unsuccessful or expired core artifact
must cause failure, not fallback to a host kernel or another distro image.

Guest acceptance must verify the exact application colours in QEMU framebuffer
captures, actual virtual keyboard events delivered to Qt, UID 1000 before and
after execution, and a return to the original console. Cases cover Bochs/BIOS,
virtio/UEFI and QXL/BIOS. Host rendering cannot substitute for these checks.

Subsequent work still needs target Qt Quick, a proper seat/display stack, shared
library/plugin packaging, DBus, PAM/account provisioning, SDDM and KDE Plasma,
followed by real authentication/session lifecycle tests. See `graphics-login.md`.
