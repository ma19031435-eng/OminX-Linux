# Source-built target Qt Quick / actual-theme acceptance

## Accepted build

- Commit: `53d0858771eac13a5f1866b7c7d1cc669fc8c2ce`.
- Run: https://github.com/ma19031435-eng/OminX-Linux/actions/runs/39500949274
- Conclusion: **success**.
- Artifact: `12303150224`, `OminX-target-QtQuick-development-53d0858771eac13a5f1866b7c7d1cc669fc8c2ce`, 20,007,921 bytes.
- Initial full dependency/guest acceptance also passed at commit
  `005178852fa8331a72e41bb3c4346fed124d304a`, run `39493780444`, artifact `12300590327`.
- Kernel input remains the SHA256-verified accepted source build
  `35514119f11e775ab696d6c3c67be5c221366848`, run `39482457386`.

Qt ShaderTools and Qt Declarative/Quick 6.8.3 were built from pinned upstream
sources using the original source GCC/musl toolchain. Native host Qt tools were
built separately. No distro Qt/runtime package was installed into the guest.
The application was checked for x86-64 static ELF/no PT_INTERP before packaging.

## Observed guest results

All three real-media cases passed as UID 1000:

| Case | Firmware | Verified |
| --- | --- | --- |
| Bochs standard VGA | BIOS | Actual theme pixels, keyboard input, masking, no-session refusal, Escape clearing, console return |
| virtio GPU | UEFI | Same checks |
| QXL | BIOS | Same checks |

Tests use the original `desktop/sddm/ominx/Main.qml`, not a recreated browser
layout. They capture QEMU's actual framebuffer, check theme/banner colours, send
virtual keyboard events, and require the expected input-state transitions. They
also verify identity after returning to the console and broker-mediated poweroff.

`target-qt-quick/guest-results.txt` preserves the published case results.
`results-json-tail.txt` is explicitly a truncated JSON excerpt, not a standalone
JSON file. Complete structured results, guest logs and full PPM captures are in
the artifact.

`target-qt-quick/guest-preview.png` is the actual Bochs guest capture, downscaled
to 800×500 and quantized for review. It was visually inspected. The validation
banner is intentional; its presence is also checked in the guest test. It is not
an image-generation mockup and is **not** an authenticated login screenshot.

## Boundaries

The application supplies an empty session model and a disabled SDDM-compatible
context, not the upstream SDDM daemon. The session selector therefore does not
invent a Plasma installation. Submitting the dummy test strings must display
“No desktop session is installed.” Any call to the disabled authentication/power
backend fails the test; no credentials are authenticated or stored.

This establishes **target Qt Quick rendering and theme/input compatibility**.
It does not establish source SDDM/PAM, account provisioning, successful password
login, Wayland/KWin, Mesa acceleration, Plasma startup, logout or relogin. The
normal image still starts the original live console; the optional validation
application is not automatically started at boot. The full requested graphical
login and KDE desktop are still unfinished.

The core regression workflow also passed with the extended packager at
https://github.com/ma19031435-eng/OminX-Linux/actions/runs/39492042637
(commit `1354409d7cd1b25c8388c3def0e3d2f45d102a11`). Local userspace/packaging checks
now total 31 passing tests. The old Debian build remains separate and preserved.
