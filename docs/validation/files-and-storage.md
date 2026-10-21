# Original file backend and Windows-filesystem acceptance

**Passed on 2026-10-20.**

- Tested source: `87372939b4247110f8ddcde179ad7246348b4be2`
- [Successful source build and full acceptance run](https://github.com/ma19031435-eng/OminX-Linux/actions/runs/39455615377)
- [Download the tested ISO and full evidence](https://github.com/ma19031435-eng/OminX-Linux/actions/runs/39455615377/artifacts/12280299360)
- Artifact: `OminX-x86-87372939b4247110f8ddcde179ad7246348b4be2`
- Artifact expiry: 2026-11-03. Rebuild or rerun the workflow after expiry.

The kernel, bootloader and both target executables were built with the existing
source-built cross toolchain. The original Debian build remains separate and was
not used for any target image or acceptance result.

## Results

| Gate | Result |
|---|---|
| Host-side hardened compiler build and unit tests | 17 passed |
| Actual musl-linked target executable tests | 17 passed |
| BIOS PC, BIOS Q35, UEFI Q35, UEFI PC, BIOS USB matrix | 5 passed |
| FAT32 (`vfat`) read-only listing/read/import and protection | PASS |
| exFAT read-only listing/read/import and protection | PASS |
| NTFS (`ntfs3`) read-only listing/read/import and protection | PASS |
| Legacy configuration checks | PASS |

All five firmware cases now also run the packaged `/bin/ominx-files` backend via
the console's `files` alias: quoted names, copy, overwrite refusal, listing, move
and explicit removal. The prior keyboard, persistence, reboot, poweroff and ext4
integrity checks remain enabled.

For each Windows filesystem a fresh UEFI Q35 guest mounted a disposable fixture
read-only, listed and read `Windows Notes.txt`, imported it to a quoted name in the
OminX RAM filesystem, then attempted writing and deletion. Both were refused. The
SHA-256 of the entire fixture before and after the guest run was identical.
Fixtures contained plain text with CRLF line endings. This does not establish
support for encrypted, hibernated, damaged or every compressed NTFS volume.

An earlier run passed FAT32 and the five platform cases but could not prepare the
exFAT fixture because the host rejected loop mounting. The test was changed to
seed that fixture in a separate QEMU guest with a **test-only initializer** and the
source-built kernel. That helper is not included in the product initramfs or ISO.
No privileged host mount is required by the successful test.

## Recorded evidence

The files below were retrieved from the successful run's annotations, not generated
as illustrative examples:

- [Target test transcript](files-and-storage/target-tests.txt)
- [Five-platform results](files-and-storage/results.json)
- [Windows filesystem results](files-and-storage/windows-filesystems.json)
- [Windows filesystem PASS summary](files-and-storage/windows-filesystems.txt)
- `files-and-storage/windows-*-readonly.txt`: serial transcript excerpts.

The run artifact contains the full serial logs, screenshots, source provenance,
checksums and the actual BIOS/UEFI ISO. Existing QEMU boot instructions in
[segment-one.md](segment-one.md) also apply to this newer artifact. Verify
`SHA256SUMS` after extraction before using the ISO.

## Layer completed and next dependency gate

This is a verified **file-management backend and storage-interoperability layer**.
The interface is currently console commands plus JSON, not a graphical file-manager
window. [Command contract and safety details](../files-and-storage.md).

Next: unprivileged users/session ownership and graphics/input permissions, then
source-built display and Qt/KDE dependencies, and an original graphical frontend.
Windows filesystems are distinct from Windows application execution; no Wine/EXE
compatibility claim is made by this result. Physical hardware and arbitrary user
volumes were not used as test fixtures.
