# Unprivileged live-session acceptance

**Passed on 2026-10-20.**

- Tested revision: `e00cc4dd2af3f5ec45a012cc49a896f6d13d69c6`
- [Successful source build and acceptance run](https://github.com/ma19031435-eng/OminX-Linux/actions/runs/39468027444)
- [Download the tested images and evidence](https://github.com/ma19031435-eng/OminX-Linux/actions/runs/39468027444/artifacts/12285774394)
- Artifact: `OminX-x86-e00cc4dd2af3f5ec45a012cc49a896f6d13d69c6`
- Artifact expiry: 2026-11-03. Rebuild or rerun CI after expiry.

## Results

| Gate | Result |
|---|---|
| Automated suite with actual target executables and host-only pure policy-parser check | 19 passed |
| Default unprivileged ISO: BIOS PC, BIOS Q35, UEFI Q35, UEFI PC, BIOS USB | 5 passed |
| Explicit recovery ISO: full storage/keyboard/reboot/shutdown regression matrix | 5 passed |
| Recovery mode: FAT32, exFAT and NTFS read-only import/unchanged-image checks | 3 passed |
| Legacy Debian configuration checks | PASS |

The default-image tests checked real, effective and saved UID/GID 1000; zero
permitted, effective and ambient capabilities; `no_new_privs=1`; correct device
groups; private home/runtime ownership and modes; private new documents; refusal
to read shadow/root files or raw disks; refusal to administer mounts/power;
card/input ownership; local keyboard operation; and identity retention after both
exec and console restart. These tests booted firmware/media, not a mocked session.

Default-session VMs were terminated through the external QEMU manager after the
checks. They did not use a secret root helper or claim that an ordinary user could
power off the guest. Clean guest shutdown and filesystem integrity continue to be
verified in the explicitly privileged recovery matrix.

## Evidence

Retrieved from the successful run's actual annotations:

- [Default-session results](sessions/sessions.json)
- [Default-session PASS transcript](sessions/sessions.txt)
- [Recovery matrix PASS transcript](sessions/platforms.txt)
- [Windows filesystem results](sessions/windows-filesystems.json)
- [Automated test transcript](sessions/userspace.txt)
- `sessions/session-*-user.txt`: available serial transcript excerpt.

Full logs, framebuffer screenshots, kernel/compiler/source provenance and
checksums are in the artifact. The source-built toolchain remains separate from
the build host; no distribution target rootfs or libraries were substituted.

## Use the correct image

After extracting the artifact:

```sh
sha256sum -c SHA256SUMS
qemu-system-x86_64 -m 512 -cdrom ominx-x86_64.iso -boot order=d -serial stdio -nic none
```

The first boot-menu entry is the normal live user. It reaches
`ominx:/home/ominx$`. Use `id`, `files`, and ordinary document operations there.
Stop the VM through its host controls when finished. For intentional root
administration choose the normal image's second menu entry, clearly labelled root
recovery, or boot `ominx-recovery-x86_64.iso`. Never confuse that recovery image
with the default unprivileged image. Secure Boot remains unsupported.

This is an automatic single-user live session, not password authentication,
physical-access protection, multi-seat isolation or a KDE desktop. Character-device
permissions prepare for graphics/input integration; they do not demonstrate a
compositor or GPU acceleration. [Policy and limitations](../sessions.md).
