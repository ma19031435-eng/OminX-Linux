# Segment one acceptance: boot to the OminX terminal

## Verified result

- Date: 2026-10-20
- Tested source: `663eef5ac547ce3d19cdbc5c9e51dd3580372166`
- [GitHub Actions run 39441574159](https://github.com/ma19031435-eng/OminX-Linux/actions/runs/39441574159)
- Runner: Ubuntu 24.04; guest: upstream Linux 6.12.0, original static OminX userspace
- Machine: QEMU x86-64, 256 MiB RAM, serial console, no guest network or attached data disk
- Result: kernel build, six host tests, and real guest boot acceptance all passed
- Evidence: [last 45 lines of the guest boot/test log](first-terminal-boot.txt),
  retrieved from the run's `boot.log` annotation, not a simulated transcript

The test explicitly waits for prompts and command responses. It verifies:

1. Linux executes `/init` and the OminX terminal appears.
2. `uname` reports the running guest kernel.
3. `write` and `cat` round-trip data in the guest filesystem.
4. `exit` restarts the console without exiting PID 1 or panicking the kernel.
5. The file remains available after console restart (not after a reboot).
6. `poweroff` produces the kernel's power-down message and QEMU exits successfully.

## Run the verified image

Download the artifact named
`OminX-core-663eef5ac547ce3d19cdbc5c9e51dd3580372166` from the linked run.
It contains `bzImage`, `initramfs.cpio.gz`, `SHA256SUMS`, the kernel source commit,
and build/boot logs. GitHub retains this development artifact for seven days;
after expiry, rebuild from the tested source or rerun the workflow.

Extract it into a directory, install `qemu-system-x86_64` on your host, and run
from that directory:

```sh
sha256sum -c SHA256SUMS
qemu-system-x86_64 -m 256 \
  -kernel bzImage -initrd initramfs.cpio.gz \
  -append 'console=ttyS0 rdinit=/init panic=-1' \
  -nographic -no-reboot -nic none
```

The checksums detect corruption; they are not a signed authenticity mechanism.
At `ominx:/root#`, enter `help`, `uname`, or file commands. Enter `poweroff` to
shut down, or use QEMU's Ctrl-A then X escape to terminate the emulator.
Do not attach real disks for this first-terminal milestone.

To repeat the automated test, extract the artifact into the checkout's `build/`
directory and run `python3 scripts/smoke-boot.py` with QEMU installed. To rebuild
from source instead, follow the root README's `LINUX_SOURCE` instructions.

## Boundaries

This is a directly kernel-booted, RAM-only development system. It is not an ISO,
USB installer, UEFI bootloader, persistent OS or KDE desktop. It has no login
security and must not be exposed as a multi-user or network-accessible system.
The boot log includes expected missing wireless regulatory database and soundcard
messages; neither device class is supported or required for this milestone.
Upstream license/source distribution obligations still apply.
