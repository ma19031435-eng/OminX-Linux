# Source-built target Qt raster acceptance

- Implementation/workflow commit: `73f2d309e3e9587dcf3dfe3284d169ae4bb3466c`.
- Run: https://github.com/ma19031435-eng/OminX-Linux/actions/runs/39482539951
- Conclusion: **success**.
- Artifact: `12292783393`, `OminX-target-Qt-development-73f2d309e3e9587dcf3dfe3284d169ae4bb3466c`, 12,236,029 bytes.
- Kernel input: acceptance-passed source commit `35514119f11e775ab696d6c3c67be5c221366848`,
  run `39482457386`; its artifact SHA256 sums were checked before repackaging.
- Upstream Qt 6.8.3 base commit: `c07c2d5a527a644d36e7853d55132ae38921682f`.

Qt Core/Gui/Widgets and the original acceptance application were cross-compiled
with the source-built GCC 14.3/musl 1.2.6 toolchain. Native Qt code generators were
built separately; no host Qt runtime libraries were copied into the guest. The
packager verified the probe is an x86-64 static executable without PT_INTERP.

All three actual media cases passed:

| Case | Firmware | Display | Observed |
| --- | --- | --- | --- |
| qt-bochs | BIOS | Bochs standard VGA | Qt raster colours, actual keyboard input, exit to user console |
| qt-virtio | UEFI | virtio GPU | Qt raster colours, actual keyboard input, exit to user console |
| qt-qxl | BIOS | QXL | Qt raster colours, actual keyboard input, exit to user console |

Each guest ran Qt as UID 1000, received Space/Return through QEMU keyboard events,
and displayed the application's exact expected RGB regions in framebuffer captures.
A nonblank firmware picture alone would not pass. Tests verified identity again
after the application exited and powered off through the controlled service.

`target-qt/qt-guest.txt` contains the published three-case result.
`target-qt/qt-target-json-tail.txt` is explicitly a **truncated JSON excerpt**, not
a standalone JSON document; complete structured results and PPM images are in the
artifact. No screenshot here is presented as a KDE login.

This proves a source-linked, unprivileged **Qt software-framebuffer application**
runs inside the independent OS. It does not prove Qt Quick, SDDM, PAM, passwords,
KDE Plasma, OpenGL/Vulkan, hardware acceleration or a desktop session lifecycle.
The optional probe is not included in the normal image unless requested during
packaging. The full graphical-login request remains unfinished.
