# Source-built architecture and acceptance gates

## Implemented foundation

The target image contains an upstream Linux kernel and a static original OminX
executable linked with the build host's libc. OminX implements PID 1 supervision,
orphan reaping, pseudo-filesystem setup, a console, basic file commands and power
controls. A Python build-host utility writes the Linux newc initramfs format;
neither Python nor a third-party shell is included in the image. The original
console is intentionally small, not a replacement for every POSIX utility.

Static libc is still a third-party dependency. Distribution must respect its
license (including applicable LGPL relinking/source obligations when using glibc).
Kernel source, build configuration, notices and corresponding sources must be
provided as their licenses require. A CI binary artifact is a development artifact,
not a complete compliant release package. Review and assemble those materials
before product distribution.

## Ownership and proprietary boundary

The user accepts open-source upstream infrastructure. Write original product logic
where practical; do not duplicate mature cryptography, browser engines, graphics
stacks or hardware drivers merely to call them proprietary. Linux and KDE are not
original OminX code. KDE modifications must follow each component's license.

The repository license is AGPLv3 and remains unchanged. Establish contributor
ownership and a component-level licensing policy before adding proprietary terms.
Separate processes are not automatically exempt from license obligations; review
interfaces, linking and derived code. Preserve upstream notices and track sources.

## Remaining milestones (not claimed complete)

1. Run kernel boot acceptance on CI and local VM; exercise failure/restart paths.
2. Choose a maintained kernel, reproducible toolchain/libc and verified source lock.
3. Persistent filesystem lifecycle, safe disk selection and recovery; no implicit
   formatting or installation. Dedicated image/USB bootloader and UEFI testing.
4. Users, authentication, permissions, device/session lifecycle, service management,
   networking, time, TLS trust, logging and updates. The current root console is not
   a security boundary or a general service manager.
5. Source-build graphics/input dependencies, Qt, KDE Frameworks and Plasma. Integrate
   original taskbar/launcher design with native KDE behavior and accessibility.
6. Original installer, setup, settings and application-management services; do not
   wire the old Debian-specific wrappers into a non-Debian system unchanged.
7. A signed update protocol, atomic upgrade/rollback, licensing materials, dependency
   inventory, vulnerability response and supported-hardware testing.
8. Desktop acceptance: boot/login, launch file manager and browser, configure a
   network, audio playback, persistent documents, reboot, upgrade and recovery.

A console boot is useful engineering progress but does not satisfy desktop
acceptance. The old Debian ISO and new standalone build are separate tracks;
retaining the former is a migration safety measure, not an assertion that it meets
the independent-source architecture.
