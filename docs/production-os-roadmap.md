# OminX production OS: architecture and acceptance roadmap

**Status:** planning baseline, not a statement that the current ISO is production-ready.

## Architecture boundary

- **Linux kernel:** schedules processes, manages memory, drivers, filesystems, networking, and hardware interfaces. It is not Debian and is distributed under its own license and notices.
- **Debian base:** an upstream distribution and package ecosystem, not a kernel. A minimal Debian installation can provide the kernel, init system, libraries, package manager, and security updates. Debian packages retain their upstream licenses.
- **KDE Plasma:** the current desktop foundation. Plasma and KDE Frameworks retain their upstream open-source licenses. OminX may ship original branding, configuration, themes, widgets, and independent applications, but cannot relicense KDE as proprietary.
- **OminX-owned software:** can be developed as original, separately packaged components and offered under a proprietary license only after confirming that OminX has the necessary rights to every contribution and dependency. The repository currently declares AGPLv3; this plan does not change that license.

A strict proprietary operating system userland is incompatible with using Debian's userland and KDE Plasma unchanged. If that requirement is absolute, the architecture must be re-scoped before implementation. A Debian/Plasma product can instead have a proprietary OminX product layer while respecting all upstream licenses.

## Product layers

1. **Boot and install:** reproducible live-build output; tested BIOS/UEFI and Secure Boot paths; signed release checksums; installation, recovery, and rollback workflows.
2. **Base system:** minimized Debian package set; supported kernel and firmware matrix; secure defaults; unattended security-update policy with user-visible controls.
3. **Desktop:** KDE Plasma session with the original OminX Aurora shell configuration and artwork; a documented compatibility boundary around upstream KDE components.
4. **OminX product layer:** independently packaged launcher, welcome/setup, settings center, software-store integration, update/status surfaces, performance and compatibility tools, and system-information services.
5. **Application and game compatibility:** explicit support tiers and tested title/device matrix. No universal Windows-application or hardware-performance guarantees.
6. **Operations:** signed repositories, release channels, vulnerability response, crash/reporting policy, backup/recovery guidance, support policy, and reproducible build provenance.

“Features from every OS” is not a finite acceptance criterion. Each requested capability must be named, assigned to an upstream or OminX-owned layer, and given a test and support tier before it is included in a release.

## Production gates

A release is not production-ready until all applicable gates pass:

- **Build/release:** clean reproducible build, source/run provenance, signed checksums, verified installer media, and upgrade/recovery tests.
- **Security:** dependency and vulnerability review, threat model, least-privilege services, polkit review, secure update/signing design, and a published response process.
- **Reliability:** install/upgrade/recovery tests across supported machines and virtual machines; boot, login, suspend/resume, storage, networking, audio, graphics, and peripheral coverage.
- **Quality:** automated unit/integration/UI tests, accessibility checks, package validation, crash-free release criteria, and a defined supported-hardware matrix.
- **Maintenance:** release cadence, supported versions, rollback policy, documentation, and user support boundaries.

## LOC quota policy

The requested **1,500,000 lines of meaningful code** is a long-term scale target, not something this migration or one build can honestly deliver. Track original production source and tests separately with a pinned counting tool and publish the report per release. Exclude generated files, vendored/upstream code, build output, binaries, and whitespace-only changes. LOC is a progress metric only; it does not replace review, tests, security, or maintainability. No filler code will be added to satisfy the number.

## Immediate baseline

The current repository is a Debian live-build prototype with a Plasma migration in progress. Static recipe checks, Debian package resolution, and GTK smoke tests passed on the latest workflow attempt; the ISO build had not completed at the last status check. This roadmap does not claim that an installable Plasma ISO or a production OS has been verified.
