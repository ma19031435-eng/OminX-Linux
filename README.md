# OminX — independent source-built OS

OminX is migrating from a Debian live-image recipe to an independent Linux-based
system with original OminX userspace and a future customized KDE Plasma desktop.
**The new build currently produces a minimal RAM-only console foundation, not a
finished desktop, installer, or production-secure OS.** It does not use Debian
packages or BusyBox in the target image. Host build tools are still required.

## Build and test

On an x86-64 Linux host, install a C compiler with static libc, make and Python 3.
For the kernel also install flex, bison, bc, libelf/OpenSSL development headers;
QEMU's x86 system emulator is needed for boot testing. On Debian/Ubuntu hosts:

```sh
sudo apt-get install build-essential python3 flex bison bc libelf-dev libssl-dev qemu-system-x86
make check                     # compile original userspace, test commands and archive
./build.sh                     # build initramfs only
# Obtain and verify an upstream Linux source tree separately, then:
LINUX_SOURCE=/absolute/path/to/linux JOBS=4 ./build.sh
make run                       # serial console; Ctrl-A X exits QEMU
python3 scripts/smoke-boot.py   # real boot, file round-trip, console restart, shutdown
```

Outputs are `build/ominx`, `build/initramfs.cpio.gz`, and, when kernel source is
provided, `build/bzImage` and `build/SHA256SUMS`. The build runs without root.
`make run` attaches no disks and disables emulated networking. Kernel configuration
starts from upstream x86-64 defaults with the required initramfs/console features.
CI uses Linux v6.12 as a fixed **development test baseline**, not as a current
security-maintained release recommendation. Production requires a maintained,
reviewed kernel version and source verification policy.

At the prompt:

```text
help
uname
cat /etc/os-release
mkdir /root/work
cd /root/work
write note Hello from OminX
cat note
ls
poweroff
```

Commands are implemented in `src/core/ominx.c`. There is no POSIX shell parser:
quoting, redirection, pipelines and expansion are not supported. An absolute path
can execute an additional compatible executable, but none are bundled. `write`
replaces the named file. All changes disappear at shutdown. This early console is
root-only, unauthenticated and for isolated VM development, not exposed machines.

## Repository structure

```text
src/core/ominx.c             Original PID 1 supervisor and console utilities
scripts/make-initramfs.py    Rootless, deterministic newc/gzip image builder
scripts/smoke-boot.py        QEMU boot acceptance test
build.sh                    Standalone kernel/initramfs build entry point
Makefile                    Build, check and VM commands
tests/                      Host-side userspace and image-format tests
.github/workflows/source-os.yml  Kernel build and real boot CI
config/                     Preserved legacy desktop assets and Debian recipes
auto/                       Preserved legacy live-build configuration
docs/legacy-debian.md        Previous desktop/ISO documentation
docs/source-os.md            Architecture, licensing boundaries and remaining gates
```

The previous Debian desktop build is available explicitly via `make legacy-build`
and its checks via `make legacy-check`. It is not part of the new standalone
image. Its documentation is historical; it does not describe the new build.

## Desktop direction and licensing

The intended desktop uses KDE Plasma with an original OminX theme, a bottom taskbar,
launcher, pinned applications, window controls and familiar keyboard workflows.
Existing Plasma assets remain available for integration; Plasma is **not yet
included in the standalone image**. No Microsoft code or artwork is included.

Linux, KDE and other upstream components retain their own licenses. Original
proprietary applications can be separated where ownership and dependency licenses
permit. **This checkout remains under its existing AGPLv3 license**; no existing
code has been relicensed and no proprietary rights are implied. See
[the architecture plan](docs/source-os.md) before distributing a product.
