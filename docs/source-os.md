# Source-built architecture

## Target versus build host

The independent x86-64 target consists of upstream Linux, an original OminX
statically linked init/console, source-built musl libc and a source-built Limine
bootloader. The static executable is built by a dedicated upstream GCC/binutils
cross toolchain. No existing distribution's target binaries or libraries are
copied into the image. musl-cross-make is a pinned upstream compiler-build recipe,
not a distro or target userspace.

A Linux host and its bootstrap compiler, make, Python, autotools and other build
utilities are prerequisites. Using host build tools is not using a distro as the
target base. Host tests use a separate output directory; target packaging requires
the dedicated source toolchain and rejects a libc outside its directory.

## Segment-one implementation

- Pinned source builds with manifests and target ELF/static-link audit.
- Hybrid ISO with BIOS and x86-64 UEFI paths, compiled bootloader, local display
  terminal and an independent serial terminal. No Secure Boot signature yet.
- Original PID 1 supervises both console sessions and reaps orphaned children.
- Original command handling and basic filesystem operations, with errors surfaced.
- Explicit ext4 data mounts; no implicit formatting, partitioning or disk writes.
- Read-only attachment, sync, clean unmount on shutdown and console restart.
- Real media boot acceptance across a finite x86-64 virtual-hardware matrix,
  including keyboard events, screenshots, persistence, restart and filesystem checks.

Exact test results are in `validation/segment-one.md`. Firmware, device emulation
and host filesystem-authoring tools are test/build infrastructure, not target
root filesystems. Test cases create their own disposable disk files exclusively
and never accept a path to a physical disk.

## Subsequent file/storage increment

The original `ominx-files` backend, quoted paths, no-overwrite copy/move and
read-only FAT32/exFAT/NTFS imports are now implemented and tested. See
[the validation report](validation/files-and-storage.md) for the precise results;
a graphical file manager has not yet been integrated.

## Subsequent session increment

Normal boots now use an original UID/GID 1000 live-session setup, private home and
runtime directories, `no_new_privs`, and an explicit character-device group policy.
Root administration is a separately selected recovery mode. This is automatic
live login, not authentication or a completed desktop session manager. See
[sessions.md](sessions.md).

## Graphics and controlled-power increment

The target now includes a supervised power broker and additional kernel graphics
drivers. A separately tested SDDM theme is available, but target Qt/KDE and
authenticated graphical startup remain unfinished. See [graphics-login.md](graphics-login.md).

## Remaining product work

1. Physical-machine testing, additional CPU/device coverage and 32-bit x86 if needed.
2. Authenticated users, permissions policy, service lifecycle, networking, time,
   trust store, logging and security updates. The automatic single-user live session and separately selected root recovery
   are not authenticated multi-user login.
3. Source-build graphics/input dependencies, Qt, KDE Frameworks and Plasma;
   integrate the original OminX bottom-taskbar desktop and accessibility behavior.
4. Original graphical file manager, settings, setup and application-management
   services. Old Debian-specific app wrappers cannot simply be reused unchanged.
5. Windows-file workflows (explicitly define file formats/filesystems separately
   from running Windows executables), storage discovery and removable-media policy.
6. Installer, safe disk-selection UI, recovery, signed updates, rollback and a
   maintained security-release policy for all pinned upstream dependencies.

## Licensing and proprietary boundary

The repository remains AGPLv3. Establish ownership and a component-level licensing
policy before applying proprietary terms to original work. Linux and KDE remain
under their upstream licenses; do not imply that original branding changes that.
Static musl is under its upstream permissive license; GCC runtime use is governed
by its applicable exception and licenses. Keep all upstream notices and sources
as required. The pinned source recipes and generated provenance are useful for
rebuilding but do not alone constitute a complete compliant release-source offer.
Development images must undergo dependency/license/security review before product
release. No new proprietary license is asserted by these changes.
