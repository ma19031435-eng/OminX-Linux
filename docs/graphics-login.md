# Graphics, controlled services and the OminX login theme

## Runtime boundary — read this first

The independent image now has a root power broker and an expanded **kernel graphics
configuration**. The original login theme has been rendered and interaction-tested
with Qt 6, and rendered by an upstream SDDM greeter built on the **build host**.

**The default source-built image still boots its live console, not an authenticated
graphical login. It does not package Qt, SDDM/PAM, a display server or KDE Plasma.**
Optional development media now run source-built Qt and Qt Quick validation
applications, but still have no real display manager or desktop session.
No host Qt libraries or display-manager binaries are copied into the musl target.
A successful theme test is not a successful OS login. The old Debian image remains
a separate preserved build and is not used to bypass this distinction.

## Recorded acceptance

The [graphics/power results](validation/graphics-login.md) now include successful
Bochs, virtio and QXL guest checks. Separately, [target Qt raster tests](validation/target-qt.md)
passed in optional development media. That small Qt application is not a
display manager and does not enable graphical login in the default image.
[Target Qt Quick/theme acceptance](validation/target-qt-quick.md) now also passes
on those three emulated adapters, using an explicitly disabled authentication
context and an empty session model—not a fabricated Plasma login.

A separate [source-built desktop IPC stage](desktop-bus.md) now provides tested
system/session buses and fixed privilege-separated supervision in optional media.
An isolated [target Qt Core/DBus bootstrap](validation/target-qt-dbus.md) also
passes actual guest object-call tests. These stages do not yet connect the theme
to authentication or a KDE session.

## Controlled system service

`/sbin/ominx-control` is original C code, built statically with the source toolchain.
PID 1 starts it as a separate root process and supervises/restarts it. Ordinary
consoles and applications remain UID/GID 1000 with `no_new_privs` and no capabilities.

The sole endpoint is `/run/ominx/control.sock`, a root-owned Unix `SOCK_SEQPACKET`
socket in a root-owned non-user-writable directory. The socket is group 1000, mode
0660. The server obtains the actual client UID with `SO_PEERCRED`; only UID 0 and
the single live account UID 1000 are authorized. The client independently checks
that the service is root. There are exactly three request packets:

```text
status\n
poweroff\n
reboot\n
```

The literal newline is required. Extra arguments, embedded NULs, compound requests,
unknown commands and oversized messages are rejected. There is **no command
execution API**, arbitrary path argument, mount request, credential operation or
permission to launch an arbitrary root service. Each connection handles one bounded
packet, with receive/send timeouts so an idle client cannot hold it indefinitely.
A live existing service cannot be replaced by a second instance; stale owned socket
cleanup is restricted to sockets in the protected service directory.

At the normal console, `control` requests status; `reboot` and `poweroff` now go
through this broker. Power operations sync and attempt a clean data unmount;
a busy/unmount-failing data volume prevents the action rather than forcing it.
An `OK ...-requested` response acknowledges a request, not a completed hardware
transition. Tests separately wait for the kernel reboot/power-down result.
Mount/import administration still requires explicit recovery mode.

This policy intentionally allows **any process of the single live account** to
request power changes. It is not authenticated multi-user/remote authorization or
an active-seat policy engine. It does not implement arbitrary service management,
network management, login authentication or a general polkit replacement.

## Kernel graphics and terminal facilities

The build enables firmware framebuffer/simpledrm, fbcon, Bochs, virtio-gpu, QXL,
VMware, Intel i915, AMDGPU and Nouveau kernel drivers. Drivers are built into the
kernel because the current image has no module distribution mechanism. Device
ownership continues to follow the documented single-seat video/render/input policy.
A private devpts instance and `/dev/ptmx` link provide the standard PTY foundation
for future graphical terminal applications.

The virtual graphics acceptance script checks actual native framebuffer driver
names, character-device permissions, a nonblank screenshot, keyboard input and
broker poweroff. It does **not** test Mesa, OpenGL, Vulkan, EGL, hardware video
acceleration, a compositor or arbitrary monitor configurations.

Intel/AMD/Nouveau/VMware being compiled is not physical-hardware certification.
Many real GPUs need separately licensed firmware that is not bundled here, and
new hardware may require different drivers/kernel versions. No universal GPU
support or proprietary NVIDIA-driver support is claimed. Consult the recorded
results for the emulated adapters actually tested.

## Styled login area

`desktop/sddm/ominx/` contains an original Qt Quick SDDM theme intended for a
Plasma session, not copied Microsoft artwork or a browser mockup. It provides:

- Original Aurora vector background and OminX identity.
- Username, masked password, keyboard submission and caps-lock indication.
- Session selection from SDDM's session model; no fabricated session launch.
- Busy-state duplicate-submit prevention, failed-login feedback and password clearing.
- Confirmed restart/shutdown callbacks, gated by SDDM's exposed capabilities.
- Responsive 1440×900, 1024×768 and 800×600 layouts and accessibility labels.

Authentication calls `sddm.login(...)`; the theme neither validates nor stores
passwords. The source-built OS currently has locked password records and automatic
live-console login. It does not yet have a provisioned password/login workflow.
Do not substitute a hardcoded password or pretend that pressing the sign-in button
in a test harness authenticated a user.

Two host-only test layers are kept distinct:

1. PySide6/Qt 6 renders and exercises the theme with a **mock SDDM context**. This
   validates layout, masking, keyboard behavior, failed/busy state and callbacks.
2. Pinned upstream SDDM 0.21.0 is compiled against the host's Qt 6 and launches the
   theme in **test mode**, checking that no fallback theme or QML errors occur.
   This validates real SDDM theme compatibility, not PAM or session startup.

The small preview in `validation/graphics-login/login-preview.png` is an actual
Qt-rendered test image with a demonstration account, downscaled/quantized for review.
Full screenshots are in the theme workflow artifact. The theme is intentionally
not enabled in target init while its runtime dependencies are absent.

## Required before this request can be called complete

1. Source-build a target graphics stack: libdrm, Mesa/software rendering as needed,
   Wayland/X11, libinput, xkbcommon, device discovery and a seat/session implementation.
2. Source-build target Qt 6 and the required KDE Frameworks/Plasma components;
   extend image packaging for their audited runtime libraries, plugins, data and licenses.
3. Source-build and configure SDDM, PAM/password hashing and DBus integration,
   secure account provisioning, and appropriate greeter/helper/session privileges.
4. Integrate the theme at boot and verify correct/incorrect authentication, logout,
   relogin, session launch, display/input handoff and ordinary-user power controls
   inside the independent image. Mock greeter tests cannot replace these checks.
5. Expand a concrete physical GPU/firmware/display support matrix and review the
   remaining security, recovery and release/license requirements.

Until those gates pass, the login theme is ready for integration; **boot-time
KDE graphical login is unfinished**.
