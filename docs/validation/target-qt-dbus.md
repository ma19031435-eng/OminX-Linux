# Target Qt DBus acceptance

- Commit: `1d93ad25f09ed9d1ab5f62f2441967a60248c0ff`.
- Run: https://github.com/ma19031435-eng/OminX-Linux/actions/runs/39566686000
- Conclusion: **success**.
- Artifact: `12330996115`, `OminX-qt-bus-development-1d93ad25f09ed9d1ab5f62f2441967a60248c0ff`, 78,031,533 bytes.
- Original target, package and source-integrity suite: **40 checks passed**.
- Target Qt: upstream 6.8.3, QtBase commit
  `c07c2d5a527a644d36e7853d55132ae38921682f`.
- D-Bus/Expat and kernel: the source-built dependencies and verified kernel
  described in [desktop bus acceptance](desktop-bus.md).

## What ran inside the guest

Both BIOS and UEFI normal-session cases executed
`/bin/ominx-qt-bus-probe --guest-test` as UID 1000 after the C bus lifecycle tests.
The static target executable uses the actual Qt Core and Qt DBus libraries,
directly linked to the source-built musl libdbus, not a host Qt package or a mock.

The probe checked:

1. Protected source-boot context and an explicit unprivileged invocation.
2. Connection to the fixed system socket and discovery of daemon UID 81 through
   a Qt DBus method call.
3. Refusal to register a system service name, with `QDBusError::AccessDenied`.
4. Two distinct session bus connections with distinct unique names.
5. Actual registration of a Qt `QObject` with an exported method and service name.
6. Refusal of duplicate ownership on the other connection.
7. Asynchronous invocation through the other connection, Qt event-loop dispatch,
   and a correctly typed string response within a bounded timeout.

The existing bus policy, credential, restart, machine-ID and original power-broker
checks also passed, including the separate root recovery isolation/lifecycle case.
The Qt object test is **not** run in that root case; the result JSON records that
explicitly. Guest transcripts and result JSON are in `target-qt-dbus/`.

## Build boundary and upstream metadata correction

`scripts/build-qt-bus-target.sh` uses isolated `qt-bus-host`, `qt-bus-target` and
`qt-bus-prefix` directories. Native source-built generators are not packaged.
Target discovery is restricted to the source toolchain and source-built prefixes.
The resulting executable passes the x86-64 static ELF/no-interpreter check.

The upstream D-Bus CMake package treated pkg-config's `-pthread` option as a macro,
producing `-D-pthread` during Qt DBus automoc predefine generation. Failed runs
`39564536008` and `39565533090` exposed this genuine build error. The recipe now
changes that installed metadata property from `INTERFACE_COMPILE_DEFINITIONS`
to `INTERFACE_COMPILE_OPTIONS`, preserving the option rather than dropping it.
The verified upstream source tree is unmodified, and the adjusted CMake file is
saved in build provenance. The successful run's configure log identifies the
source-prefix `libdbus-1.a` version 1.16.2.

The artifact includes the pinned QtBase source archive, upstream bus/Expat source
archives, license texts, configuration, ELF/hash evidence and logs. Optional
packaging requires both the bus bundle and Qt license texts. Missing prerequisites
or invalid executable input fail closed; ordinary image packaging is unchanged.

## Default-image regression

The full source core workflow at `29ee23893c055263aa46fb68e701102d9005eb44`,
which added the optional Qt-bus packaging path, also succeeded:
https://github.com/ma19031435-eng/OminX-Linux/actions/runs/39564535782
It passed 40 checks and the normal-session, recovery/storage, Windows-filesystem
and framebuffer guest matrices. Subsequent changes before this Qt acceptance
only corrected the dedicated Qt build/diagnostics and documentation.

## What this does not establish

This is a **Core/DBus dependency bootstrap**, separate from the accepted
framebuffer/Quick build. Do not mix libraries from their different Qt feature
configurations. A consolidated GUI/DBus SDK and a shared-library desktop runtime
still need to be built and validated for KDE integration.

This does not provide PAM/password login, seat/device handoff, an SDDM daemon,
a compositor or a Plasma session. No graphical login or complete desktop is
claimed. Unix-FD passing and broader KDE-specific DBus interfaces have not yet
been tested by this probe.
