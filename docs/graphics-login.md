# Graphics, controlled services and the OminX login theme

## Runtime boundary — read this first

The independent image now has a root power broker, an expanded **kernel graphics
configuration**, and an original **graphical login**: a root authentication
broker, a seat supervisor, and a source-built Qt Quick login screen plus desktop
session. That stack is validated end to end in real guests —
see [graphical login acceptance](validation/graphical-login.md).

**The default source-built image still boots its live console.** The graphical
login ships in optional media produced with `--login-dir`; it is not yet the
default boot path, and it is a framebuffer login, not a compositor session.
There is still no SDDM daemon, no PAM, no X11/Wayland display server and no KDE
Plasma in any image. No host Qt libraries or display-manager binaries are copied
into the musl target, and the old Debian image remains a separate preserved build
that is not used to bypass this distinction.

## Recorded acceptance

The [graphics/power results](validation/graphics-login.md) now include successful
Bochs, virtio and QXL guest checks. Separately, [target Qt raster tests](validation/target-qt.md)
passed in optional development media. That small Qt application is not a
display manager and does not enable graphical login in the default image.
[Target Qt Quick/theme acceptance](validation/target-qt-quick.md) now also passes
on those three emulated adapters, using an explicitly disabled authentication
context and an empty session model—not a fabricated Plasma login.

[Graphical login acceptance](validation/graphical-login.md) now covers the
original login broker, seat supervisor and Qt Quick login/session on BIOS and
UEFI media, including a refused password, socket-level isolation from the signed-in
user, an authenticated session, logout, login-screen poweroff, and recovery-side
password changes verified by musl `crypt`.

A separate [source-built desktop IPC stage](desktop-bus.md) provides tested
system/session buses and fixed privilege-separated supervision in optional media.
An isolated [target Qt Core/DBus bootstrap](validation/target-qt-dbus.md) passes
actual guest object-call tests, and a source-built [shared graphics runtime](validation/graphics-runtime.md)
(Mesa softpipe EGL/GLES, Wayland, libxkbcommon, libdrm) passes real shader and
protocol checks as an unprivileged user. Those graphics and IPC stacks are not yet
joined to the login session: the login screen renders on the kernel framebuffer
with static Qt Quick, and no compositor, KDE component or DBus-driven session
service runs yet.

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
Full screenshots are in the theme workflow artifact.

The same artwork now also runs **in the target image** as the real login screen:
`desktop/desktop-shell/GreeterRoot.qml` embeds `desktop/sddm/ominx/Main.qml`
unchanged and supplies a genuine authentication context instead of the mock one,
so the theme is exercised by both harnesses without diverging.

## Achieved and still open

Achieved and guest-verified:

1. A source-built target graphics stack (Mesa softpipe EGL/GLES, Wayland client and
   server libraries, libxkbcommon with real keymap data, libdrm) with an audited
   musl shared-library closure — [evidence](validation/graphics-runtime.md).
2. An original login stack: root authentication broker, seat supervisor, Qt Quick
   login screen and desktop session, recovery password tool, and packaging that
   fails closed on malformed account records —
   [evidence](validation/graphical-login.md).
3. Correct/incorrect authentication, logout and relogin, session launch as the
   authenticated user, login-screen power through the fixed power broker, and
   isolation of the login service from the signed-in user, all inside real BIOS
   and UEFI guests.

Still open:

1. A real compositor session: the login screen and session draw directly on the
   kernel framebuffer with static Qt Quick. Window management, the shared
   Wayland/Mesa runtime, and DBus session services are not yet joined to it.
2. KDE Frameworks/Plasma components are not built; the session shell is original
   QML with a Windows-familiar layout, not Plasma.
3. Account provisioning is limited to the packaged records: no account creation,
   expiry, or non-local authentication.
4. A physical GPU/firmware/display support matrix beyond the emulated adapters,
   and the remaining release/license review.

**Boot-time KDE Plasma graphical login is still unfinished**; what is finished and
verified is an original graphical login and desktop session on the source image.
