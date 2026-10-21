# Target shared graphics runtime acceptance

- Commit: `f0bc8f5d505ef9c900b25c19228be3dcb4b67d67`.
- Run: https://github.com/ma19031435-eng/OminX-Linux/actions/runs/39571680312
- Conclusion: **success**.
- Artifacts: `12331739713` (development bundle, 101,842,406 bytes) and
  `12332064393` (source SDK/sysroot + host tools, 11,855,972 bytes).
- Local package/target suite: **53 checks passed**.
- Kernel: the source kernel from run `39564535782` (commit
  `29ee23893c055263aa46fb68e701102d9005eb44`), re-verified by SHA256 before use.

## What this adds

Until now every target Qt artifact was **static** and drew through the accepted
kernel framebuffer path. This stage builds a real **shared** user-space graphics
SDK from source and validates it inside the booted image, using the same
`x86_64-linux-musl` compiler and no distribution packages.

Source-built and pinned in `desktop/graphics/sources.json` and
`desktop/graphics/source.env`: zlib 1.3.2, libffi 3.8.0, Wayland 1.24.0,
wayland-protocols 1.48, xkeyboard-config 2.38, libxkbcommon 1.9.2,
libdrm 2.4.134, Mesa 26.1.8, Expat (the pinned bus revision) and the source
GCC 14.3.0 / musl 1.2.6 compiler runtime.

Native build tools (wayland-scanner, host Expat) are built from the same source
into `build/graphics-host` and are never installed into the target sysroot.

## Guest evidence

Both `runtime-bios` (Bochs, BIOS) and `runtime-uefi` (virtio-gpu, UEFI) ran the
dynamically linked `ominx-render-probe` as UID 1000 twice each:

```
PASS Wayland shared-library protocol roundtrip
PASS XKB source keyboard data and modifiers
DRM driver: bochs-drm                      (virtio_gpu on UEFI)
PASS DRM shared-library device/resource query
Renderer: softpipe; GL: OpenGL ES 3.1 Mesa 26.1.8
PASS source shared graphics: Wayland, XKB, EGL and shader pixels
```

This proves the musl dynamic loader resolves the whole closure
(`ld-musl-x86_64.so.1`, libc, libstdc++, libgcc_s, libEGL, libGLESv2,
libwayland-client/server, libxkbcommon, libdrm, libffi, libz, libexpat), that
software GL shading actually rasterises verified red/green pixels, that the
unprivileged user can query real DRM resources, and that a second process can
repeat all of it. The console, power broker, storage, keyboard and framebuffer
regressions also ran in the same guests.

## Packaging and audit rules

`scripts/runtime-elf.py` parses every packaged object without executing it:
ELF64 x86-64, musl interpreter, no `RPATH`/`RUNPATH`, no text relocations, no
`GLIBC_` symbol versions, closed dependency graph inside the bundle, shared
libraries only for `NEEDED` entries, 0755/0644 modes and relative links.
`ldd` is never used, so nothing from the build tree is executed.
`scripts/stage-graphics-runtime.py` copies only shared objects, XKB data, the
render probe and license notices; it strips symbols, records a per-file SHA256
manifest (`build/provenance/graphics-runtime.json`), archives every verified
source, and fails closed if the compiler runtime resolves outside the source
toolchain. `make-initramfs.py --runtime-dir` refuses duplicate image paths.

`scripts/fetch-archive.py` now materialises bounded *internal* upstream source
aliases (Mesa's `.gitlab-ci/bin`, `.clang-format` links, libdrm test scripts) as
ordinary files, with cycle, depth, size and escape limits. No archive symlink is
ever extracted or followed, and reuse still requires byte-for-byte integrity.

## Not established

No Wayland compositor, display manager, desktop shell, KDE component or
hardware-accelerated driver is claimed. Only `softpipe` software GL is built;
LLVM, Vulkan, GBM/DRI hardware drivers, udev and X11 are out of this stage.
