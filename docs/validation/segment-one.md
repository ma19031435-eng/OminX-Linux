# Segment one — x86-64 source-built media acceptance

**Completed on 2026-10-20 against the matrix below.** This supersedes the original
single direct-kernel serial-console experiment.

- Tested revision: `c753b4671c41dd68192c87b67e591032fff19fb4`
- [Successful build and acceptance run](https://github.com/ma19031435-eng/OminX-Linux/actions/runs/39448085192)
- [Download the tested ISO and evidence](https://github.com/ma19031435-eng/OminX-Linux/actions/runs/39448085192/artifacts/12277394973)
- Artifact: `OminX-x86-c753b4671c41dd68192c87b67e591032fff19fb4`
- Artifact expiry: 2026-11-03; rebuild or rerun the workflow after expiry.

## Source-only target

The target uses Linux 6.12.60, musl 1.2.6, original OminX init/console and Limine
8.7.0. GCC 14.3.0 and binutils 2.44 were built from upstream source with the pinned
musl-cross-make recipe. The successful acceptance run restored that source-built
toolchain from this branch's CI cache, compiled the target and bootloader, and
verified that the target libc resolves inside the dedicated toolchain.

There is no Debian/Ubuntu/other distro rootfs, package manager, or copied host libc
in this ISO. Ubuntu is only the build/test host. The old Debian build remains
available separately and was not used to satisfy this milestone.

## Passed matrix

All cases booted the **actual hybrid ISO through firmware and Limine**, not through
QEMU's direct `-kernel` shortcut. Tests used software CPU emulation (TCG).

| Case | Firmware | Machine | CPU model | RAM | Boot media | Data disk | Result |
|---|---|---|---|---|---|---|---|
| bios-pc-256 | SeaBIOS | PC/i440FX | qemu64 | 256 MiB | CD-ROM ISO | virtio-blk | PASS |
| bios-q35-512 | SeaBIOS | Q35 | max | 512 MiB | CD-ROM ISO | SATA/AHCI | PASS |
| uefi-q35-512 | OVMF | Q35 | qemu64 | 512 MiB | CD-ROM ISO | virtio-blk | PASS |
| uefi-pc-1024 | OVMF | PC/i440FX | max | 1024 MiB | CD-ROM ISO | NVMe | PASS |
| bios-usb-512 | SeaBIOS | Q35 | qemu64 | 512 MiB | ISO as USB mass storage | virtio-blk | PASS |

Each case passed:

1. Firmware/media boot into the OminX terminal and correct kernel/OS identity.
2. Independent serial terminal and virtual PS/2 keyboard input into the local
   display terminal; keyboard-created file read back over serial; screenshot saved.
3. Write, copy, move, read and delete commands; invalid command and missing-file errors.
4. Rejection of a non-block device as a data mount, and of duplicate data attachment.
5. Console restart after `exit`, without killing PID 1 or losing RAM files.
6. Ext4 write/read/detach, shutdown, a **new QEMU process**, and data read-back.
7. Read-only attachment with actual write refusal.
8. Guest reboot through firmware, another persistent-data read, and clean poweroff.
9. Host-side read-only `e2fsck -fn` of the disposable data filesystem after shutdown.

That is 15 firmware boots (two cold starts and one guest reboot per case), plus
**eight passing tests against the actual musl-linked executable**. The successful
workflow explicitly enables Bash `pipefail`, so `tee` cannot hide build/test errors.
An earlier attempt had an incorrect Limine toolchain-prefix setting and masked
pipeline failures; that attempt is **not** accepted evidence.

## Evidence

- [Five-case PASS summary](x86-media/platform-results.txt), retrieved verbatim from
  the successful run's `platforms.log` annotation.
- [Machine-readable summary](x86-media/summary.json), derived from that PASS summary.
- `x86-media/*-write.txt` and `*-read.txt`: available annotation excerpts (last 65
  lines), not fabricated or complete transcripts. GitHub caps annotation counts;
  not every full log is reproduced in the checkout.
- The downloadable artifact contains the full serial transcripts, screenshots,
  complete `acceptance/results.json`, source/compiler provenance and checksums.

## Boot the tested artifact

Extract the artifact, verify the checksums, then boot its ISO:

```sh
sha256sum -c SHA256SUMS
qemu-system-x86_64 -m 512 -cdrom ominx-x86_64.iso \
  -boot order=d -serial stdio -nic none
```

Use the display window's keyboard or the serial terminal. Enter `help` to see
commands, `exit` to restart the current console, and `poweroff` to shut down.
Secure Boot must be off. The checksums detect corruption; they are not signatures.

For UEFI on a host with OVMF installed, copy the variable store before running:

```sh
cp /usr/share/OVMF/OVMF_VARS_4M.fd ./ominx-vars.fd
qemu-system-x86_64 -machine q35 -m 512 \
  -drive if=pflash,format=raw,unit=0,readonly=on,file=/usr/share/OVMF/OVMF_CODE_4M.fd \
  -drive if=pflash,format=raw,unit=1,file=ominx-vars.fd \
  -cdrom ominx-x86_64.iso -boot order=d -serial stdio -nic none
```

To repeat acceptance, place the artifact's ISO in the checkout's `build/` directory
and run `make boot-check` with QEMU, OVMF and e2fsprogs installed. Tests exclusively
create their own disposable regular disk files; they do not operate on host block
devices. A failed run retains its `build/acceptance/*-data.raw` file for inspection;
remove only those disposable files before rerunning a failed case.

## Scope of this completion

Segment one is the source-built x86-64 boot/media/terminal/storage foundation
specified and tested above. These results are not physical-hardware certification,
32-bit i686 support, Secure Boot validation or testing of every emulator. The next
product segment can build the desktop, richer userspace, graphical file manager
and Windows-file workflows on this foundation. Physical-machine testing remains
a separate requirement before claiming support for particular real PCs.
